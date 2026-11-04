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


class LLMProvider(ABC):
    def __init__(self, api_key: str):
        self.api_key = api_key

    @abstractmethod
    async def complete(
        self,
        system: str,
        prompt: str,
        model: str,
        on_token: TokenCallback = None,
    ) -> LLMResult: ...


# Pricing per million tokens — update as providers change rates
PRICING: dict[str, dict[str, float]] = {
    # Anthropic
    "claude-sonnet-4-6":        {"in": 3.00,   "out": 15.00},
    "claude-opus-4-8":          {"in": 15.00,  "out": 75.00},
    "claude-haiku-4-5-20251001":{"in": 0.80,   "out": 4.00},
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


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    p = PRICING.get(model, {"in": 3.00, "out": 15.00})
    return input_tokens / 1_000_000 * p["in"] + output_tokens / 1_000_000 * p["out"]
