"""The cascade session option (core/cascade.py), with the loop, scout and reviewer replaced by fakes."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
import subprocess
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlmodel import SQLModel, create_engine, select

import core.cascade as cascade
from database import get_session as db_session
from models import Iteration, Session, SessionEvent, Task


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    import database
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout


@pytest.fixture
def repo(tmp_path):
    path = tmp_path / "repo"
    path.mkdir()
    git(path, "init", "-q")
    git(path, "config", "user.email", "t@t")
    git(path, "config", "user.name", "t")
    (path / "app.py").write_text("x = 1\n")
    git(path, "add", "-A")
    git(path, "commit", "-qm", "start")
    (path / "mine.txt").write_text("the user's untracked file\n")
    return path


def seed(repo, model="claude-sonnet-5-5") -> str:
    session_id = str(uuid.uuid4())
    with db_session() as db:
        db.add(Session(id=session_id, name="t", repo_path=str(repo), verify_command="true", model=model, max_iterations=2))
        db.add(Task(id=str(uuid.uuid4()), session_id=session_id, title="t", spec="fix the bug"))
        db.commit()
    return session_id


def fake_loop(outcomes: list[bool], seen: list[dict]):
    """Each call is one model's loop: it edits the repo, records an iteration, commits on a pass and reports."""
    async def run_loop(session_id, broadcast_fn, user_api_key=None, **options):
        with db_session() as db:
            s = db.get(Session, session_id)
            task = db.exec(select(Task).where(Task.session_id == session_id)).first()
            seen.append({"model": s.model, "spec": task.spec, "max_cost_usd": options["max_cost_usd"]})
            repo = s.repo_path
            passed = outcomes[len(seen) - 1]
            s.total_cost_usd += 0.01
            s.status = "passed" if passed else "failed"
            db.add(s)
            db.add(Iteration(id=str(uuid.uuid4()), session_id=session_id, iteration_number=1,
                             status=s.status, cost_usd=0.01))
            db.commit()
        with open(os.path.join(repo, "app.py"), "w") as f:
            f.write(f"x = {len(seen) + 1}\n")
        with open(os.path.join(repo, f"new{len(seen)}.py"), "w") as f:
            f.write("y = 1\n")
        if passed:
            git(repo, "add", "-A")
            git(repo, "commit", "-qm", "pass")
        await broadcast_fn({"event": "verify_output", "data": {"output": "1 failed" if not passed else "ok", "passed": passed}})
        await broadcast_fn({"event": "session_complete", "data": {"status": "passed" if passed else "failed"}})
    return run_loop


async def fake_scout(task, repo_path, model, max_cost_usd, **kwargs):
    return "## Relevant code\n- app.py::x", SimpleNamespace(cost_usd=0.001, input_tokens=10, output_tokens=5)


def fake_review(accept: bool, calls: list):
    async def review_fix(spec, diff, read, note, prompt, user_api_key=None):
        calls.append({"spec": spec, "diff": diff, "original": read("app.py")})
        return {"accept": accept, "why": "it misses the twin function", "cost_usd": 0.02, "input_tokens": 100,
                "output_tokens": 20, "reply": ""}
    return review_fix


def run(session_id, outcomes, accept=True):
    seen, reviews, sent = [], [], []

    async def broadcast(msg):
        sent.append(msg)

    with patch.object(cascade, "run_loop", fake_loop(outcomes, seen)), \
         patch.object(cascade, "run_scout", fake_scout), \
         patch.object(cascade, "review_fix", fake_review(accept, reviews)):
        asyncio.run(cascade.run_cascade(session_id, broadcast, max_cost_usd=1.0))
    steps = [m["data"]["step"] for m in sent if m["event"] == "cascade"]
    finals = [m["data"]["status"] for m in sent if m["event"] == "session_complete"]
    return seen, reviews, steps, finals


def session(session_id):
    with db_session() as db:
        s = db.get(Session, session_id)
        spec = db.exec(select(Task).where(Task.session_id == session_id)).first().spec
        return s, spec


def test_a_reviewed_pass_from_the_cheap_model_ends_the_session(repo):
    session_id = seed(repo)
    seen, reviews, steps, finals = run(session_id, [True], accept=True)
    assert [s["model"] for s in seen] == ["claude-haiku-5-5"]
    assert "## Notes from a teammate" in seen[0]["spec"]
    assert steps == ["scout", "cheap", "review", "reviewed"]
    assert finals == ["passed"]  # one final event, after the review, not the cheap loop's own
    assert reviews[0]["spec"] == "fix the bug" and "x = 2" in reviews[0]["diff"]
    assert reviews[0]["original"] == "x = 1\n"
    assert "mine.txt" not in reviews[0]["diff"]
    s, spec = session(session_id)
    assert s.status == "passed" and s.model == "claude-sonnet-5-5" and spec == "fix the bug"
    assert s.total_cost_usd == pytest.approx(0.001 + 0.01 + 0.02)
    assert (repo / "app.py").read_text() == "x = 2\n"  # the accepted fix stays


def test_a_rejected_pass_is_undone_and_the_main_model_starts_over_with_the_reason(repo):
    session_id = seed(repo)
    seen, _, steps, finals = run(session_id, [True, True], accept=False)
    assert [s["model"] for s in seen] == ["claude-haiku-5-5", "claude-sonnet-5-5"]
    assert "the reviewer said: it misses the twin function" in seen[1]["spec"]
    assert "app.py" in seen[1]["spec"]
    assert steps == ["scout", "cheap", "review", "reviewed", "escalated"]
    assert finals == ["passed"]
    assert seen[1]["max_cost_usd"] == pytest.approx(1.0 - 0.031)
    # The second loop started from the original commit: its edit is the only one, and the first loop's file is gone
    assert (repo / "app.py").read_text() == "x = 3\n"
    assert not (repo / "new1.py").exists() and (repo / "new2.py").exists()
    assert (repo / "mine.txt").exists()


def test_a_cheap_failure_escalates_without_a_review(repo):
    session_id = seed(repo)
    seen, reviews, steps, finals = run(session_id, [False, False])
    assert reviews == []
    assert steps == ["scout", "cheap", "escalated"]
    assert "which didn't pass" in seen[1]["spec"] and "1 failed" in seen[1]["spec"]
    assert finals == ["failed"]
    s, spec = session(session_id)
    assert s.status == "failed" and spec == "fix the bug"
    with db_session() as db:
        events = db.exec(select(SessionEvent).where(SessionEvent.kind == "cascade")).all()
    assert '"cheap_iterations": 1' in events[-1].data


def test_uncommitted_changes_are_refused_before_any_model_call(repo):
    (repo / "app.py").write_text("x = 99\n")
    session_id = seed(repo)
    seen, _, steps, finals = run(session_id, [True])
    assert seen == [] and steps == [] and finals == ["failed"]
    assert (repo / "app.py").read_text() == "x = 99\n"


def test_the_main_model_must_be_a_stronger_claude_model():
    assert cascade.cascade_problem("claude-sonnet-5-5") is None
    assert "stronger" in cascade.cascade_problem("claude-haiku-5-5")
    assert "Claude model" in cascade.cascade_problem("gemini-3.5-flash-lite")
