import os
from .base import LLMProvider
from .anthropic import AnthropicProvider
from .openai import OpenAIProvider
from .gemini import GeminiProvider, vertex_enabled
from .mistral import MistralProvider


def _provider_for(model: str) -> str:
    if model.startswith("claude"):    return "anthropic"
    if model.startswith("gpt"):       return "openai"
    if model.startswith("gemini"):    return "google"
    if model.startswith("mistral"):   return "mistral"
    return "anthropic"


_CLASSES = {
    "anthropic": AnthropicProvider,
    "openai":    OpenAIProvider,
    "google":    GeminiProvider,
    "mistral":   MistralProvider,
}

# Our platform keys — used when user hasn't provided BYOK
_PLATFORM_KEYS = {
    "anthropic": os.getenv("ANTHROPIC_API_KEY", ""),
    "openai":    os.getenv("OPENAI_API_KEY", ""),
    "google":    os.getenv("GOOGLE_API_KEY", ""),
    "mistral":   os.getenv("MISTRAL_API_KEY", ""),
}


def get_provider(model: str, user_api_key: str | None = None) -> LLMProvider:
    """
    Return the right provider instance.
    user_api_key: decrypted BYOK key. If None, falls back to platform key.
    """
    provider_name = _provider_for(model)
    if provider_name == "google" and not user_api_key and vertex_enabled():
        return GeminiProvider(api_key="")  # Vertex AI, billed to the Google Cloud project
    key = user_api_key or _PLATFORM_KEYS.get(provider_name, "")
    if not key:
        raise ValueError(f"No API key available for provider '{provider_name}'. Add your key in Settings.")
    return _CLASSES[provider_name](api_key=key)
