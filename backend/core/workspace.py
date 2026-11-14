"""Sessions on a user's GitHub repo rather than a folder on this machine.

The repo is cloned into a folder of its own per session. Only https://github.com URLs are accepted, so a session
can't make the server read its own files (file://, a local path) or reach other hosts. A token for a private repo
reaches git through the environment, so it never appears in a command line, the clone's config or the database.

Running a stranger's tests runs their code, so a cloned repo's checks always run in the sandbox (core/sandbox.py):
its dependencies are installed into a container first, then every test run is a container with no network.
LOOP_RUNNER_HOSTED=1 is for a deployment other people use: sessions must come from GitHub there, and each one runs
on its user's own API key, never the server's.
"""
import asyncio
import base64
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from sqlmodel import select

from core.cascade import run_cascade
from core.loop import BroadcastFn, _fail_session, _mark_session_failed, _running, run_loop
from core.sandbox import SandboxError, sandbox_for
from database import get_session as db_session
from models import Session, SessionEvent

WORKSPACES = Path(os.getenv("WORKSPACES_DIR", str(Path.home() / ".loop-runner" / "workspaces")))
HOSTED = os.getenv("LOOP_RUNNER_HOSTED") == "1"
CLONE_TIMEOUT_SECONDS = 180
CLONE_DEPTH = 50
_GITHUB = re.compile(r"^https://github\.com/([A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))/([A-Za-z0-9._-]{1,100}?)(?:\.git)?/?$")
_BRANCH = re.compile(r"^[A-Za-z0-9._/-]{1,200}$")


class CloneError(Exception):
    pass


def github_repo(url: str) -> str:
    """The canonical clone URL for a GitHub repo URL, or ValueError."""
    match = _GITHUB.match(url.strip())
    if not match or match.group(2) in (".", ".."):
        raise ValueError("Use a GitHub repo URL like https://github.com/owner/repo")
    return f"https://github.com/{match.group(1)}/{match.group(2)}.git"


def clone(url: str, dest: Path, branch: str | None = None, token: str | None = None) -> str:
    """Clone into dest and return the commit the session starts from."""
    repo = github_repo(url)
    if branch and (not _BRANCH.match(branch) or branch.startswith("-") or ".." in branch):
        raise ValueError("That branch name isn't valid.")
    env = {"PATH": os.environ.get("PATH", ""), "HOME": str(dest.parent), "GIT_TERMINAL_PROMPT": "0",
           "GIT_ALLOW_PROTOCOL": "https", "GIT_CONFIG_NOSYSTEM": "1"}
    if token:
        auth = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        env.update({"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
                    "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {auth}"})
    dest.parent.mkdir(parents=True, exist_ok=True)
    args = ["git", "clone", "--quiet", "--depth", str(CLONE_DEPTH), "--single-branch", "--no-tags",
            *(["--branch", branch] if branch else []), "--", repo, str(dest)]
    try:
        result = subprocess.run(args, env=env, capture_output=True, text=True, timeout=CLONE_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        shutil.rmtree(dest, ignore_errors=True)
        raise CloneError(f"Cloning took longer than {CLONE_TIMEOUT_SECONDS} seconds.")
    if result.returncode != 0:
        shutil.rmtree(dest, ignore_errors=True)
        detail = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "git failed"
        raise CloneError(f"Couldn't clone {repo}: {detail}. For a private repo, add a token that can read it.")
    # The loop commits a passing attempt, which needs an author
    for key, value in (("user.name", "Loop Runner"), ("user.email", "loop-runner@localhost")):
        subprocess.run(["git", "-C", str(dest), "config", key, value], check=True)
    return head(str(dest))


def head(repo: str) -> str | None:
    result = subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"], capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else None


def owns_workspace(repo_path: str) -> bool:
    """Whether the folder is one this module cloned, so deleting the session may delete it."""
    try:
        return Path(repo_path).resolve().parent == WORKSPACES.resolve()
    except OSError:
        return False


def record(session_id: str, repo_url: str | None, branch: str | None, base: str | None):
    """Where the session's code came from, kept as its first event; /diff compares against base."""
    with db_session() as db:
        db.add(SessionEvent(session_id=session_id, kind="workspace",
                            data=json.dumps({"repo_url": repo_url, "branch": branch, "base": base})))
        db.commit()


def workspace(session_id: str) -> dict:
    """What record() kept: repo_url, branch and base, or {} for an older session."""
    with db_session() as db:
        event = db.exec(select(SessionEvent).where(SessionEvent.session_id == session_id,
                                                   SessionEvent.kind == "workspace")).first()
    return json.loads(event.data) if event else {}


def base_commit(session_id: str) -> str | None:
    return workspace(session_id).get("base")


def diff(repo: str, base: str) -> str:
    """Everything the session changed since base: committed and uncommitted, and new files in a cloned workspace.
    New files are left out of a folder on this machine, since marking them would show in the user's git status."""
    if owns_workspace(repo):
        subprocess.run(["git", "-C", repo, "add", "-A", "--intent-to-add"], capture_output=True)
    return subprocess.run(["git", "-C", repo, "diff", base], capture_output=True, text=True, check=True).stdout


async def run_session(session_id: str, broadcast_fn: BroadcastFn, cascade: bool = False, sandboxed: bool = False,
                      **options):
    """Install the repo's dependencies in a sandbox if asked, then run the loop or the cascade in it."""
    if sandboxed:
        with db_session() as db:
            repo = db.get(Session, session_id).repo_path
        with db_session() as db:
            event = SessionEvent(session_id=session_id, kind="setup",
                                 data=json.dumps({"text": "Installing the repo's dependencies in a sandbox"}))
            db.add(event)
            db.commit()
            event_id = event.id
        await broadcast_fn({"event": "setup", "data": {"text": "Installing the repo's dependencies in a sandbox",
                                                        "id": event_id}})
        try:
            sandbox = await asyncio.to_thread(sandbox_for, repo, str(WORKSPACES / ".scratch"))
            await asyncio.to_thread(sandbox.prepare, lambda _: None)
        except (SandboxError, OSError, subprocess.CalledProcessError) as e:
            reason = f"Couldn't set up the sandbox: {e}"
            _mark_session_failed(session_id, reason)
            await _fail_session(session_id, broadcast_fn, reason)
            _running.pop(session_id, None)
            return
        options["sandbox"] = sandbox
    await (run_cascade if cascade else run_loop)(session_id, broadcast_fn, **options)


def start_session(session_id: str, broadcast_fn: BroadcastFn, cascade: bool = False, sandboxed: bool = False,
                  **options):
    (WORKSPACES / ".scratch").mkdir(parents=True, exist_ok=True)
    task = asyncio.create_task(run_session(session_id, broadcast_fn, cascade, sandboxed, **options))
    _running[session_id] = task
    return task
