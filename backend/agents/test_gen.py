"""
Test Generation Agent — the core product differentiator.

Takes a product description + repo context → produces a failing test suite
that serves as the executable spec the loop runner will implement.
"""
import json
import os
import re
from dataclasses import dataclass

from core.agent import resolve_in_repo
from providers.router import get_provider
from providers.base import TokenCallback, calculate_cost

SYSTEM_PROMPT = """You are a senior test engineer who specialises in test-driven development.
Your output IS the specification. The coding agent reads only your tests — nothing else.

## Your job
Given a product description and existing project files, write a complete test suite
that defines exactly what must be implemented. The tests must FAIL before any
implementation exists and PASS only when the feature is fully correct.

## Rules
1. Tests define the contract — names, parameters, return types, error behaviour.
2. NEVER mock the core feature being tested. Mock only external I/O (DB, HTTP, time).
3. Cover every case: happy path, edge cases, invalid inputs, boundary values, error states.
4. Use realistic data — not "foo", "bar", "test123".
5. Tests must be self-documenting. `test_rate_limiter_blocks_after_5_requests` not `test_case_3`.
6. Do not write `pass` or placeholder bodies. Every test must make a real assertion.
7. Do not import the implementation — use the correct import path based on the project structure.
8. Match the existing project's test style if test files are provided as context.

## Framework selection (use what fits, don't force another)
| Stack | Framework | Notes |
|---|---|---|
| Python | pytest | Use fixtures, parametrize for data-driven cases |
| TypeScript / JavaScript | Vitest (prefer) or Jest | Use describe/it blocks |
| Go | standard `testing` package | Table-driven tests |
| Rust | `#[cfg(test)]` modules | inline in lib.rs or separate tests/ |
| Ruby | RSpec | describe/context/it |
| Java / Kotlin | JUnit 5 | |

## Output format — STRICT
Output ONLY the blocks below, nothing else.

One block per test file:
<file path="tests/test_feature.py">
...complete file, ready to run...
</file>

Then one metadata block:
<meta>
{
  "verify_command": "pytest tests/ -v",
  "implementation_spec": "2-4 sentence plain-English spec for the coding agent. Name every class, method, and behaviour the agent must implement."
}
</meta>

## What makes a good implementation_spec
Bad:  "Implement the feature as described."
Good: "Implement a `RateLimiter(max_requests, window_seconds)` class in `src/rate_limiter.py`.
       `is_allowed(client_id) -> bool` uses a per-client sliding window deque.
       `retry_after(client_id) -> int` returns 0 if allowed, else seconds until oldest entry expires.
       Use `collections.deque` and `time.time()`. No external dependencies."
"""


@dataclass
class TestGenResult:
    test_files: list[dict]        # [{"path": str, "content": str}]
    verify_command: str
    implementation_spec: str
    raw_output: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    truncated: bool = False


# ── stack detection ───────────────────────────────────────────────────────────

_STACK_MARKERS = {
    "python":     ["requirements.txt", "pyproject.toml", "setup.py", "Pipfile"],
    "typescript": ["tsconfig.json", "package.json"],
    "javascript": ["package.json"],
    "go":         ["go.mod"],
    "rust":       ["Cargo.toml"],
    "ruby":       ["Gemfile"],
    "java":       ["pom.xml", "build.gradle"],
}


def detect_stack(repo_path: str) -> str:
    for stack, markers in _STACK_MARKERS.items():
        if any(os.path.exists(os.path.join(repo_path, m)) for m in markers):
            # distinguish TS from plain JS
            if stack == "javascript":
                pkg = os.path.join(repo_path, "package.json")
                try:
                    data = json.loads(open(pkg).read())
                    deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
                    if "typescript" in deps or os.path.exists(os.path.join(repo_path, "tsconfig.json")):
                        return "typescript"
                except Exception:
                    pass
            return stack
    return "python"  # safe default


def read_context(repo_path: str, context_files: list[str]) -> str:
    parts = []
    for rel in context_files:
        try:
            content = open(resolve_in_repo(repo_path, rel)).read()
            parts.append(f"### {rel}\n```\n{content}\n```")
        except FileNotFoundError:
            parts.append(f"### {rel}\n(not found)")
        except ValueError:
            parts.append(f"### {rel}\n(outside the repo, not read)")
    return "\n\n".join(parts)


def _find_existing_tests(repo_path: str) -> str:
    """Include up to 2 existing test files as style examples."""
    examples = []
    for root, _, files in os.walk(repo_path):
        for f in files:
            if f.startswith("test_") or f.endswith("_test.py") or f.endswith(".test.ts"):
                rel = os.path.relpath(os.path.join(root, f), repo_path)
                try:
                    content = open(os.path.join(root, f)).read()
                    examples.append(f"### {rel} (existing test — match this style)\n```\n{content[:2000]}\n```")
                except Exception:
                    pass
                if len(examples) >= 2:
                    return "\n\n".join(examples)
    return ""


# ── output parsers ────────────────────────────────────────────────────────────

def _parse_files(text: str) -> list[dict]:
    return [
        {"path": m.group(1), "content": m.group(2).strip()}
        for m in re.finditer(r'<file path="([^"]+)">(.*?)</file>', text, re.DOTALL)
    ]


def _parse_meta(text: str) -> dict:
    m = re.search(r"<meta>\s*(\{.*?\})\s*</meta>", text, re.DOTALL)
    if not m:
        return {"verify_command": "pytest tests/ -v", "implementation_spec": ""}
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return {"verify_command": "pytest tests/ -v", "implementation_spec": ""}


# ── main entry point ──────────────────────────────────────────────────────────

async def generate_tests(
    description: str,
    repo_path: str,
    tech_stack: str | None,
    context_files: list[str],
    model: str,
    user_api_key: str | None = None,
    on_token: TokenCallback = None,
) -> TestGenResult:
    stack = tech_stack or detect_stack(repo_path)
    file_context = read_context(repo_path, context_files)
    style_examples = _find_existing_tests(repo_path)

    prompt = f"""## Tech stack
{stack}

## Product description
{description}

{f"## Existing project files (for context){chr(10)}{file_context}" if file_context else ""}

{f"## Existing tests (match this style){chr(10)}{style_examples}" if style_examples else ""}

Generate the complete test suite now.
"""

    provider = get_provider(model, user_api_key)
    result = await provider.complete(SYSTEM_PROMPT, prompt, model, on_token)

    test_files = _parse_files(result.text)
    meta = _parse_meta(result.text)

    return TestGenResult(
        test_files=test_files,
        verify_command=meta.get("verify_command", "pytest tests/ -v"),
        implementation_spec=meta.get("implementation_spec", description),
        raw_output=result.text,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        cost_usd=calculate_cost(model, result.input_tokens, result.output_tokens),
        truncated=result.truncated,
    )


async def apply_tests(repo_path: str, test_files: list[dict]):
    """Write the generated test files to disk."""
    resolved = [(resolve_in_repo(repo_path, f["path"]), f["content"]) for f in test_files]  # all or nothing
    for abs_path, content in resolved:
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        open(abs_path, "w").write(content)
