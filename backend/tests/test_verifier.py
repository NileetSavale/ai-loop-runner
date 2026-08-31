import sys, os, asyncio
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.verifier import run_verify


def run(coro):
    return asyncio.run(coro)


def test_passing_command(tmp_path):
    result = run(run_verify("exit 0", str(tmp_path)))
    assert result.passed is True
    assert result.exit_code == 0


def test_failing_command(tmp_path):
    result = run(run_verify("exit 1", str(tmp_path)))
    assert result.passed is False
    assert result.exit_code == 1


def test_output_captured(tmp_path):
    result = run(run_verify("echo hello_world", str(tmp_path)))
    assert "hello_world" in result.output


def test_stderr_captured(tmp_path):
    result = run(run_verify("echo err >&2", str(tmp_path)))
    assert "err" in result.output  # stderr merged into stdout


def test_timeout(tmp_path, monkeypatch):
    monkeypatch.setenv("MAX_VERIFY_TIMEOUT_SECONDS", "1")
    # reload to pick up env change
    import importlib, core.verifier as v
    importlib.reload(v)
    result = run(v.run_verify("sleep 10", str(tmp_path)))
    assert result.passed is False
    assert "TIMEOUT" in result.output
