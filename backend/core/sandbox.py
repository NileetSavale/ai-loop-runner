"""Run a repo's checks in a container, so code the agents write never runs on the host.

The container gets the repo and nothing else: no network, no home folder, no host environment, and the repo's
credential files covered by empty ones. Dependencies are installed once, for Linux, into Docker volumes that checks
can only read, so agent code can't change them.
"""
import hashlib
import json
import os
import re
import subprocess
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from core.edits import is_secret_path

DEFAULT_NODE_IMAGE = "node:22-bookworm-slim"
_SKIPPED_DIRS = {".git", "node_modules", ".next", ".venv", "venv", "dist", "build", "__pycache__"}
_DOCKERFILE_NODE = re.compile(r"^FROM\s+node:(\d+)", re.M | re.I)
# Limits for a check run: enough for a type-check of a large app, not enough to take the machine down
LIMITS = ["--memory", "4g", "--cpus", "2", "--pids-limit", "1024"]
# Folders inside node_modules that tools write caches to (Vite and Vitest, Babel and others). The dependencies are
# read-only during checks, so these get a scratch space that is thrown away with the container.
CACHE_DIRS = [".vite", ".cache"]


class SandboxError(Exception):
    pass


@dataclass
class Sandbox:
    image: str
    repo: str
    # Repo-relative folder ("." for the root) -> Docker volume holding that folder's Linux node_modules
    volumes: dict[str, str] = field(default_factory=dict)
    # Folders to run the install in. An npm workspace's packages are installed by its root, into the workspace
    # members' node_modules too, so members have a volume but no install of their own.
    installs: list[str] = field(default_factory=list)
    # Repo-relative credential files, covered inside the container
    secrets: list[str] = field(default_factory=list)
    empty_file: str = ""

    def argv(self, command: str, cwd: str, name: str | None = None, network: bool = False,
             writable_deps: bool = False, workdir: str = ".") -> list[str]:
        """docker run arguments that run command in a container with cwd mounted as the repo. cwd can be a copy of
        the repo, since dependencies and covered files are placed by repo-relative path."""
        args = ["docker", "run", "--rm", "--name", name or f"loop-runner-check-{uuid.uuid4().hex[:12]}",
                "--security-opt", "no-new-privileges", "--cap-drop", "ALL", *LIMITS,
                "-e", "CI=1", "-e", "HOME=/tmp", "-e", "npm_config_cache=/tmp/.npm",
                "-v", f"{os.path.abspath(cwd)}:/work"]
        if not network:
            args += ["--network", "none"]
        for folder, volume in self.volumes.items():
            target = "/work/node_modules" if folder == "." else f"/work/{folder}/node_modules"
            args += ["-v", f"{volume}:{target}" + ("" if writable_deps else ":ro")]
            if not writable_deps:
                args += [a for d in CACHE_DIRS for a in ("--tmpfs", f"{target}/{d}")]
        for rel in self.secrets:
            args += ["-v", f"{self.empty_file}:/work/{rel}:ro"]
        workdir = "/work" if workdir == "." else f"/work/{workdir}"
        return args + ["-w", workdir, self.image, "sh", "-c", command]

    def prepare(self, log=print) -> None:
        """Pull the image and install dependencies into the volumes, from the repo's lockfiles. The install has
        network access (it downloads packages) but still never sees the host or the credential files."""
        if subprocess.run(["docker", "image", "inspect", self.image], capture_output=True).returncode != 0:
            log(f"Pulling {self.image}...")
            _check(subprocess.run(["docker", "pull", self.image], capture_output=True, text=True), "pull the image")
        for folder in self.installs:
            volume = self.volumes[folder]
            if _volume_ready(self.image, volume):
                log(f"Dependencies for {folder} are already installed ({volume}).")
                continue
            log(f"Installing dependencies for {folder} into {volume}...")
            for v in self.volumes.values():
                subprocess.run(["docker", "volume", "create", v], capture_output=True, check=True)
            # npm ci empties node_modules first, which works on a mounted volume. The marker records a finished
            # install, so an interrupted one is redone.
            # The cache folders must exist to be mounted over during checks
            caches = " ".join(f"{f}/node_modules/{d}" for f in self.volumes for d in CACHE_DIRS)
            result = subprocess.run(self.argv(f"npm ci --no-audit --no-fund && cd /work && mkdir -p {caches}"
                                              f" && touch {folder}/node_modules/.loop-runner-ready",
                                              self.repo, network=True, writable_deps=True, workdir=folder),
                                    capture_output=True, text=True)
            if result.returncode != 0:
                subprocess.run(["docker", "volume", "rm", "-f", volume], capture_output=True)
            _check(result, f"install dependencies for {folder}")


