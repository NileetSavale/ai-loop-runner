import sys, os, asyncio
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.verifier import failing_tests, run_verify


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


def test_verify_leaves_no_bytecode_to_commit(tmp_path):
    (tmp_path / "m.py").write_text("X = 1")
    assert run(run_verify(f"{sys.executable} -c 'import m'", str(tmp_path))).passed
    assert not (tmp_path / "__pycache__").exists()


def test_reads_failing_test_names_from_pytest_django_and_sympy_output():
    pytest_out = "FAILED a/test_x.py::test_one - AssertionError\nERROR a/test_y.py - ImportError\nPASSED a/test_x.py::test_two\n"
    django_out = "FAIL: test_one (app.tests.Case)\n----\nERROR: test_two (app.tests.Case.test_two)\n"
    sympy_out = "____ sympy/core/tests/test_basic.py:test_one ____\n______ xpassed tests ______\n"
    assert failing_tests(pytest_out) == {"a/test_x.py::test_one", "a/test_y.py"}
    assert failing_tests(django_out) == {"test_one (app.tests.Case)", "test_two (app.tests.Case.test_two)"}
    assert failing_tests(sympy_out) == {"sympy/core/tests/test_basic.py:test_one"}
    assert failing_tests("1 failed in 0.01s") == set()


def test_failing_tests_are_read_through_colour_codes_and_short_sympy_rules():
    coloured = "\x1b[31mFAILED\x1b[0m sklearn/a.py::\x1b[1mtest_roc\x1b[0m - AssertionError\n"
    sympy_long = "__ sympy/codegen/tests/test_rewriting.py:test_create_expand_pow_optimization ___\n"
    assert failing_tests(coloured) == {"sklearn/a.py::test_roc"}
    assert failing_tests(sympy_long) == {"sympy/codegen/tests/test_rewriting.py:test_create_expand_pow_optimization"}
