"""The actions an agent can take in a repo.

The model only asks. This code decides. There is deliberately no shell tool: the model can run the session's
verify command and nothing else, and every write goes through the same rules as the one-shot agent.
"""
import os

from core.edits import FileEdit, apply_edits, describe_change, filter_edits, read_current, resolve_in_repo
from core.verifier import run_verify

MAX_READ_CHARS = 100_000
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
    _tool("read_file", "Read a text file from the repo.", path="Path relative to the repo root."),
    _tool("search_code", "Find lines containing some text, ignoring case. Not a regex.", query="Text to look for."),
    _tool(
        "edit_file",
        "Replace text in an existing file. old_text must appear exactly once, so include enough surrounding "
        "lines to make it unique. Prefer this to write_file for small changes.",
        path="Path relative to the repo root.", old_text="The exact text to replace.", new_text="The replacement.",
    ),
    _tool("write_file", "Create a file, or replace one completely.", path="Path relative to the repo root.", content="The full file contents."),
    _tool("run_tests", "Run the project's verify command and return its output."),
]
_REQUIRED = {t["name"]: t["input_schema"]["required"] for t in TOOL_SCHEMAS}


class ToolError(Exception):
    """A failure the model should see and can recover from."""


class RepoTools:
    def __init__(self, repo_path: str, verify_command: str, added_tests: set[str] | None = None):
        self.repo_path = repo_path
        self.verify_command = verify_command
        self.added_tests = set() if added_tests is None else added_tests
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
        try:
            return await getattr(self, f"_{name}")(**{k: args[k] for k in _REQUIRED[name]}), False
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

    async def _read_file(self, path: str) -> str:
        with open(resolve_in_repo(self.repo_path, path)) as f:
            content = f.read(MAX_READ_CHARS + 1)
        if len(content) > MAX_READ_CHARS:
            raise ToolError(f"{path} is over {MAX_READ_CHARS} characters, too large to read whole. Use search_code.")
        return content

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
            raise ToolError(rejected[0])
        before = read_current(self.repo_path, path)
        self.changed += apply_edits(allowed, self.repo_path)
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

    async def _run_tests(self) -> str:
        result = await run_verify(self.verify_command, self.repo_path)
        status = "PASSED" if result.passed else "FAILED"
        return f"{status}\n{result.output[-MAX_TEST_OUTPUT_CHARS:]}"
