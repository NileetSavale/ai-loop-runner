import anthropic as sdk
from .base import LLMProvider, LLMResult, TokenCallback


class AnthropicProvider(LLMProvider):
    async def complete(self, system: str, prompt: str, model: str, on_token: TokenCallback = None) -> LLMResult:
        client = sdk.Anthropic(api_key=self.api_key)
        full_text = ""

        with client.messages.stream(
            model=model,
            max_tokens=8096,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for chunk in stream.text_stream:
                full_text += chunk
                if on_token:
                    await on_token(chunk)
            final = stream.get_final_message()

        return LLMResult(
            text=full_text,
            input_tokens=final.usage.input_tokens,
            output_tokens=final.usage.output_tokens,
        )
