"""Sessions on a GitHub repo (core/workspace.py): which URLs are accepted, how a token reaches git, the diff."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import subprocess
from pathlib import Path

import pytest

import core.workspace as workspace


@pytest.mark.parametrize("url", [
    "https://github.com/psf/requests", "https://github.com/psf/requests.git", "https://github.com/a-b/c.d_e/",
])
def test_github_urls_are_accepted(url):
    assert workspace.github_repo(url).startswith("https://github.com/") and workspace.github_repo(url).endswith(".git")


@pytest.mark.parametrize("url", [
    "file:///etc", "/Users/me/repo", "http://github.com/a/b", "https://gitlab.com/a/b", "https://github.com/a",
    "https://github.com/a/b/tree/main", "https://github.com.evil.com/a/b", "https://user@github.com/a/b",
    "https://github.com/a/..", "https://github.com/-a/b", "git@github.com:a/b.git", "https://github.com/a/b?x=1",
])
def test_anything_else_is_refused(url):
    with pytest.raises(ValueError):
        workspace.github_repo(url)


def test_a_token_reaches_git_through_the_environment_only(tmp_path, monkeypatch):
    calls, real_run = [], subprocess.run

    def fake_run(args, **kwargs):
        calls.append((args, kwargs.get("env")))
        if args[:2] == ["git", "clone"]:
            dest = Path(args[-1])
            dest.mkdir(parents=True)
            real_run(["git", "init", "-q", str(dest)], check=True)
            return subprocess.CompletedProcess(args, 0, "", "")
        return real_run(args, **kwargs)

    monkeypatch.setattr(workspace.subprocess, "run", fake_run)
    workspace.clone("https://github.com/me/private", tmp_path / "ws" / "s1", branch="dev", token="ghp_secret")
    args, env = calls[0]
    assert "ghp_secret" not in " ".join(args)
    assert args[-2:] == ["https://github.com/me/private.git", str(tmp_path / "ws" / "s1")] and "--" in args
    assert env["GIT_CONFIG_KEY_0"] == "http.https://github.com/.extraheader"
    assert env["GIT_ALLOW_PROTOCOL"] == "https" and env["GIT_TERMINAL_PROMPT"] == "0"
    assert "ghp_secret" not in (tmp_path / "ws" / "s1" / ".git" / "config").read_text()
    assert ["--branch", "dev"] == args[args.index("--branch"):args.index("--branch") + 2]


@pytest.mark.parametrize("branch", ["--upload-pack=x", "a..b", "a b", "x;rm"])
def test_bad_branch_names_are_refused_before_git_runs(tmp_path, branch):
    with pytest.raises(ValueError):
        workspace.clone("https://github.com/a/b", tmp_path / "s", branch=branch)


def test_the_diff_covers_commits_edits_and_new_files_in_a_workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace, "WORKSPACES", tmp_path)
    repo = tmp_path / "s1"
    repo.mkdir()
    git = lambda *a: subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True)
    git("init", "-q")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    (repo / "a.py").write_text("x = 1\n")
    git("add", "-A")
    git("commit", "-qm", "start")
    base = workspace.head(str(repo))
    (repo / "a.py").write_text("x = 2\n")
    git("commit", "-qam", "loop pass")
    (repo / "a.py").write_text("x = 3\n")
    (repo / "new.py").write_text("y = 1\n")
    patch = workspace.diff(str(repo), base)
    assert "-x = 1" in patch and "+x = 3" in patch and "+y = 1" in patch
    assert workspace.owns_workspace(str(repo)) and not workspace.owns_workspace(str(tmp_path))
