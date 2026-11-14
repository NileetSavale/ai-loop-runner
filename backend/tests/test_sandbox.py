import asyncio
import json
from unittest.mock import patch

import pytest

import core.verifier
from core.sandbox import Sandbox, node_sandbox
from core.verifier import run_verify


def _write(path, text=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "app"
    _write(root / "package.json", json.dumps({"workspaces": ["web"]}))
    _write(root / "package-lock.json", "root lock")
    _write(root / "web/package.json", "{}")
    _write(root / "web/package-lock.json", "web lock")
    _write(root / "web/.env.local", "KEY=1")
    _write(root / "web/.env.example", "KEY=")
    _write(root / "tool/package.json", "{}")
    _write(root / "tool/package-lock.json", "tool lock")
    _write(root / "web/Dockerfile", "FROM node:20-alpine AS deps\n")
    _write(root / "node_modules/x/package-lock.json", "ignored")
    _write(root / "node_modules/x/.env", "ignored")
    return root


def test_node_sandbox_installs_workspace_roots_only(repo, tmp_path):
    box = node_sandbox(str(repo), str(tmp_path))
    # web is a workspace of the root, so the root's install fills it; tool has its own
    assert box.installs == [".", "tool"]
    assert set(box.volumes) == {".", "web", "tool"}
    assert box.volumes["web"].endswith(box.volumes["."].rsplit("-", 1)[1])
    assert box.volumes["tool"] != box.volumes["."]
    assert box.secrets == ["web/.env.local"]
    assert box.image == "node:20-bookworm-slim"


def test_new_lockfile_gets_new_volumes(repo, tmp_path):
    before = node_sandbox(str(repo), str(tmp_path)).volumes
    (repo / "package-lock.json").write_text("changed")
    after = node_sandbox(str(repo), str(tmp_path)).volumes
    assert after["."] != before["."] and after["web"] != before["web"] and after["tool"] == before["tool"]


def test_checks_get_no_network_read_only_deps_and_hidden_secrets(repo, tmp_path):
    box = node_sandbox(str(repo), str(tmp_path))
    args = box.argv("npm test", str(repo), name="check")
    joined = " ".join(args)
    assert args[args.index("--network") + 1] == "none"
    assert f"{box.volumes['web']}:/work/web/node_modules:ro" in args
    assert "/work/web/node_modules/.vite" in joined  # scratch space for caches
    assert f"{box.empty_file}:/work/web/.env.local:ro" in args
    assert args[-4:] == [box.image, "sh", "-c", "npm test"]
    assert "HOME=/tmp" in args and not any(a.startswith("/Users") and ":/work" not in a for a in args)


def test_install_has_network_and_writable_deps(repo, tmp_path):
    box = node_sandbox(str(repo), str(tmp_path))
    args = box.argv("npm ci", str(repo), network=True, writable_deps=True, workdir="tool")
    assert "--network" not in args
    assert f"{box.volumes['tool']}:/work/tool/node_modules" in args
    assert args[args.index("-w") + 1] == "/work/tool"


class _LocalSandbox(Sandbox):
    """Runs the command on this machine, so the wiring can be tested without Docker."""
    def argv(self, command, cwd, name=None, **_):
        return ["sh", "-c", f"cd {cwd} && echo in-sandbox && {command}"]


def test_run_verify_uses_the_sandbox(tmp_path):
    result = asyncio.run(run_verify("echo ran", str(tmp_path), _LocalSandbox(image="", repo=str(tmp_path))))
    assert result.passed and result.output.split() == ["in-sandbox", "ran"]


def test_timeout_kills_the_container(tmp_path):
    with patch.object(core.verifier, "MAX_TIMEOUT", 0.5), patch.object(core.verifier, "kill") as kill:
        result = asyncio.run(run_verify("sleep 5", str(tmp_path), _LocalSandbox(image="", repo=str(tmp_path))))
    assert not result.passed and "TIMEOUT" in result.output
    assert kill.call_args.args[0].startswith("loop-runner-check-")


# --- Python repos ---

from core.sandbox import SandboxError, python_sandbox, python_test_sets


def _pyproject(root, text):
    (root / "pyproject.toml").write_text(text)


def test_a_dependency_group_named_tests_is_installed(tmp_path):
    _pyproject(tmp_path, '[project]\nname = "x"\n[dependency-groups]\ndev = ["tox"]\ntests = ["freezegun", "pytest"]\n')
    assert python_test_sets(tmp_path) == (["tests"], [], [])
    sandbox = python_sandbox(str(tmp_path), str(tmp_path))
    assert "pip install -q --group tests" in sandbox.python_install and "--group dev" not in sandbox.python_install
    assert "pip install -q -e ." in sandbox.python_install


def test_a_test_extra_goes_into_the_editable_install(tmp_path):
    _pyproject(tmp_path, '[project]\nname = "x"\n[project.optional-dependencies]\ntest = ["hypothesis"]\n')
    assert "pip install -q -e '.[test]'" in python_sandbox(str(tmp_path), str(tmp_path)).python_install


def test_requirements_folder_files_and_dev_as_a_fallback(tmp_path):
    (tmp_path / "requirements.txt").write_text("requests\n")
    (tmp_path / "requirements").mkdir()
    (tmp_path / "requirements" / "dev.txt").write_text("pytest-mock\n")
    (tmp_path / "requirements" / "docs.txt").write_text("sphinx\n")
    install = python_sandbox(str(tmp_path), str(tmp_path)).python_install
    assert "-r requirements.txt" in install and "-r requirements/dev.txt" in install and "docs.txt" not in install


def test_a_repo_with_nothing_to_install_from_is_refused(tmp_path):
    (tmp_path / "main.py").write_text("x = 1\n")
    with pytest.raises(SandboxError):
        python_sandbox(str(tmp_path), str(tmp_path))
