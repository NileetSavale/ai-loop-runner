"""Turn this project's Claude Code sessions into readable Markdown, one file per session, in chat_logs/.

    python3 scripts/export_chats.py

Keeps what was said: your messages and Claude's replies, plus a one-line note per tool call. Tool output is left
out, since it's what makes the raw files megabytes long. Rerunning rewrites the files, so it's safe to repeat.
"""
import json
from pathlib import Path

PROJECT = Path.home() / ".claude-team/projects/-Users-nileetsavale-Desktop-loop-runner"
OUT = Path(__file__).resolve().parents[1] / "chat_logs"


def text_of(content) -> tuple[str, list[str]]:
    if isinstance(content, str):
        return content, []
    texts, tools = [], []
    for block in content or []:
        if block.get("type") == "text":
            texts.append(block["text"])
        elif block.get("type") == "tool_use":
            args = block.get("input", {})
            hint = args.get("description") or args.get("file_path") or args.get("command") or ""
            tools.append(f"{block['name']}: {str(hint).splitlines()[0][:150] if hint else ''}")
    return "\n\n".join(texts), tools


def export(path: Path) -> Path | None:
    lines = []
    started = None
    for raw in path.read_text().splitlines():
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if entry.get("isSidechain") or entry.get("type") not in ("user", "assistant"):
            continue
        started = started or entry.get("timestamp", "")
        text, tools = text_of(entry.get("message", {}).get("content"))
        if entry["type"] == "user":
            if text.strip() and not text.lstrip().startswith("<"):  # skip system reminders and tool results
                lines.append(f"## You · {entry.get('timestamp', '')[:16].replace('T', ' ')}\n\n{text.strip()}\n")
        else:
            if text.strip():
                lines.append(f"### Claude\n\n{text.strip()}\n")
            lines.extend(f"> tool · {t}" for t in tools)
    if not lines:
        return None
    out = OUT / f"{(started or '0000-00-00')[:10]}_{path.stem[:8]}.md"
    out.write_text(f"# Session {path.stem}\n\n" + "\n".join(lines) + "\n")
    return out


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    for session in sorted(PROJECT.glob("*.jsonl")):
        written = export(session)
        if written:
            print(f"{written.name}: {written.stat().st_size // 1024} KB")
