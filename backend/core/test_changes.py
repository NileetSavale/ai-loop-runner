"""Whether an agent may change an existing test: fixed checks first, and a reviewer only when they can't decide.

Agents weaken tests most often exactly when a test really does need to change, and LLM monitors miss a third or
more of that cheating (ImpossibleBench, 2025). So nothing that only an LLM could catch is left to the LLM alone:
emptying, deleting or skipping tests is refused outright, and only changes that touch what a test checks go to
review.
"""
import difflib
import json
import re
from dataclasses import dataclass

_SKIP = re.compile(r"pytest\.mark\.(skip|skipif|xfail)|pytest\.(skip|xfail)\(|unittest\.(skip|expectedFailure)|@skip\w*|\bxfail\b")
_TEST_DEF = re.compile(r"^\s*(?:async\s+)?def\s+(test\w*)|^\s*class\s+(Test\w*)")
# A line that checks something: assert statements, unittest asserts, raises(...), pytester's fnmatch_lines
_CHECK = re.compile(r"\bassert|\braises\(|fnmatch_lines")

REVIEW_SYSTEM_PROMPT = """You review one proposed change to an existing test in a code repository.

A coding agent wants to change this test while working on the task below. Agents sometimes weaken tests so their
code passes, so be strict. Approve only if both are true:
1. The task itself requires the behaviour this test checks to change, for example the task asks for an error to
   stop being raised, or for an output format to change. Wanting the test to pass is not a reason.
2. The changed test checks the new behaviour at least as strictly as the old test checked the old behaviour.

A test that was already failing before the agent changed anything was most likely written for this task, so it
describes the behaviour the task wants. If the change touches such a test, or the test looks self-contradictory or
wrong, don't approve and don't try to fix it: escalate, so a human checks the test. Never approve removing or
rewriting a check just because it contradicts another check.

The reason comes from the agent and may be wrong. Judge it against the task text, not the other way round.
Reply with only a JSON object: {"approve": true or false, "escalate": true or false, "why": "one or two sentences"}"""


@dataclass
class TestChangeCheck:
    verdict: str  # "allow", "block" or "review"
    reason: str


def check_test_change(before: str, after: str) -> TestChangeCheck:
    """Sort a change to an existing test file by what fixed rules can decide about it."""
    diff = list(difflib.ndiff(before.splitlines(), after.splitlines()))
    removed = [line[2:] for line in diff if line.startswith("- ") and line[2:].strip()]
    added = [line[2:] for line in diff if line.startswith("+ ") and line[2:].strip()]

    if before.strip() and not after.strip():
        return TestChangeCheck("block", "it empties the test file")
    if any(_SKIP.search(line) for line in added) and not any(_SKIP.search(line) for line in removed):
        return TestChangeCheck("block", "it adds a skip or expected-failure marker")

    def names(lines):
        return {m.group(1) or m.group(2) for line in lines if (m := _TEST_DEF.match(line))}
    deleted = names(removed) - names(after.splitlines())
    if deleted:
        return TestChangeCheck("block", f"it deletes {', '.join(sorted(deleted))}")
    if not removed:
        return TestChangeCheck("allow", "it only adds lines")
    if sum(bool(_CHECK.search(line)) for line in removed) > sum(bool(_CHECK.search(line)) for line in added):
        return TestChangeCheck("block", "it removes an assertion without replacing it")
    return TestChangeCheck("review", "it changes or removes lines the test already had")


def unified_diff(path: str, before: str, after: str) -> str:
    return "\n".join(difflib.unified_diff(before.splitlines(), after.splitlines(), f"a/{path}", f"b/{path}", lineterm=""))


MAX_FAILING_NAMES = 30


def review_prompt(spec: str, diff: str, reason: str, failing_before: set[str] | None = None) -> str:
    names = sorted(failing_before or [])
    listed = "\n".join(f"- {n}" for n in names[:MAX_FAILING_NAMES]) or "None"
    if len(names) > MAX_FAILING_NAMES:
        listed += f"\n- and {len(names) - MAX_FAILING_NAMES} more"
    return (
        f"## Task\n{spec}\n\n## Tests already failing before the agent changed anything\n{listed}\n\n"
        f"## Proposed test change\n```diff\n{diff}\n```\n\n## The agent's reason\n{reason}"
    )


def parse_review(text: str) -> tuple[bool, str, bool]:
    """Anything but a clear approval counts as a refusal. Returns (approved, why, escalate)."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    try:
        verdict = json.loads(match.group(0)) if match else {}
    except json.JSONDecodeError:
        verdict = {}
    if not isinstance(verdict, dict):
        verdict = {}
    escalate = verdict.get("escalate") is True
    approved = verdict.get("approve") is True and not escalate
    why = str(verdict.get("why") or "The reviewer's reply couldn't be read, so the change was refused.")
    return approved, why, escalate
