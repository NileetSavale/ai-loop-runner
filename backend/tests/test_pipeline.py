"""Pipelines (core/pipeline.py): the format's checks, the reviewed-cascade preset, and the engine in core/cascade.py
running pipelines other than the preset. Models, scout and reviewer are the fakes test_cascade uses."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
from unittest.mock import patch

import pytest

import core.cascade as cascade
from core.pipeline import PipelineError, load, parse
from tests.test_cascade import fake_loop, fake_review, fake_scout, fresh_db, repo, seed  # noqa: F401  (fixtures)

FIX = {"kind": "fix", "model": "main", "on_pass": "done", "on_fail": "done"}


def pipeline(**steps):
    return {"name": "t", "start": next(iter(steps)), "steps": steps}


def test_the_preset_is_the_reviewed_cascade():
    p = load("reviewed-cascade")
    assert p.start == "scout"
    assert {s.id: (s.kind, s.model, s.edges) for s in p.steps.values()} == {
        "scout": ("scout", "cheap", {"next": "cheap"}),
        "cheap": ("fix", "cheap", {"on_pass": "review", "on_fail": "escalated"}),
        "review": ("review", "claude-sonnet-5-5", {"on_accept": "done", "on_reject": "escalated"}),
        "escalated": ("fix", "main", {"on_pass": "done", "on_fail": "done"}),
    }
    assert p.steps["escalated"].options == {"undo": True}


@pytest.mark.parametrize("document, reason", [
    (pipeline(a={**FIX, "kind": "deploy"}), "kind 'deploy'"),
    (pipeline(a={**FIX, "model": "gpt-7"}), "model 'gpt-7'"),
    (pipeline(a={**FIX, "on_pass": "b"}), "sends on_pass to 'b'"),
    (pipeline(a={**FIX, "on_fail": "b"}, b={**FIX, "on_fail": "a"}), "cycle: a -> b -> a"),
    (pipeline(a=FIX, b=FIX), "nothing leads to steps ['b']"),
    (pipeline(a={"kind": "fix", "model": "main", "on_pass": "done"}), "doesn't say where ['on_fail'] lead"),
    (pipeline(a={**FIX, "retries": 3}), "unknown fields ['retries']"),
    (pipeline(done=FIX), '"done" ends a pipeline'),
    ({"name": "t", "start": "x", "steps": {"a": FIX}}, "start 'x' is not a step"),
])
def test_a_pipeline_the_engine_cant_run_is_refused_with_the_reason(document, reason):
    with pytest.raises(PipelineError, match=reason.replace("[", r"\[").replace("]", r"\]")):
        parse(document)


def test_a_missing_preset_is_refused():
    with pytest.raises(PipelineError, match="no pipeline 'nope'"):
        load("nope")


def run(session_id, document, outcomes, accept=True):
    seen, reviews, sent = [], [], []

    async def broadcast(msg):
        sent.append(msg)

    with patch.object(cascade, "run_loop", fake_loop(outcomes, seen)), \
         patch.object(cascade, "run_scout", fake_scout), \
         patch.object(cascade, "review_fix", fake_review(accept, reviews)):
        asyncio.run(cascade.run_cascade(session_id, broadcast, max_cost_usd=1.0, pipeline=parse(document)))
    steps = [m["data"]["step"] for m in sent if m["event"] == "cascade"]
    finals = [m["data"]["status"] for m in sent if m["event"] == "session_complete"]
    return seen, steps, finals


def test_a_pipeline_without_a_review_ends_on_the_cheap_models_pass(repo):
    document = pipeline(cheap={"kind": "fix", "model": "cheap", "on_pass": "done", "on_fail": "main"},
                        main={**FIX, "undo": True})
    seen, steps, finals = run(seed(repo), document, [True])
    assert steps == ["cheap"] and finals == ["passed"]
    assert [s["model"] for s in seen] == [cascade.CHEAP_MODEL]
    assert seen[0]["spec"] == "fix the bug"  # no scout ran, so the task is handed over as written


def test_a_review_step_can_use_another_model(repo):
    asked = []

    async def review_fix(spec, diff, read, note, prompt, user_api_key=None, model=None):
        asked.append(model)
        return {"accept": True, "why": "fine", "cost_usd": 0.0, "input_tokens": 1, "output_tokens": 1, "reply": ""}

    document = pipeline(cheap={"kind": "fix", "model": "cheap", "on_pass": "review", "on_fail": "done"},
                        review={"kind": "review", "model": "claude-opus-5-5", "on_accept": "done",
                                "on_reject": "done"})
    with patch.object(cascade, "run_loop", fake_loop([True], [])), patch.object(cascade, "review_fix", review_fix):
        asyncio.run(cascade.run_cascade(seed(repo), lambda m: asyncio.sleep(0), max_cost_usd=1.0,
                                        pipeline=parse(document)))
    assert asked == ["claude-opus-5-5"]


def test_the_api_lists_pipelines_with_their_steps_and_description(monkeypatch):
    import auth
    from fastapi.testclient import TestClient
    from main import app
    monkeypatch.setattr(auth, "ALLOW_ANONYMOUS", True)
    client = TestClient(app)
    listed = client.get("/pipelines").json()
    cascade = next(p for p in listed if p["name"] == "reviewed-cascade")
    assert cascade["start"] == "scout" and "cheap model tries first" in cascade["description"]
    assert {s["id"]: s["edges"] for s in cascade["steps"]}["review"] == {"on_accept": "done", "on_reject": "escalated"}
    assert client.get("/pipelines/reviewed-cascade").json() == cascade


def test_the_api_refuses_a_name_that_is_not_a_pipeline_file(monkeypatch):
    import auth
    from fastapi.testclient import TestClient
    from main import app
    monkeypatch.setattr(auth, "ALLOW_ANONYMOUS", True)
    client = TestClient(app)
    assert client.get("/pipelines/nope").status_code == 404
    assert client.get("/pipelines/..%2Fmain").status_code == 404


CHECK = {"kind": "command", "run": "true", "on_pass": "done", "on_fail": "done"}


@pytest.mark.parametrize("step, reason", [
    ({**CHECK, "model": "cheap"}, "runs no model"),
    ({**CHECK, "run": "  "}, "needs `run`"),
    ({k: v for k, v in CHECK.items() if k != "run"}, "needs `run`"),
])
def test_a_command_step_runs_a_command_and_no_model(step, reason):
    with pytest.raises(PipelineError, match=reason):
        parse(pipeline(check=step))


@pytest.fixture
def pipelines_dir(tmp_path, monkeypatch):
    """A scratch backend/pipelines/, with the built-in pipeline in it."""
    import shutil
    import core.pipeline as module
    shutil.copy(module.PIPELINES / "reviewed-cascade.yaml", tmp_path)
    monkeypatch.setattr(module, "PIPELINES", tmp_path)
    return tmp_path


def test_a_saved_pipeline_round_trips_through_its_file(pipelines_dir):
    from core.pipeline import save
    doc = pipeline(cheap={"kind": "fix", "model": "cheap", "on_pass": "lint", "on_fail": "done"},
                   lint={**CHECK, "run": "ruff check ."})
    save("lint-after-fix", doc)
    loaded = load("lint-after-fix")
    assert loaded.name == "lint-after-fix"
    assert loaded.steps["lint"].options == {"run": "ruff check ."}
    assert loaded.steps["cheap"].edges == {"on_pass": "lint", "on_fail": "done"}


@pytest.mark.parametrize("name, reason", [
    ("reviewed-cascade", "built in and read-only"),
    ("Has Spaces", "lowercase letters"),
    ("../escape", "lowercase letters"),
])
def test_saving_refuses_built_ins_and_unsafe_names(pipelines_dir, name, reason):
    from core.pipeline import save
    with pytest.raises(PipelineError, match=reason):
        save(name, pipeline(a=FIX))


def test_a_pipeline_that_cant_run_is_not_saved(pipelines_dir):
    from core.pipeline import save
    with pytest.raises(PipelineError, match="cycle"):
        save("loops", pipeline(a={**FIX, "on_fail": "b"}, b={**FIX, "on_fail": "a"}))
    assert not (pipelines_dir / "loops.yaml").exists()


def test_delete_removes_a_saved_pipeline_but_not_a_built_in(pipelines_dir):
    from core.pipeline import delete, save
    save("mine", pipeline(a=FIX))
    delete("mine")
    assert not (pipelines_dir / "mine.yaml").exists()
    with pytest.raises(PipelineError, match="built in"):
        delete("reviewed-cascade")


def test_the_api_saves_and_deletes_locally_and_refuses_on_a_hosted_server(pipelines_dir, monkeypatch):
    import auth
    import routes.pipelines
    from fastapi.testclient import TestClient
    from main import app
    monkeypatch.setattr(auth, "ALLOW_ANONYMOUS", True)
    client = TestClient(app)
    body = pipeline(a={**CHECK, "run": "pytest -q"})
    saved = client.put("/pipelines/mine", json=body)
    assert saved.status_code == 200 and saved.json()["steps"][0]["options"] == {"run": "pytest -q"}
    assert client.put("/pipelines/reviewed-cascade", json=body).status_code == 422
    assert "kind 'deploy'" in client.put("/pipelines/bad", json=pipeline(a={**FIX, "kind": "deploy"})).json()["detail"]
    monkeypatch.setattr(routes.pipelines, "HOSTED", True)
    assert client.put("/pipelines/mine", json=body).status_code == 403
    assert client.delete("/pipelines/mine").status_code == 403
    monkeypatch.setattr(routes.pipelines, "HOSTED", False)
    assert client.delete("/pipelines/mine").json() == {"deleted": "mine"}


def test_a_command_step_runs_in_the_repo_and_branches_on_its_exit_code(repo):
    document = pipeline(cheap={"kind": "fix", "model": "cheap", "on_pass": "lint", "on_fail": "done"},
                        lint={**CHECK, "run": "test -f mine.txt && false", "on_fail": "main"},
                        main={**FIX, "undo": True})
    seen, steps, finals = run(seed(repo), document, [True, True])
    assert steps == ["cheap", "lint", "main"]  # the command failed, so its on_fail ran the main model
    assert [s["model"] for s in seen] == [cascade.CHEAP_MODEL, "claude-sonnet-5-5"]
    assert finals == ["passed"]


def test_a_session_runs_its_pipeline_and_records_which(repo):
    from database import get_session as db_session
    from models import SessionEvent
    from sqlmodel import select
    sid = seed(repo)
    run(sid, pipeline(cheap={"kind": "fix", "model": "cheap", "on_pass": "done", "on_fail": "done"}), [True])
    with db_session() as db:
        kinds = {e.kind: e.data for e in db.exec(select(SessionEvent).where(SessionEvent.session_id == sid))}
    assert kinds["pipeline"] == '{"name": "t"}'


def test_a_session_asking_for_a_missing_pipeline_is_refused_before_it_starts(tmp_path, monkeypatch):
    import auth
    from fastapi.testclient import TestClient
    from main import app
    monkeypatch.setattr(auth, "ALLOW_ANONYMOUS", True)
    response = TestClient(app).post("/sessions", json={
        "name": "t", "repo_path": str(tmp_path), "verify_command": "true", "model": "claude-sonnet-5-5",
        "pipeline": "nope", "task": {"title": "t", "spec": "s"}})
    assert response.status_code == 400 and "No pipeline 'nope'" in response.json()["detail"]


@pytest.mark.parametrize("command, status", [("true", "passed"), ("false", "failed")])
def test_a_pipeline_of_commands_only_ends_with_the_last_commands_result(repo, command, status):
    from database import get_session as db_session
    from models import Session
    sid = seed(repo)
    _, steps, finals = run(sid, pipeline(check={**CHECK, "run": command}), [])
    assert steps == ["check"] and finals == [status]
    with db_session() as db:
        assert db.get(Session, sid).status == status


APPROVE = {"kind": "approve", "on_accept": "done", "on_reject": "main"}


def _answer_when_waiting(session_id: str, accept: bool, note: str = ""):
    """A person answering in the app: once the step waits, the API saves their answer."""
    import json
    import threading
    import time
    from database import get_session as db_session
    from models import SessionEvent
    from routes.sessions import _waiting_for

    def answer():
        for _ in range(200):
            with db_session() as db:
                step = _waiting_for(session_id, db)
                if step:
                    db.add(SessionEvent(session_id=session_id, kind="approval",
                                        data=json.dumps({"step": step, "accept": accept, "note": note})))
                    db.commit()
                    return
            time.sleep(0.02)
    threading.Thread(target=answer, daemon=True).start()


@pytest.fixture
def fast_approval(monkeypatch):
    monkeypatch.setattr(cascade, "APPROVAL_POLL_SECONDS", 0.02)


def test_an_approval_ends_the_session_on_the_fix(repo, fast_approval):
    sid = seed(repo)
    _answer_when_waiting(sid, accept=True)
    document = pipeline(cheap={"kind": "fix", "model": "cheap", "on_pass": "ok", "on_fail": "done"},
                        ok=APPROVE, main={**FIX, "undo": True})
    seen, steps, finals = run(sid, document, [True])
    assert steps == ["cheap", "ok", "approved"]  # waiting at ok, then the answer
    assert finals == ["passed"] and len(seen) == 1


def test_a_rejection_hands_its_note_to_the_next_step(repo, fast_approval):
    sid = seed(repo)
    _answer_when_waiting(sid, accept=False, note="Don't touch the public API")
    document = pipeline(cheap={"kind": "fix", "model": "cheap", "on_pass": "ok", "on_fail": "done"},
                        ok=APPROVE, main={**FIX, "undo": True})
    seen, steps, finals = run(sid, document, [True, True])
    assert steps == ["cheap", "ok", "approved", "main"]
    assert "Don't touch the public API" in seen[1]["spec"]


def test_no_answer_in_time_is_a_rejection(repo, fast_approval):
    sid = seed(repo)
    document = pipeline(cheap={"kind": "fix", "model": "cheap", "on_pass": "ok", "on_fail": "done"},
                        ok={**APPROVE, "timeout_hours": 0.0002}, main={**FIX, "undo": True})
    seen, steps, _ = run(sid, document, [True, True])
    assert steps == ["cheap", "ok", "approved", "main"]
    assert "No one answered within" in seen[1]["spec"]


def test_the_api_takes_one_answer_for_the_step_a_session_waits_on(repo, monkeypatch):
    import json
    import auth
    from fastapi.testclient import TestClient
    from database import get_session as db_session
    from main import app
    from models import SessionEvent
    monkeypatch.setattr(auth, "ALLOW_ANONYMOUS", True)
    client = TestClient(app)
    sid = seed(repo)
    answer = {"step": "ok", "accept": True}
    assert client.post(f"/sessions/{sid}/approval", json=answer).status_code == 409  # not waiting yet
    with db_session() as db:
        db.add(SessionEvent(session_id=sid, kind="cascade", data=json.dumps({"step": "ok", "kind": "approve", "waiting": True})))
        db.commit()
    listed = next(s for s in client.get("/sessions").json() if s["id"] == sid)
    assert listed["waiting_for"] == "ok"
    assert client.post(f"/sessions/{sid}/approval", json={**answer, "step": "other"}).status_code == 409
    assert client.post(f"/sessions/{sid}/approval", json=answer).status_code == 200
    assert client.post(f"/sessions/{sid}/approval", json=answer).status_code == 409  # only once


def test_notifications_go_out_for_a_session_end_and_a_wait_for_approval():
    from core.notify import message_for
    assert message_for({"event": "session_complete", "data": {"status": "passed"}}, "Fix login") == \
        ("Session passed", "Fix login")
    assert message_for({"event": "cascade", "data": {"kind": "approve", "waiting": True}}, "Fix login")[0] == \
        "Waiting for your approval"
    assert message_for({"event": "usage", "data": {}}, "Fix login") is None


def test_a_device_registers_once_per_token(monkeypatch):
    import auth
    from fastapi.testclient import TestClient
    from main import app
    monkeypatch.setattr(auth, "ALLOW_ANONYMOUS", True)
    client = TestClient(app)
    first = client.post("/devices", json={"platform": "ios", "token": "apns-token-123"}).json()["id"]
    again = client.post("/devices", json={"platform": "ios", "token": "apns-token-123"}).json()["id"]
    assert first == again
    assert client.post("/devices", json={"platform": "blackberry", "token": "apns-token-123"}).status_code == 422
    assert client.delete(f"/devices/{first}").json() == {"deleted": first}
