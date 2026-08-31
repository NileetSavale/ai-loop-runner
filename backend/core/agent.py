import re
from dataclasses import dataclass
from providers.base import LLMProvider, TokenCallback, calculate_cost
from providers.router import get_provider

SYSTEM_PROMPT = """You are a software engineer executing a specific coding task.
You will be given:
1. A task spec describing exactly what to implement
2. The current contents of relevant files

Your job: output the complete modified file contents for each file you change.
Format each file as:
<file path="relative/path/to/file.py">
...complete file content...
</file>

Rules:
- Output ONLY file blocks. No explanations unless asked.
- Always output the COMPLETE file, not just the diff.
- Do not create new files unless the spec requires it.
- The tests already exist — make them pass, do not modify them.
"""


@dataclass
class FileEdit:
    path: str
    content: str


@dataclass
class AgentResult:
    raw_output: str
    edits: list[FileEdit]
    input_tokens: int
    output_tokens: int
    cost_usd: float


def parse_file_blocks(text: str) -> list[FileEdit]:
    pattern = r'<file path="([^"]+)">(.*?)</file>'
    return [
        FileEdit(path=m.group(1), content=m.group(2).strip())
        for m in re.finditer(pattern, text, re.DOTALL)
    ]


async def run_agent(
    prompt: str,
    model: str,
    user_api_key: str | None = None,
    on_token: TokenCallback = None,
) -> AgentResult:
    provider = get_provider(model, user_api_key)
    result = await provider.complete(SYSTEM_PROMPT, prompt, model, on_token)
    cost = calculate_cost(model, result.input_tokens, result.output_tokens)
    return AgentResult(
        raw_output=result.text,
        edits=parse_file_blocks(result.text),
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        cost_usd=cost,
    )
