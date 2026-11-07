from mistralai.client import Mistral
from .base import LLMProvider, LLMResult, MAX_OUTPUT_TOKENS, TokenCallback


class MistralProvider(LLMProvider):
    async def complete(self, system: str, prompt: str, model: str, on_token: TokenCallback = None,
                       effort: str | None = None) -> LLMResult:
        client = Mistral(api_key=self.api_key)
        full_text = ""
        input_tokens = output_tokens = 0
        truncated = False

        stream = await client.chat.stream_async(
            model=model,
            max_tokens=MAX_OUTPUT_TOKENS,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        )
        async with stream:
            async for chunk in stream:
                choice = chunk.data.choices[0] if chunk.data.choices else None
                token = choice.delta.content or "" if choice else ""
                full_text += token
                if on_token and token:
                    await on_token(token)
                if choice and choice.finish_reason == "length":
                    truncated = True
                if chunk.data.usage:
                    input_tokens = chunk.data.usage.prompt_tokens or 0
                    output_tokens = chunk.data.usage.completion_tokens or 0

        return LLMResult(text=full_text, input_tokens=input_tokens, output_tokens=output_tokens, truncated=truncated)
