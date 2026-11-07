"""Estimate where an agent's tokens go: which part of the prompt, which tool's results, which kind of reply.

The API reports tokens per turn, not per part, so each turn's real counts are shared out by character count:
cache writes (and the few uncached input tokens) over what's new in this turn's request, cache reads over what was
sent before, and output over this turn's reply. The totals always match the API; only the split is estimated.
"""
import json
import re

SYSTEM = "system prompt and tools"
EARLIER_REPLIES = "earlier replies, resent"

# Headings build_prompt and _build_guide use. Only these split the prompt, since an issue's own text can use "## "
_SECTIONS = {
    "## Task Spec": "task",
    "## Likely places to look": "guide: likely places",
    "## Repo map": "guide: repo map",
    "## Tests already failing before your changes": "guide: old failures",
    "## Test output before your changes": "guide: test output before",
    "## Current File Contents": "file contents",
}
_SECTION = re.compile("^(" + "|".join(re.escape(h) for h in _SECTIONS) + ")$", re.M)
_RETRY = "\n\n> attempt #"


def prompt_sources(prompt: str) -> dict[str, int]:
    """Characters in each part of the prompt that starts an attempt."""
    sizes: dict[str, int] = {}

    def add(label: str, text: str):
        if text:
            sizes[label] = sizes.get(label, 0) + len(text)

    if prompt.startswith(_RETRY.lstrip()):
        return {"retry feedback": len(prompt)}  # a retry that continues the conversation sends only this
    cuts = list(_SECTION.finditer(prompt))
    add("task", prompt[:cuts[0].start()] if cuts else prompt)
    for match, following in zip(cuts, cuts[1:] + [None]):
        text = prompt[match.start():following.start() if following else len(prompt)]
        label = _SECTIONS[match.group(1)]
        if label == "task" and _RETRY in text:
            # The previous attempt's test output rides along with the task on a retry
            text, retry = text.split(_RETRY, 1)
            add("retry feedback", _RETRY + retry)
        add(label, text)
    return sizes


def _field(block, name):
    return block.get(name) if isinstance(block, dict) else getattr(block, name, None)


def reply_sources(content) -> dict[str, int]:
    """Characters in each kind of output: explanation, edits, or other tool calls."""
    if isinstance(content, str):
        return {"reply: text": len(content)} if content else {}
    sizes: dict[str, int] = {}
    for block in content or []:
        kind = _field(block, "type")
        if kind == "text":
            label, size = "reply: text", len(_field(block, "text") or "")
        elif kind == "thinking":
            label, size = "reply: thinking", len(_field(block, "thinking") or "")
        elif kind == "tool_use":
            name = _field(block, "name")
            label = "reply: edits" if name in ("edit_file", "write_file", "change_existing_test") else "reply: other tool calls"
            size = len(json.dumps(_field(block, "input") or {}))
        else:
            continue
        sizes[label] = sizes.get(label, 0) + size
    return sizes


def share(total: int, sizes: dict[str, int]) -> dict[str, float]:
    chars = sum(sizes.values())
    if not total:
        return {}
    if not chars:
        return {"unattributed": float(total)}
    return {label: total * size / chars for label, size in sizes.items() if size}


def turn_sources(turn, read: dict[str, int], written: dict[str, int], reply: dict[str, int]) -> dict[str, dict[str, float]]:
    """One turn's real token counts, shared out by source: {source: {"written", "read", "output"}}."""
    out: dict[str, dict[str, float]] = {}
    for kind, tokens, sizes in (
        ("written", turn.cache_write_tokens + turn.input_tokens, written),
        ("read", turn.cache_read_tokens, read),
        ("output", turn.output_tokens, reply),
    ):
        for label, amount in share(tokens, sizes).items():
            out.setdefault(label, {"written": 0.0, "read": 0.0, "output": 0.0})[kind] += amount
    return out


def merge_sizes(into: dict[str, int], more: dict[str, int]):
    for label, size in more.items():
        into[label] = into.get(label, 0) + size


def merge(total: dict[str, dict[str, float]], part: dict[str, dict[str, float]]):
    for label, counts in part.items():
        into = total.setdefault(label, {"written": 0.0, "read": 0.0, "output": 0.0})
        for kind, amount in counts.items():
            into[kind] = into.get(kind, 0.0) + amount
