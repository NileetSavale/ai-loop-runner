"""The repo map and how it points the agent at a problem. Real files, no LLM."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlmodel import SQLModel, create_engine, select

import database
from core.edits import describe_change
from core.repo_map import MAX_FOCUS_FILES, MAX_PROMPT_MAP_CHARS, build_repo_map, locate_issue, map_for_prompt
from core.verifier import VerifyResult
from database import get_session as db_session
from models import Session, SessionEvent, Task
from tests.test_tool_agent import MODEL, ScriptedModel, turn


def write(root, files):
    for path, content in files.items():
        full = root / path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content)
    return str(root)


APP = {
    "backend/core/loop.py": "from core.agent import run\nfrom . import helpers\n\ndef go():\n    pass\n\nclass Loop:\n    pass\n",
    "backend/core/agent.py": "import os\nimport json\n\nasync def run():\n    pass\n",
    "backend/core/helpers.py": "VALUE = 1\n",
    "backend/tests/test_loop.py": "from core.loop import go\n\ndef test_go():\n    assert go()\n",
    "frontend/lib/api.ts": "export function fetchIt() {}\nexport const BASE = 1;\n",
    "frontend/components/View.tsx": 'import { fetchIt } from "@/lib/api";\nimport React from "react";\nexport function View() {}\n',
    "frontend/node_modules/dep/index.js": "module.exports = 1",
    "README.md": "# not code",
}


@pytest.fixture
def app(tmp_path):
    root = write(tmp_path, APP)
    return root, build_repo_map(root)


def _edges(m):
    return {(e["from"], e["to"]) for e in m["edges"]}


def test_finds_code_and_skips_dependencies(app):
    paths = {n["path"] for n in app[1]["nodes"]}
    assert "backend/core/loop.py" in paths and "frontend/components/View.tsx" in paths
    assert not any("node_modules" in p or p.endswith(".md") for p in paths)


def test_finds_functions_and_classes_with_their_lines(app):
    loop = next(n for n in app[1]["nodes"] if n["path"] == "backend/core/loop.py")
    assert loop["symbols"] == [{"name": "go", "line": 4}, {"name": "Loop", "line": 7}]
    api = next(n for n in app[1]["nodes"] if n["path"] == "frontend/lib/api.ts")
    assert [s["name"] for s in api["symbols"]] == ["fetchIt", "BASE"]


def test_follows_absolute_relative_and_alias_imports_but_not_packages(app):
    edges = _edges(app[1])
    assert ("backend/core/loop.py", "backend/core/agent.py") in edges  # from a parent folder
    assert ("backend/core/loop.py", "backend/core/helpers.py") in edges  # from . import
    assert ("backend/tests/test_loop.py", "backend/core/loop.py") in edges
    assert ("frontend/components/View.tsx", "frontend/lib/api.ts") in edges  # @/ alias
    assert all(not b.endswith(("os.py", "json.py", "react")) for _, b in edges)


def test_callers_sit_left_of_what_they_use(app):
    layers = app[1]["layers"]
    assert layers["backend/tests"] < layers["backend/core"]
    assert layers["frontend/components"] < layers["frontend/lib"]


def test_circular_imports_do_not_hang(tmp_path):
    root = write(tmp_path, {"a/x.py": "from b.y import z\n", "b/y.py": "from a.x import q\n"})
    assert len(build_repo_map(root)["edges"]) == 2


def test_broken_python_stays_on_the_map(tmp_path):
    m = build_repo_map(write(tmp_path, {"bad.py": "def (((:\n"}))
    assert m["nodes"][0]["path"] == "bad.py" and m["nodes"][0]["symbols"] == []


def test_failing_test_points_at_what_it_imports(app):
    output = "backend/tests/test_loop.py:4: in test_go\nE   assert None\n"
    focus = locate_issue(app[1], "", output, [])
    assert focus[0] == {"path": "backend/core/loop.py", "reason": "imported by failing test backend/tests/test_loop.py"}
    assert focus[1]["path"] == "backend/tests/test_loop.py"


def test_crash_in_real_code_comes_before_everything_else(app):
    output = 'File "/venv/lib/site.py", line 9\nbackend/tests/test_loop.py:4: in test_go\nbackend/core/agent.py:5: ValueError\n'
    focus = locate_issue(app[1], "", output, [])
    assert focus[0] == {"path": "backend/core/agent.py", "reason": "in the test failure at line 5"}
    assert not any("site.py" in f["path"] for f in focus)


def test_absolute_and_python_style_trace_paths_are_understood(app):
    root, m = app
    output = f'File "{os.path.realpath(root)}/backend/core/helpers.py", line 1, in <module>\n'
    assert locate_issue(m, "", output, [], root)[0] == {"path": "backend/core/helpers.py", "reason": "in the test failure at line 1"}


def test_user_selection_always_comes_first(app):
    focus = locate_issue(app[1], "", "backend/core/agent.py:5: boom", ["frontend/lib/api.ts"])
    assert focus[0] == {"path": "frontend/lib/api.ts", "reason": "you selected this"}


def test_task_words_match_file_and_function_names_when_tests_say_nothing(app):
    focus = locate_issue(app[1], "Change how fetchit retries", None, [])
    assert focus == [{"path": "frontend/lib/api.ts", "reason": "matches 'fetchit' in the task"}]
    assert locate_issue(app[1], "fix the failing test in this project", None, []) == []


def test_focus_is_capped(tmp_path):
    m = build_repo_map(write(tmp_path, {f"widget_{i}.py": "" for i in range(20)}))
    assert len(locate_issue(m, "widget", None, [])) == MAX_FOCUS_FILES


def test_prompt_map_stays_small_and_keeps_focus_first(tmp_path):
    m = build_repo_map(write(tmp_path, {f"pkg/module_{i}.py": "def f():\n    pass\n" for i in range(400)}))
    text = map_for_prompt(m, [{"path": "pkg/module_399.py", "reason": "x"}])
    assert text.startswith("pkg/module_399.py: f")
    assert len(text) < MAX_PROMPT_MAP_CHARS + 100 and "more files" in text


def test_change_description_counts_and_shows_the_diff():
    change = describe_change("a.py", "one\ntwo\n", "one\nTWO\nthree\n")
    assert (change["added"], change["removed"], change["is_new"]) == (2, 1, False)
    assert "-two" in change["diff"] and "+TWO" in change["diff"]
    assert describe_change("b.py", "", "x\n")["is_new"] is True


# --- through the loop ---

@pytest.fixture
def db(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path}/test.db", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)


def _run(repo, model, files=(), command="true", verify=None):
    import core.loop as loop
    sid = str(uuid.uuid4())
    with db_session() as s:
        s.add(Session(id=sid, name="t", repo_path=str(repo), verify_command=command, model=MODEL, max_iterations=2, status="running"))
        t = Task(id=str(uuid.uuid4()), session_id=sid, title="t", spec="do it")
        t.set_files_context(list(files))
        s.add(t)
        s.commit()
    loop._running[sid] = object()
    events = []

    async def broadcast(e):
        events.append(e)

    patches = [patch("core.agent.get_provider", return_value=model), patch("core.loop.git_commit", return_value="abc"),
               patch("core.loop.invalidate_analytics", new_callable=AsyncMock)]
    if verify:
        patches.append(patch("core.loop.run_verify", verify))
    for p in patches:
        p.start()
    try:
        asyncio.run(loop.run_loop(sid, broadcast, use_map=True))
    finally:
        for p in patches:
            p.stop()
    with db_session() as s:
        saved = s.exec(select(SessionEvent).where(SessionEvent.session_id == sid).order_by(SessionEvent.id)).all()
    return events, saved


def test_agent_gets_the_map_failure_and_likely_files_up_front(tmp_path, db):
    write(tmp_path, APP)
    failing = VerifyResult(False, "backend/tests/test_loop.py:4: in test_go\nE   assert None\n", 1)
    model = ScriptedModel([turn(("write_file", {"path": "backend/core/loop.py", "content": "x = 1\n"})), turn()])
    _run(tmp_path, model, verify=AsyncMock(side_effect=[failing, VerifyResult(True, "ok", 0)]))
    prompt = model.seen[0][0]["content"]
    assert "backend/core/loop.py (imported by failing test backend/tests/test_loop.py)" in prompt
    assert "## Repo map" in prompt and "frontend/lib/api.ts: fetchIt, BASE" in prompt
    assert "E   assert None" in prompt
    assert "from core.agent import run" not in prompt  # names only: including contents measured as more expensive


def test_files_the_user_selected_are_still_included_whole(tmp_path, db):
    write(tmp_path, {"chosen.py": "CHOSEN = 1\n"})
    model = ScriptedModel([turn(("write_file", {"path": "a.py", "content": "x\n"})), turn()])
    _run(tmp_path, model, files=["chosen.py"])
    assert "CHOSEN = 1" in model.seen[0][0]["content"]


def test_test_files_are_not_suspects_just_for_matching_a_word(tmp_path):
    m = build_repo_map(write(tmp_path, {"agent.py": "", "tests/test_agent.py": ""}))
    assert [f["path"] for f in locate_issue(m, "the agent is slow", None, [])] == ["agent.py"]


def test_events_are_broadcast_and_saved_for_the_visual_view(tmp_path, db):
    (tmp_path / "a.py").write_text("old\n")
    model = ScriptedModel([
        turn(("read_file", {"path": "a.py"}), ("edit_file", {"path": "a.py", "old_text": "old", "new_text": "new"}),
             ("read_file", {"path": "../nope"})),
        turn(),
    ])
    events, saved = _run(tmp_path, model, files=["a.py"])
    kinds = [e["event"] for e in events]
    assert kinds[0] == "focus" and kinds.count("tool") == 3 and kinds.count("file_changed") == 1
    assert [s.kind for s in saved if s.kind != "usage"] == ["focus", "tool", "tool", "file_changed", "tool"]
    assert [s.kind for s in saved].count("usage") == 2  # one per model turn
    live = {e["data"]["id"] for e in events if e["event"] in ("focus", "usage", "tool", "file_changed")}
    assert live == {s.id for s in saved}  # the page uses these ids to merge saved and live events
    change = next(e["data"] for e in events if e["event"] == "file_changed")
    assert change["path"] == "a.py" and "+new" in change["diff"]
    bad = [e["data"] for e in events if e["event"] == "tool" and e["data"]["error"]]
    assert bad[0]["target"] == "../nope" and "outside the repo" in bad[0]["error"]
    assert json.loads(saved[0].data)["files"][0] == {"path": "a.py", "reason": "you selected this"}


def test_one_shot_providers_also_report_their_changes(tmp_path, db):
    from providers.base import LLMProvider, LLMResult

    class OneShot(LLMProvider):
        async def complete(self, system, prompt, model, on_token=None):
            return LLMResult(text='<file path="a.py">new</file>', input_tokens=1, output_tokens=1)

    (tmp_path / "a.py").write_text("old\n")
    events, _ = _run(tmp_path, OneShot("k"))
    assert "+new" in next(e["data"]["diff"] for e in events if e["event"] == "file_changed")


def test_session_event_routes_respect_ownership(tmp_path, db):
    from fastapi import HTTPException
    from routes.sessions import delete_session, session_events, session_map
    (tmp_path / "a.py").write_text("x = 1\n")
    sid = str(uuid.uuid4())
    with db_session() as s:
        s.add(Session(id=sid, user_id="owner", name="t", repo_path=str(tmp_path), verify_command="true", model=MODEL))
        s.add(SessionEvent(session_id=sid, kind="tool", data='{"tool": "read_file"}'))
        s.commit()
    owner = {"sub": "owner"}
    assert session_events(sid, owner)[0]["tool"] == "read_file"
    assert session_map(sid, owner)["nodes"][0]["path"] == "a.py"
    for call in (session_events, session_map):
        with pytest.raises(HTTPException) as e:
            call(sid, {"sub": "someone-else"})
        assert e.value.status_code == 404
    asyncio.run(delete_session(sid, owner))
    with db_session() as s:
        assert s.exec(select(SessionEvent)).all() == []
