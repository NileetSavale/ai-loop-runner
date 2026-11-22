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
