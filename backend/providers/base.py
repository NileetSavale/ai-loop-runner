from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Awaitable

TokenCallback = Callable[[str], Awaitable[None]] | None

MAX_OUTPUT_TOKENS = 16000  # the lowest ceiling among supported models is gpt-4o at 16384


@dataclass
class LLMResult:
    text: str
    input_tokens: int
    output_tokens: int
    truncated: bool = False  # the reply hit MAX_OUTPUT_TOKENS and was cut off
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict


@dataclass
class ToolTurn:
    """One model turn in an agent loop."""
    text: str
    tool_calls: list[ToolCall]
    stop_reason: str | None
    assistant_message: dict  # goes back into the conversation exactly as received
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


class LLMProvider(ABC):
    supports_tools = False

    def __init__(self, api_key: str):
        self.api_key = api_key

    async def complete_with_tools(
        self, system: str, messages: list[dict], tools: list[dict], model: str, on_token: TokenCallback = None,
        effort: str | None = None,
    ) -> ToolTurn:
        """effort: as in complete. Callers pass it only when set, so providers without it keep working."""
        raise NotImplementedError

    def tool_results_message(self, results: list[dict]) -> dict:
        """results: [{"id", "content", "is_error"}]. All of a turn's results go back in one message."""
        raise NotImplementedError

    @abstractmethod
    async def complete(
        self,
        system: str,
        prompt: str,
        model: str,
        on_token: TokenCallback = None,
        effort: str | None = None,
    ) -> LLMResult:
        """effort: how hard the model thinks ("low" to "max"), where the provider supports it. None keeps its default."""


# Pricing per million tokens — update as providers change rates
PRICING: dict[str, dict[str, float]] = {
    # Anthropic
    "claude-opus-5-5":          {"in": 4.00,   "out": 20.00},
    "claude-sonnet-5-5":        {"in": 2.00,   "out": 10.00},
    "claude-haiku-5-5":         {"in": 0.10,   "out": 0.50},  # ponytail: $0.50/$2.50 over 100K prompt tokens, not modelled
    "claude-sonnet-4-6":        {"in": 3.00,   "out": 15.00},
    "claude-opus-4-8":          {"in": 5.00,   "out": 25.00},
    "claude-haiku-4-5-20251001":{"in": 1.00,   "out": 5.00},
    # OpenAI
    "gpt-4o":                   {"in": 2.50,   "out": 10.00},
    "gpt-4o-mini":              {"in": 0.15,   "out": 0.60},
    # Google
    "gemini-1.5-pro":           {"in": 1.25,   "out": 5.00},
    "gemini-1.5-flash":         {"in": 0.075,  "out": 0.30},
    # Mistral
    "mistral-large-latest":     {"in": 2.00,   "out": 6.00},
    "mistral-small-latest":     {"in": 0.20,   "out": 0.60},
}

SUPPORTED_MODELS = {
    "anthropic": [
        {"id": "claude-opus-5-5",           "name": "Claude Opus 5.5"},
        {"id": "claude-sonnet-5-5",         "name": "Claude Sonnet 5.5"},
        {"id": "claude-haiku-5-5",          "name": "Claude Haiku 5.5"},
        {"id": "claude-sonnet-4-6",         "name": "Claude Sonnet 4.6"},
        {"id": "claude-opus-4-8",           "name": "Claude Opus 4.8"},
        {"id": "claude-haiku-4-5-20251001", "name": "Claude Haiku 4.5"},
    ],
    "openai": [
        {"id": "gpt-4o",      "name": "GPT-4o"},
        {"id": "gpt-4o-mini", "name": "GPT-4o Mini"},
    ],
    "google": [
        {"id": "gemini-1.5-pro",   "name": "Gemini 1.5 Pro"},
        {"id": "gemini-1.5-flash", "name": "Gemini 1.5 Flash"},
    ],
    "mistral": [
        {"id": "mistral-large-latest", "name": "Mistral Large"},
        {"id": "mistral-small-latest", "name": "Mistral Small"},
    ],
}


def calculate_cost(
    model: str, input_tokens: int, output_tokens: int, cache_read_tokens: int = 0, cache_write_tokens: int = 0
) -> float:
    p = PRICING.get(model, {"in": 3.00, "out": 15.00})
    # Cached prompt tokens are reported separately from input_tokens: reads cost about 0.1x, writes about 1.25x
    prompt = input_tokens + cache_read_tokens * 0.1 + cache_write_tokens * 1.25
    return prompt / 1_000_000 * p["in"] + output_tokens / 1_000_000 * p["out"]
