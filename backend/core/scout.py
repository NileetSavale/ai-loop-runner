"""A cheap model explores the repo first and writes notes, so the models that fix the bug don't pay to explore.

The scout can only read. Its notes are findings (where the code is, what the tests check, a guess at the cause),
never a fix. When a cheap attempt fails and a stronger model takes over, the handover passes those findings and,
optionally, what the attempt tried and what happened, stated as facts rather than as "this approach is wrong", so a
right idea that was badly carried out isn't ruled out. The failed diff itself is never passed on.
"""
import re

from core.agent import run_agent
from core.tools import RepoTools
from core.verifier import tail

SCOUT_SYSTEM_PROMPT = """You explore a code repository so that another engineer can fix a bug quickly. You can list,
search and read files, and nothing else: don't try to fix anything.

Find the code the task is about and the tests that cover it. Read only what you need. Then reply with notes in
exactly this format, and nothing after it:

## Relevant code
- path/to/file.py::function_or_Class.method - one line on what it does and why it matters here
## Relevant tests
- path/to/test_file.py::test_name - what it checks
## Likely cause
Two or three sentences. Say how sure you are.

Name only code you actually read. If you couldn't find something, say so rather than guess."""

MAX_NOTES_CHARS = 4000
MAX_TRIED_OUTPUT_CHARS = 1200
_NOTES_START = re.compile(r"^## Relevant code", re.M)


def scout_prompt(task: str) -> str:
    return f"The task the other engineer will work on:\n\n{task}"


def notes_from(text: str) -> str:
    """The notes section of the scout's reply, or the end of the reply if it ignored the format."""
    match = _NOTES_START.search(text)
    notes = text[match.start():] if match else text
    return tail(notes.strip(), MAX_NOTES_CHARS)


async def run_scout(task: str, repo_path: str, model: str, max_cost_usd: float, on_event=None,
                    max_listed_files: int = 100, effort: str | None = None):
    """Returns (notes, AgentResult)."""
    tools = RepoTools(repo_path, verify_command="", read_only=True, max_listed_files=max_listed_files)
    result = await run_agent(scout_prompt(task), model, tools=tools, max_cost_usd=max_cost_usd, on_event=on_event,
                             system_prompt=SCOUT_SYSTEM_PROMPT, effort=effort)
    return notes_from(result.final_text or result.raw_output), result


def tried_summary(changed: dict[str, list[str]], failing: list[str], broken: list[str], test_output: str,
                  own_words: str) -> str:
    """What an attempt did and what happened, as facts. changed: file -> functions it touched."""
    where = "\n".join(f"- {path}" + (f" ({', '.join(funcs)})" if funcs else "") for path, funcs in changed.items())
    parts = [f"It changed:\n{where or '- nothing'}"]
    if own_words.strip():
        parts.append(f"In its own words:\n{tail(own_words.strip(), 600)}")
    if broken:
        parts.append("Tests that passed before it and failed after: " + ", ".join(broken))
    others = [t for t in failing if t not in broken]
    if others:
        parts.append("Other tests still failing: " + ", ".join(others[:20]))
    if test_output.strip():
        parts.append(f"End of the test output:\n```\n{tail(test_output.strip(), MAX_TRIED_OUTPUT_CHARS)}\n```")
    return "\n\n".join(parts)


def handover(task: str, notes: str, tried: str | None = None, rejected: str | None = None) -> str:
    """The task as the next model sees it: the original text, then what is already known. rejected: the attempt
    passed the tests but a reviewer turned it down, for this reason."""
    text = f"{task}\n\n## Notes from a teammate who explored the repo\n{notes}"
    if tried and rejected:
        text += ("\n\n## A teammate's earlier attempt, which a reviewer rejected\nIt passed the tests, but the reviewer "
                 f"said: {rejected}\nIts changes have been undone. This is what it tried; whether the reviewer is right "
                 f"is for you to judge.\n\n{tried}")
    elif tried:
        text += ("\n\n## A teammate's earlier attempt, which didn't pass\nIts changes have been undone. This is what it "
                 "tried and what happened; whether the idea or only its execution was wrong is for you to judge.\n\n"
                 f"{tried}")
    return text
