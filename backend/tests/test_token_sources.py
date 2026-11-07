"""Tests for tracing an agent's tokens back to the parts of its requests they came from."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
from unittest.mock import patch

import pytest

from core.agent import run_agent
from core.loop import build_prompt, continue_prompt
from core.token_sources import EARLIER_REPLIES, SYSTEM, prompt_sources, reply_sources, turn_sources
from core.tools import RepoTools
from providers.base import ToolCall, ToolTurn
from tests.test_tool_agent import MODEL, ScriptedModel

GUIDE = "## Repo map\na.py: f\n\n## Tests already failing before your changes\n- test_x\n\n"


def test_prompt_is_split_at_our_headings_only():
    spec = "Fix f.\n\n## Steps to reproduce\ncall f()"  # an issue's own heading stays part of the task
    prompt = build_prompt(spec, "### a.py\n```\nx\n```", 1, None, GUIDE)
    sizes = prompt_sources(prompt)
    assert set(sizes) == {"task", "guide: repo map", "guide: old failures", "file contents"}
    assert sum(sizes.values()) == len(prompt)


def test_retry_feedback_is_counted_apart_from_the_task():
    prompt = build_prompt("Fix f.", "", 2, "1 failed: test_f", GUIDE)
    sizes = prompt_sources(prompt)
    assert sizes["retry feedback"] > len("1 failed: test_f") and sum(sizes.values()) == len(prompt)


def test_a_continued_retry_is_all_retry_feedback():
    prompt = continue_prompt(2, "1 failed: test_f")
    assert prompt_sources(prompt) == {"retry feedback": len(prompt)}


def test_replies_are_sorted_into_text_edits_and_other_calls():
    content = [
        {"type": "text", "text": "Looking."},
        {"type": "tool_use", "name": "read_file", "input": {"path": "a.py"}},
        {"type": "tool_use", "name": "edit_file", "input": {"path": "a.py", "old_text": "x", "new_text": "y"}},
    ]
    assert set(reply_sources(content)) == {"reply: text", "reply: other tool calls", "reply: edits"}


def test_shares_always_add_up_to_what_the_api_reported():
    turn = ToolTurn("", [], "end_turn", {}, input_tokens=10, output_tokens=50, cache_read_tokens=900, cache_write_tokens=300)
    out = turn_sources(turn, {"a": 1, "b": 2}, {"c": 5}, {})
    assert sum(c["read"] for c in out.values()) == pytest.approx(900)
    assert out["c"]["written"] == pytest.approx(310)
    assert out["unattributed"]["output"] == 50  # a reply we couldn't size still counts


def test_each_turn_charges_new_parts_as_written_and_earlier_ones_as_read(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n" * 50)
    model = ScriptedModel([
        ToolTurn("", [ToolCall("1", "read_file", {"path": "a.py"})], "tool_use", {"role": "assistant", "content": "r"},
                 input_tokens=5, output_tokens=20, cache_read_tokens=1000, cache_write_tokens=400),
        ToolTurn("done", [], "end_turn", {"role": "assistant", "content": "done"},
                 input_tokens=5, output_tokens=10, cache_read_tokens=1400, cache_write_tokens=100),
    ])
    events = []

    async def on_event(kind, data):
        events.append((kind, data))

    with patch("core.agent.get_provider", return_value=model):
        asyncio.run(run_agent(build_prompt("Fix f.", "", 1, None, GUIDE), MODEL,
                              tools=RepoTools(str(tmp_path), "true"), max_cost_usd=1, on_event=on_event))
    first, second = [data["sources"] for kind, data in events if kind == "usage"]
    assert set(first[SYSTEM]) and first[SYSTEM]["read"] == 1000 and first["task"]["written"] > 0
    assert second["results: read_file"]["written"] > 0 and EARLIER_REPLIES in second
    assert second["task"]["read"] > 0 and second["reply: text"]["output"] == 10
