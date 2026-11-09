"""What agents learned about a repo, kept for the next task on it.

After a task, the coder continues its own conversation (so its cache still holds what it read) and writes short
notes on the code it read: where things live, what a function does, what covers it. Each note is stored with a hash
of the code it describes, taken from the commit the task started on. A later task gets only notes whose code is
unchanged, ranked against its own text, so a stale note is dropped rather than trusted.

The comparison baseline keeps raw transcripts instead: what an earlier task did, tool call by tool call, and how it
ended (prior work found raw past trajectories beat compressed memory, see research_notes/exploration_memory_litcheck.md).
"""
import hashlib
import json
import re
import subprocess
from pathlib import Path

from core.keyword_locate import BM25, functions, tokens

NOTES_PROMPT = """The task is over; don't change anything. Teammates will work on other tasks in this repo later. Write
down what you learned about the code you read that would save them time: where things live, what functions and
classes do, how pieces connect, which tests cover what, and traps. Not this task's fix.

Reply without using tools, with lines only, in exactly this format:
- path/to/file.py::function_or_Class.method - one or two sentences
Use the path alone for a whole file. Name only code you read during this task. At most 15 lines."""

MAX_NOTES_PER_TASK = 15
MAX_MEMORY_CHARS = 2500
MAX_TRANSCRIPT_CHARS = 3000
_NOTE = re.compile(r"^\s*[-*]\s+`?([^\s`:]+)(?:::([\w.]+))?`?\s+[-–—:]\s+(.+)$", re.M)


def parse_notes(text: str) -> list[tuple[str, str, str]]:
    """(path, qualified name or "", note) for each line in the notes format."""
    return [(m.group(1), m.group(2) or "", m.group(3).strip()) for m in _NOTE.finditer(text)][:MAX_NOTES_PER_TASK]


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def code_hash(source: str | None, path: str, name: str) -> str | None:
    """Hash of the function or class the note is about, or of the whole file when it names none (or isn't Python)."""
    if source is None:
        return None
    if name and path.endswith(".py"):
        found = next((f for f in functions(path, source) if f["id"] == f"{path}::{name}"), None)
        if found:
            return _digest(found["text"])
    return _digest(source)


def source_at(repo_path: str, rev: str | None, path: str) -> str | None:
    """A file's text at a commit, or in the working tree when rev is None. None when it doesn't exist."""
    if rev is None:
        try:
            return (Path(repo_path) / path).read_text(errors="replace")
        except OSError:
            return None
    shown = subprocess.run(["git", "show", f"{rev}:{path}"], cwd=repo_path, capture_output=True, text=True,
                           errors="replace")
    return shown.stdout if shown.returncode == 0 else None


class RepoMemory:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        data = json.loads(self.path.read_text()) if self.path.exists() else {}
        self.notes: dict[str, dict] = data.get("notes", {})
        self.transcripts: list[dict] = data.get("transcripts", [])

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"notes": self.notes, "transcripts": self.transcripts}, indent=1))

    def add_notes(self, text: str, repo_path: str, rev: str, task: str) -> int:
        """Store notes on code as it was at rev (before the task changed it). A newer note on the same code replaces
        the older one. Notes on code that doesn't exist at rev are dropped. Returns how many were kept."""
        kept = 0
        for path, name, note in parse_notes(text):
            digest = code_hash(source_at(repo_path, rev, path), path, name)
            if digest:
                self.notes[f"{path}::{name}"] = {"note": note, "hash": digest, "task": task}
                kept += 1
        return kept

    def relevant(self, repo_path: str, task: str, max_chars: int = MAX_MEMORY_CHARS) -> tuple[str, dict]:
        """Notes whose code is unchanged in the working tree, best match to the task first, within max_chars.
        Returns (text for the prompt, counts of stored, stale and used notes)."""
        sources: dict[str, str | None] = {}
        valid = {}
        for key, entry in self.notes.items():
            path, name = key.split("::", 1)
            if path not in sources:
                sources[path] = source_at(repo_path, None, path)
            if code_hash(sources[path], path, name) == entry["hash"]:
                valid[key] = entry
        scores = BM25({k: tokens(k) * 2 + tokens(e["note"]) for k, e in valid.items()}).scores(tokens(task)) if valid else {}
        lines, used = [], 0
        for key in sorted(scores, key=lambda k: (-scores[k], k)):
            path, name = key.split("::", 1)
            line = f"- {path}{'::' + name if name else ''} - {valid[key]['note']}"
            if used + len(line) > max_chars:
                break
            lines.append(line)
            used += len(line) + 1
        counts = {"stored": len(self.notes), "stale": len(self.notes) - len(valid), "used": len(lines)}
        return "\n".join(lines), counts

    def add_transcript(self, task: str, actions: list[str], final_text: str, outcome: str):
        self.transcripts.append({"task": task, "actions": actions, "final_text": final_text, "outcome": outcome})

    def similar_transcript(self, task: str, max_chars: int = MAX_TRANSCRIPT_CHARS) -> str:
        """The earlier task most like this one, as it happened: its text, its tool calls, and how it ended."""
        if not self.transcripts:
            return ""
        scores = BM25({str(i): tokens(t["task"]) for i, t in enumerate(self.transcripts)}).scores(tokens(task))
        if not scores:
            return ""
        past = self.transcripts[int(max(scores, key=lambda i: (scores[i], int(i))))]
        text = (f"Its task:\n{past['task'][:800]}\n\nWhat it did, in order:\n" + "\n".join(past["actions"]) +
                f"\n\nHow it ended ({past['outcome']}):\n{past['final_text'][-800:]}")
        return text if len(text) <= max_chars else text[:max_chars] + "\n(cut)"


def memory_section(notes: str) -> str:
    return ("\n\n## Notes teammates left about this repo\nFrom earlier tasks, on code that hasn't changed since. They "
            f"may not apply to this task.\n{notes}") if notes else ""


def transcript_section(transcript: str) -> str:
    return ("\n\n## How a teammate handled the most similar earlier task in this repo\nThe code may have changed "
            f"since, and it may not apply to this task.\n\n{transcript}") if transcript else ""
