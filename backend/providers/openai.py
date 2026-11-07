from openai import AsyncOpenAI
from .base import LLMProvider, LLMResult, MAX_OUTPUT_TOKENS, TokenCallback


class OpenAIProvider(LLMProvider):
    async def complete(self, system: str, prompt: str, model: str, on_token: TokenCallback = None,
                       effort: str | None = None) -> LLMResult:
        client = AsyncOpenAI(api_key=self.api_key)
        full_text = ""
        input_tokens = output_tokens = 0
        truncated = False

        stream = await client.chat.completions.create(
            model=model,
            max_tokens=MAX_OUTPUT_TOKENS,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            stream=True,
            stream_options={"include_usage": True},
        )

        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                token = chunk.choices[0].delta.content
                full_text += token
                if on_token:
                    await on_token(token)
            if chunk.choices and chunk.choices[0].finish_reason == "length":
                truncated = True
            if chunk.usage:
                input_tokens = chunk.usage.prompt_tokens
                output_tokens = chunk.usage.completion_tokens

        return LLMResult(text=full_text, input_tokens=input_tokens, output_tokens=output_tokens, truncated=truncated)
