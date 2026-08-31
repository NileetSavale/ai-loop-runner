from google import genai
from google.genai import types as genai_types
from .base import LLMProvider, LLMResult, TokenCallback


class GeminiProvider(LLMProvider):
    async def complete(self, system: str, prompt: str, model: str, on_token: TokenCallback = None) -> LLMResult:
        client = genai.Client(api_key=self.api_key)
        full_text = ""
        input_tokens = output_tokens = 0

        async for chunk in client.aio.models.generate_content_stream(
            model=model,
            contents=prompt,
            config=genai_types.GenerateContentConfig(system_instruction=system),
        ):
            token = chunk.text or ""
            full_text += token
            if on_token and token:
                await on_token(token)
            if chunk.usage_metadata:
                input_tokens = chunk.usage_metadata.prompt_token_count or 0
                output_tokens = chunk.usage_metadata.candidates_token_count or 0

        return LLMResult(text=full_text, input_tokens=input_tokens, output_tokens=output_tokens)
