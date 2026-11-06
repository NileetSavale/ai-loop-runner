import asyncio
from dataclasses import dataclass
import os
import re
import signal

MAX_TIMEOUT = int(os.getenv("MAX_VERIFY_TIMEOUT_SECONDS", "120"))

_SECRET_ENV = re.compile(r".*(_API_KEY|_SECRET|_TOKEN|_PASSWORD)|DATABASE_URL|REDIS_URL|VAULT_KEY", re.IGNORECASE)


# pytest -rA ("FAILED a.py::test_x - ...", or "ERROR a.py" when collecting fails), unittest/Django
# ("FAIL: test_x (mod.Class)"), and SymPy's bin/test ("____ sympy/a.py:test_x ____")
_FAILING_TEST = re.compile(r"^(?:(?:FAILED|ERROR) (\S+\.py\S*)|(?:FAIL|ERROR): (\w+ \([\w.]+\))|_{3,} (\S+\.py:\w+) _{3,})", re.M)


def failing_tests(output: str) -> set[str]:
    """Names of the failing tests in a test run's output. Empty when the format isn't recognised."""
    return {next(g for g in m.groups() if g) for m in _FAILING_TEST.finditer(output)}


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
