import asyncio
from dataclasses import dataclass
import os
import re
import signal

MAX_TIMEOUT = int(os.getenv("MAX_VERIFY_TIMEOUT_SECONDS", "120"))

_SECRET_ENV = re.compile(r".*(_API_KEY|_SECRET|_TOKEN|_PASSWORD)|DATABASE_URL|REDIS_URL|VAULT_KEY", re.IGNORECASE)


# pytest -rA ("FAILED a.py::test_x - ...", or "ERROR a.py" when collecting fails), unittest/Django
# ("FAIL: test_x (mod.Class)"), and SymPy's bin/test ("____ sympy/a.py:test_x ____", down to two underscores
# around a long name)
# Vitest/Jest-style runners print " FAIL  web/a.test.ts > suite > test", or " FAIL  web/a.test.ts [ web/a.test.ts ]" for a
# file that won't load (the file path alone is then the name).
_FAILING_TEST = re.compile(
    r"^(?:(?:FAILED|ERROR) (\S+\.py\S*)|(?:FAIL|ERROR): (\w+ \([\w.]+\))|_{2,} (\S+\.py:\w+) _{2,}"
    r"|\s*FAIL\s+(\S+\.(?:test|spec)\.[cm]?[jt]sx?(?: > .+?)?)(?:\s+\[ .+ \])?\s*$)", re.M)
# Colour codes, which pytest prints when it runs under tox or with --color=yes
_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_PYTEST_SUMMARY = " short test summary info "


def failing_tests(output: str) -> set[str]:
    """Names of the failing tests in a test run's output. Empty when the format isn't recognised."""
    output = _ANSI.sub("", output)
    # pytest's own tests run pytest inside pytest, and the inner runs' FAILED lines show up in captured output.
    # The run's real summary is the last one.
    output = output[output.rfind(_PYTEST_SUMMARY):] if _PYTEST_SUMMARY in output else output
    return {next(g for g in m.groups() if g) for m in _FAILING_TEST.finditer(output)}


def tail(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return f"(the first {len(text) - limit} characters were cut)\n{text[-limit:]}"


MAX_SHORT_OUTPUT_CHARS = 2_000
MAX_SHORT_NAMES = 20
# Lines for tests that passed: pytest -rA's summary, and unittest/Django's verbose " ... ok"
_PASSED_LINE = re.compile(r"^PASSED |\.\.\. ok$|^test_\w+ ok\s")


def short_test_output(output: str, old_failures: set[str] = frozenset()) -> str:
    """A test run cut down to what an agent acts on: which tests fail, which of those failed before any change,
    and the end of the output without the lines for tests that passed."""
    failing = failing_tests(output)
    parts = []
    if failing:
        new, old = sorted(failing - old_failures), sorted(failing & old_failures)
        def listed(names):
            more = f"\n- and {len(names) - MAX_SHORT_NAMES} more" if len(names) > MAX_SHORT_NAMES else ""
            return "".join(f"\n- {n}" for n in names[:MAX_SHORT_NAMES]) + more
        if new:
            parts.append(f"Failing ({len(new)}):{listed(new)}")
        if old:
            parts.append(f"Also failing, but already failing before any change ({len(old)}):{listed(old)}")
    kept = "\n".join(line for line in _ANSI.sub("", output).splitlines() if not _PASSED_LINE.search(line))
    parts.append(f"End of the output:\n{tail(kept, MAX_SHORT_OUTPUT_CHARS)}")
    return "\n\n".join(parts)


@dataclass
class VerifyResult:
    passed: bool
    output: str
    exit_code: int


def _verify_env(cwd: str) -> dict[str, str]:
    """Environment for a verify command, which runs code the LLM just wrote.

    The repo root is importable, so `pytest` and `python -m pytest` behave the same.
    """
    # ponytail: hides secrets from the environment only. That code can still read files such as backend/.env
    # until loops are sandboxed (see plan.md).
    env = {k: v for k, v in os.environ.items() if not _SECRET_ENV.fullmatch(k)}
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [cwd, env.get("PYTHONPATH")]))
    env["PYTHONDONTWRITEBYTECODE"] = "1"  # otherwise .pyc files get committed, and can hide mutants
    return env


async def run_verify(command: str, cwd: str) -> VerifyResult:
    proc = await asyncio.create_subprocess_shell(
        command,
        cwd=cwd,
        env=_verify_env(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        start_new_session=True,  # own process group, so everything it spawned can be killed with it
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=MAX_TIMEOUT)
        return VerifyResult(
            passed=proc.returncode == 0,
            output=stdout.decode(errors="replace"),
            exit_code=proc.returncode,
        )
    except asyncio.TimeoutError:
        return VerifyResult(passed=False, output="TIMEOUT: verify command exceeded limit", exit_code=-1)
    finally:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass  # already gone
        await proc.wait()
