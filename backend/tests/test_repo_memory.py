import subprocess

from core.repo_memory import RepoMemory, memory_section, parse_notes

A = "def unit(x):\n    return x * 2\n\n\ndef other():\n    return 1\n"


def _repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text(A)
    for args in (["init", "-q"], ["add", "-A"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "base"]):
        subprocess.run(["git", *args], cwd=repo, check=True)
    return repo, subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True).stdout.strip()


def test_notes_are_parsed_from_the_format_and_loose_variants():
    text = "Here:\n- a.py::unit - doubles a unit\n* `b/c.py` - config loading\n- not a note\n"
    assert parse_notes(text) == [("a.py", "unit", "doubles a unit"), ("b/c.py", "", "config loading")]


def test_notes_survive_changes_elsewhere_and_drop_when_their_code_changes(tmp_path):
    repo, base = _repo(tmp_path)
    memory = RepoMemory(tmp_path / "m.json")
    (repo / "a.py").write_text(A.replace("x * 2", "x * 3"))  # the task's own fix doesn't count: notes use base
    kept = memory.add_notes("- a.py::unit - doubles a unit value\n- a.py::other - returns one\n- gone.py - nothing",
                            str(repo), base, "bug-1")
    assert kept == 2
    memory.save()

    (repo / "a.py").write_text(A.replace("return 1", "return 2"))  # a later snapshot: other changed, unit didn't
    text, counts = RepoMemory(tmp_path / "m.json").relevant(str(repo), "unit values are wrong")
    assert text == "- a.py::unit - doubles a unit value"
    assert counts == {"stored": 2, "stale": 1, "used": 1}
    assert "Notes teammates left" in memory_section(text) and memory_section("") == ""


def test_transcripts_return_the_most_similar_earlier_task(tmp_path):
    memory = RepoMemory(tmp_path / "m.json")
    memory.add_transcript("Fix the admin login redirect", ["read_file admin.py"], "Changed redirect.", "passed")
    memory.add_transcript("Unit conversion rounds wrong", ["search_code round", "edit_file units.py"], "Fixed.", "failed")
    past = memory.similar_transcript("rounding in unit conversion")
    assert "Unit conversion" in past and "edit_file units.py" in past and "(failed)" in past
    assert RepoMemory(tmp_path / "empty.json").similar_transcript("x") == ""


def test_memory_arm_carries_notes_to_the_next_task_on_the_same_repo(tmp_path):
    import asyncio
    from unittest.mock import patch

    import benchmarks.run as bench
    from benchmarks.run import BenchTask, RunResult, run_memory_arm

    repo, _ = _repo(tmp_path)
    prompts = []

    async def fake_loop(task, repo_path, model, budget, result, **settings):
        prompts.append((task.prompt, settings.get("write_notes")))
        return {"notes": "- a.py::unit - doubles a unit value", "actions": ["read_file a.py"], "final_text": "done"}

    with patch.object(bench, "run_loop_arm", fake_loop), patch.object(bench, "MEMORY_DIR", tmp_path / "mem"):
        for name in ("django__django-1", "django__django-2"):
            result = RunResult(name, "swe-loop-lean-memory", "m", 1)
            asyncio.run(run_memory_arm(BenchTask(name, repo, "unit values wrong", "true"), repo, "m", 1.0, result))
    assert "Notes teammates left" not in prompts[0][0] and prompts[0][1]
    assert "- a.py::unit - doubles a unit value" in prompts[1][0]
    assert result.memory == {"stored": 1, "stale": 0, "used": 1, "kept": 1}
    assert (tmp_path / "mem" / "swe-loop-lean-memory-django__django.json").exists()
