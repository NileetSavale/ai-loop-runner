import asyncio
from dataclasses import dataclass
import os
import signal

MAX_TIMEOUT = int(os.getenv("MAX_VERIFY_TIMEOUT_SECONDS", "120"))


@dataclass
class VerifyResult:
    passed: bool
    output: str
    exit_code: int


async def run_verify(command: str, cwd: str) -> VerifyResult:
    proc = await asyncio.create_subprocess_shell(
        command,
        cwd=cwd,
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
