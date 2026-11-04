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


def test_secrets_hidden_from_code_under_test(tmp_path, monkeypatch):
    for name in ["ANTHROPIC_API_KEY", "SUPABASE_JWT_SECRET", "VAULT_KEY", "DATABASE_URL", "GH_TOKEN"]:
        monkeypatch.setenv(name, "hunter2")
    monkeypatch.setenv("MY_ORDINARY_SETTING", "visible")
    result = run(run_verify("env", str(tmp_path)))
    assert "hunter2" not in result.output
    assert "MY_ORDINARY_SETTING=visible" in result.output


def test_repo_root_is_importable_and_existing_pythonpath_kept(tmp_path, monkeypatch):
    monkeypatch.setenv("PYTHONPATH", "/already/here")
    (tmp_path / "mymodule.py").write_text("VALUE = 42")
    (tmp_path / "sub").mkdir()
    script = tmp_path / "sub" / "check.py"
    script.write_text("import sys, mymodule\nassert mymodule.VALUE == 42\nassert '/already/here' in sys.path\n")
    result = run(run_verify(f"{sys.executable} sub/check.py", str(tmp_path)))
    assert result.passed, result.output
