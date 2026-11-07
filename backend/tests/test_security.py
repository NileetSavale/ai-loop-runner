"""Tests for the security agents' prompts and replies."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.edits import is_test_path
from core.security import AuditCache, files_to_audit, findings_for, findings_guide, parse_findings, parse_verdict


def test_the_auditor_reads_the_task_files_and_what_they_import():
    focus = [{"path": "app/main.py"}]
    edges = [{"from": "app/main.py", "to": "app/auth.py"}, {"from": "tests/test_x.py", "to": "app/main.py"},
             {"from": "app/other.py", "to": "app/db.py"}]
    assert files_to_audit(focus, edges, is_test_path) == ["app/main.py", "app/auth.py"]


def test_findings_are_read_from_json_and_listed_for_the_coder():
    text = 'Here: {"findings": [{"file": "app/main.py", "problem": "SQL built with an f-string.", "fix": "Use ?", "severity": "high"}]}'
    findings = parse_findings(text)
    assert findings[0]["file"] == "app/main.py"
    assert "[high] app/main.py: SQL built with an f-string. Fix: Use ?" in findings_guide(findings)
    assert parse_findings("no json") == [] and findings_guide([]) == ""


def test_the_pair_sends_work_back_only_with_a_reason():
    assert parse_verdict('{"approve": false, "problems": ["search still uses an f-string"]}') == (
        False, ["search still uses an f-string"])
    assert parse_verdict('{"approve": true, "problems": []}')[0]
    assert parse_verdict("garbled")[0]  # an unreadable reply mustn't stall the coder
    assert parse_verdict('{"approve": false, "problems": []}')[0]


def test_run_tests_shows_the_coder_what_the_security_pair_sent_back(tmp_path):
    import asyncio
    from core.tools import RepoTools

    async def review(changed):
        return [f"{changed[0]} reads a note without checking its owner"]

    tools = RepoTools(str(tmp_path), "true", review_changes=review)
    tools.changed = ["app/main.py"]
    report, is_error = asyncio.run(tools.run("run_tests", {}))
    assert report.startswith("PASSED") and not is_error
    assert "SECURITY REVIEW: your changes were sent back" in report and "app/main.py reads a note" in report
    tools.changed = []
    assert "SECURITY REVIEW" not in asyncio.run(tools.run("run_tests", {}))[0]  # nothing changed, nothing to review


def test_cached_findings_last_only_while_the_file_and_the_auditor_are_unchanged(tmp_path):
    path = str(tmp_path / "audit.json")
    cache = AuditCache(path, "model-a")
    cache.put("app/main.py", "v1", [{"file": "app/main.py", "problem": "SQL injection"}])
    cache.save()
    assert AuditCache(path, "model-a").get("app/main.py", "v1")[0]["problem"] == "SQL injection"
    assert AuditCache(path, "model-a").get("app/main.py", "v2") is None
    assert AuditCache(path, "model-b").get("app/main.py", "v1") is None


def test_findings_are_matched_to_files_by_path_suffix():
    findings = [{"file": "main.py", "problem": "x"}, {"file": "app/db.py", "problem": "y"}, {"file": "", "problem": "z"}]
    assert [f["problem"] for f in findings_for("app/main.py", findings)] == ["x"]
    assert [f["problem"] for f in findings_for("db.py", findings)] == ["y"]