def node_sandbox(repo: str, scratch: str, image: str | None = None) -> Sandbox:
    """A sandbox for a Node repo: an install in each folder with a package-lock.json that isn't an npm workspace
    member, and a volume for each of those folders and their members. Volumes are named after the repo and the
    installing lockfile's contents, so a changed lockfile gets a fresh install."""
    root = Path(repo).resolve()
    locked = sorted(str(p.parent.relative_to(root)) for p in _walk(root) if p.name == "package-lock.json")
    if not locked:
        raise SandboxError("No package-lock.json found. Only npm repos are supported so far.")
    members = {folder: _workspaces(root, folder) for folder in locked}
    installs = [f for f in locked if not any(f in m for m in members.values())]
    repo_id = hashlib.sha256(str(root).encode()).hexdigest()[:8]
    volumes = {}
    for folder in installs:
        lock = hashlib.sha256((root / folder / "package-lock.json").read_bytes()).hexdigest()[:8]
        for f in [folder, *members[folder]]:
            slug = re.sub(r"[^a-z0-9]+", "-", f"{root.name}-{f}".lower()).strip("-")
            volumes[f] = f"loop-runner-deps-{slug}-{repo_id}-{lock}"
    empty = Path(scratch) / "loop-runner-empty"
    empty.write_text("")
    return Sandbox(image=image or _node_image(root), repo=str(root), volumes=volumes, installs=installs,
                   secrets=[str(p.relative_to(root)) for p in _walk(root) if is_secret_path(str(p.relative_to(root)))],
                   empty_file=str(empty))


def kill(name: str) -> None:
    subprocess.run(["docker", "kill", name], capture_output=True)


def _node_image(root: Path) -> str:
    """The Node major version the repo asks for: .nvmrc, then its Dockerfiles, then a current LTS."""
    nvmrc = root / ".nvmrc"
    if nvmrc.is_file() and (m := re.match(r"v?(\d+)", nvmrc.read_text().strip())):
        return f"node:{m.group(1)}-bookworm-slim"
    for dockerfile in sorted(_walk(root, "Dockerfile")):
        if m := _DOCKERFILE_NODE.search(dockerfile.read_text(errors="replace")):
            return f"node:{m.group(1)}-bookworm-slim"
    return DEFAULT_NODE_IMAGE


def _workspaces(root: Path, folder: str) -> list[str]:
    """Repo-relative folders of the npm workspaces declared in folder's package.json."""
    try:
        spec = json.loads((root / folder / "package.json").read_text()).get("workspaces", [])
    except (OSError, ValueError):
        return []
    patterns = spec.get("packages", []) if isinstance(spec, dict) else spec
    found = {p for pattern in patterns for p in (root / folder).glob(pattern) if (p / "package.json").is_file()}
    return sorted(str(p.relative_to(root)) for p in found)


def _walk(root: Path, name: str | None = None):
    for folder, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in _SKIPPED_DIRS]
        for f in files:
            if name is None or f == name:
                yield Path(folder) / f


def _volume_ready(image: str, volume: str) -> bool:
    result = subprocess.run(["docker", "run", "--rm", "--network", "none", "-v", f"{volume}:/deps:ro", image,
                             "test", "-f", "/deps/.loop-runner-ready"], capture_output=True)
    return result.returncode == 0


def _check(result: subprocess.CompletedProcess, what: str) -> None:
    if result.returncode != 0:
        raise SandboxError(f"Couldn't {what}:\n{(result.stdout or '')[-2000:]}{(result.stderr or '')[-2000:]}")
