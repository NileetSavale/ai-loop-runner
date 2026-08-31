from mistralai.client import Mistral
from .base import LLMProvider, LLMResult, TokenCallback


class MistralProvider(LLMProvider):
    async def complete(self, system: str, prompt: str, model: str, on_token: TokenCallback = None) -> LLMResult:
        client = Mistral(api_key=self.api_key)
        full_text = ""

        async with client.chat.stream_async(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        ) as stream:
            async for chunk in stream:
                token = chunk.data.choices[0].delta.content or "" if chunk.data.choices else ""
                full_text += token
                if on_token and token:
                    await on_token(token)
            final = await stream.get_final_response()

        usage = final.usage
        return LLMResult(
            text=full_text,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
        )
