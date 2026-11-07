"""The actions an agent can take in a repo.

The model only asks. This code decides. There is deliberately no shell tool: the model can run the session's
verify command and nothing else, and every write goes through the same rules as the one-shot agent.
"""
import os

from core.edits import FileEdit, apply_edits, describe_change, filter_edits, is_locked_path, is_test_path, read_current, resolve_in_repo
from core.test_changes import check_test_change, unified_diff
from core.verifier import run_verify, short_test_output

MAX_READ_LINES = 300
MAX_READ_CHARS = 12_000  # about 3,000 tokens, and every later turn in the attempt resends it
MAX_READABLE_BYTES = 10_000_000
MAX_LISTED_FILES = 500
MAX_SEARCH_HITS = 100
MAX_TEST_OUTPUT_CHARS = 8_000
SKIPPED_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".next", "dist", "build"}


def _tool(name: str, description: str, **params) -> dict:
    return {
        "name": name,
        "description": description,
        "input_schema": {
            "type": "object",
            "properties": {k: {"type": "string", "description": v} for k, v in params.items()},
            "required": list(params),
        },
    }


TOOL_SCHEMAS = [
    _tool("list_files", "List files in the repo, skipping dependency and build folders."),
    {
        "name": "read_file",
        "description": f"Read part of a text file from the repo: up to {MAX_READ_LINES} lines from start_line. "
                       "In a large file, use search_code to find the line first, then read around it.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path relative to the repo root."},
                "start_line": {"type": "integer", "description": "First line to read, counting from 1. Default 1."},
                "end_line": {"type": "integer", "description": "Last line to read. Optional."},
            },
            "required": ["path"],
        },
    },
    _tool("search_code", "Find lines containing some text, ignoring case. Not a regex.", query="Text to look for."),
    _tool(
        "edit_file",
        "Replace text in an existing file. old_text must appear exactly once, so include enough surrounding "
        "lines to make it unique. Prefer this to write_file for small changes.",
        path="Path relative to the repo root.", old_text="The exact text to replace.", new_text="The replacement.",
    ),
    _tool("write_file", "Create a file, or replace one completely.", path="Path relative to the repo root.", content="The full file contents."),
    _tool("run_tests", "Run the project's verify command and return its output."),
    _tool(
        "change_existing_test",
        "Change what an existing test expects, only when the task itself requires that behaviour to change. Works "
        "like edit_file. Adding lines is allowed; changing or removing them goes to a reviewer who sees the task, "
        "the change and your reason. Skipping, deleting or emptying tests is always refused.",
        path="Path of the existing test file.", old_text="The exact text to replace.", new_text="The replacement.",
        reason="Why the task requires this change. Quote the part of the task that asks for the new behaviour.",
    ),
]
_REQUIRED = {t["name"]: t["input_schema"]["required"] for t in TOOL_SCHEMAS}
_OPTIONAL_LINES = {"read_file": ("start_line", "end_line")}


class ToolError(Exception):
    """A failure the model should see and can recover from."""


class RepoTools:
    def __init__(self, repo_path: str, verify_command: str, added_tests: set[str] | None = None, review_test_change=None,
                 short_output: bool = False, old_failures: set[str] = frozenset(), review_changes=None):
        self.repo_path = repo_path
        # async (changed paths) -> problems. A security reviewer that sees the changes each time the tests run.
        self.review_changes = review_changes
        # Return failing names and the end of the output instead of up to MAX_TEST_OUTPUT_CHARS of it
        self.short_output = short_output
        self.old_failures = old_failures
        self.verify_command = verify_command
        self.added_tests = set() if added_tests is None else added_tests
        # async (path, diff, reason) -> (approved, why). None means existing tests stay read-only.
        self.review_test_change = review_test_change
        self.changed: list[str] = []
        self.changes: list[dict] = []  # descriptions of writes not yet reported to the website

    async def run(self, name: str, args: dict) -> tuple[str, bool]:
        """Returns (result, is_error). Errors go back to the model rather than ending the run."""
        if name not in _REQUIRED:
            return f"Unknown tool: {name}", True
        # Model output is untrusted, including its arguments
        bad = [k for k in _REQUIRED[name] if not isinstance(args.get(k), str)]
        if bad:
            return f"{name} needs text for: {', '.join(bad)}", True
        lines = {k: args[k] for k in _OPTIONAL_LINES.get(name, ()) if args.get(k) is not None}
        # bool is an int in Python, and a model could send true
        if any(type(v) is not int or v < 1 for v in lines.values()):
            return f"{name} needs whole numbers of 1 or more for: {', '.join(lines)}", True
        try:
            return await getattr(self, f"_{name}")(**{k: args[k] for k in _REQUIRED[name]}, **lines), False
        except ToolError as e:
            return str(e), True
        except ValueError as e:  # a path outside the repo
            return str(e), True
        except (OSError, UnicodeDecodeError) as e:
            return f"{name} failed: {e}", True

    async def _list_files(self) -> str:
        root = os.path.realpath(self.repo_path)
        found = []
        for folder, dirs, files in os.walk(root):
            dirs[:] = sorted(d for d in dirs if d not in SKIPPED_DIRS)
            found += [os.path.relpath(os.path.join(folder, f), root) for f in sorted(files)]
        note = f"\n(showing {MAX_LISTED_FILES} of {len(found)} files)" if len(found) > MAX_LISTED_FILES else ""
        return "\n".join(found[:MAX_LISTED_FILES]) + note

    async def _read_file(self, path: str, start_line: int = 1, end_line: int | None = None) -> str:
        full_path = resolve_in_repo(self.repo_path, path)
        if os.path.getsize(full_path) > MAX_READABLE_BYTES:
            raise ToolError(f"{path} is over {MAX_READABLE_BYTES} bytes, too large to read. Use search_code.")
        if end_line is not None and end_line < start_line:
            raise ToolError(f"end_line ({end_line}) is before start_line ({start_line}).")
        with open(full_path) as f:
            lines = f.readlines()
        if not lines and start_line == 1:
            return ""
        if start_line > len(lines):
            raise ToolError(f"{path} has {len(lines)} lines, so there is no line {start_line}.")

        last = min(end_line or len(lines), len(lines), start_line + MAX_READ_LINES - 1)
        content, shown = "", start_line - 1
        for line in lines[start_line - 1:last]:
            if content and len(content) + len(line) > MAX_READ_CHARS:
                break
            content += line
            shown += 1
        if len(content) > MAX_READ_CHARS:  # a single huge line, such as minified code
            return f"{content[:MAX_READ_CHARS]}\n(line {start_line} of {path} was cut at {MAX_READ_CHARS} characters. Use search_code.)"
        if start_line == 1 and shown == len(lines):
            return content
        ending = "" if content.endswith("\n") else "\n"
        return f"{content}{ending}(showing lines {start_line}-{shown} of {len(lines)}. Set start_line to read further.)"

    async def _search_code(self, query: str) -> str:
        # ponytail: plain text, because a model-written regex can hang the server. Add regex with a timeout if needed.
        root = os.path.realpath(self.repo_path)
        needle, hits = query.lower(), []
        for folder, dirs, files in os.walk(root):
            dirs[:] = sorted(d for d in dirs if d not in SKIPPED_DIRS)
            for name in sorted(files):
                path = os.path.join(folder, name)
                try:
                    with open(path) as f:
                        for number, line in enumerate(f, 1):
                            if needle in line.lower():
                                hits.append(f"{os.path.relpath(path, root)}:{number}: {line.strip()[:200]}")
                                if len(hits) >= MAX_SEARCH_HITS:
                                    return "\n".join(hits) + f"\n(stopped at {MAX_SEARCH_HITS} matches)"
                except (OSError, UnicodeDecodeError):
                    continue  # binary or unreadable
        return "\n".join(hits) or "No matches."

    def _write(self, path: str, content: str) -> str:
        allowed, rejected = filter_edits([FileEdit(path, content)], self.repo_path, self.added_tests)
        if rejected:
            hint = " If the task requires changing what this test expects, use change_existing_test." if (
                self.review_test_change and "existing tests are read-only" in rejected[0]) else ""
            raise ToolError(rejected[0] + hint)
        return self._apply(path, content)

    def _apply(self, path: str, content: str) -> str:
        before = read_current(self.repo_path, path)
        self.changed += apply_edits([FileEdit(path, content)], self.repo_path)
        self.changes.append(describe_change(path, before, content))
        return f"Wrote {path}."

    async def _write_file(self, path: str, content: str) -> str:
        return self._write(path, content)

    async def _edit_file(self, path: str, old_text: str, new_text: str) -> str:
        with open(resolve_in_repo(self.repo_path, path)) as f:
            content = f.read()
        count = content.count(old_text) if old_text else 0
        if count != 1:
            raise ToolError(f"old_text must appear exactly once in {path}, but it appears {count} times. Read the file and try again.")
        return self._write(path, content.replace(old_text, new_text))

    async def _change_existing_test(self, path: str, old_text: str, new_text: str, reason: str) -> str:
        if not self.review_test_change:
            raise ToolError("Changing existing tests isn't enabled for this task. Existing tests are read-only.")
        full_path = resolve_in_repo(self.repo_path, path)
        rel = os.path.relpath(full_path, os.path.realpath(self.repo_path))
        if is_locked_path(rel):
            raise ToolError(f"{path} is test config, which is always read-only.")
        if not is_test_path(rel) or not os.path.exists(full_path):
            raise ToolError(f"{path} isn't an existing test file. Use edit_file or write_file.")
        with open(full_path) as f:
            before = f.read()
        count = before.count(old_text) if old_text else 0
        if count != 1:
            raise ToolError(f"old_text must appear exactly once in {path}, but it appears {count} times. Read the file and try again.")
        after = before.replace(old_text, new_text)
        check = check_test_change(before, after)
        if check.verdict == "block":
            raise ToolError(f"Refused: {check.reason}. Skipping, deleting or emptying tests is never allowed.")
        if check.verdict == "review":
            approved, why = await self.review_test_change(rel, unified_diff(rel, before, after), reason)
            if not approved:
                raise ToolError(f"The reviewer refused this test change: {why}")
            return self._apply(rel, after) + f" The reviewer approved it: {why}"
        return self._apply(rel, after)

    async def _run_tests(self) -> str:
        result = await run_verify(self.verify_command, self.repo_path)
        status = "PASSED" if result.passed else "FAILED"
        if self.short_output:
            report = f"{status}\n{short_test_output(result.output, self.old_failures)}"
        else:
            report = f"{status}\n{result.output[-MAX_TEST_OUTPUT_CHARS:]}"
        if self.review_changes and self.changed:
            problems = await self.review_changes(list(self.changed))
            if problems:
                report += "\n\nSECURITY REVIEW: your changes were sent back. Fix these before you finish:\n" + "\n".join(
                    f"- {p}" for p in problems)
        return report
