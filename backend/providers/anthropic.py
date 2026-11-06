import anthropic as sdk
from .base import LLMProvider, LLMResult, MAX_OUTPUT_TOKENS, TokenCallback, ToolCall, ToolTurn


class AnthropicProvider(LLMProvider):
    supports_tools = True

    async def complete(self, system: str, prompt: str, model: str, on_token: TokenCallback = None) -> LLMResult:
        client = sdk.AsyncAnthropic(api_key=self.api_key)
        full_text = ""

        async with client.messages.stream(
            model=model,
            max_tokens=MAX_OUTPUT_TOKENS,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            async for chunk in stream.text_stream:
                full_text += chunk
                if on_token:
                    await on_token(chunk)
            final = await stream.get_final_message()

        return LLMResult(
            text=full_text,
            input_tokens=final.usage.input_tokens,
            output_tokens=final.usage.output_tokens,
            truncated=final.stop_reason == "max_tokens",
        )

    async def complete_with_tools(self, system, messages, tools, model, on_token=None) -> ToolTurn:
        client = sdk.AsyncAnthropic(api_key=self.api_key)
        text = ""

        # An agent loop resends the whole conversation each step, so cache it
        async with client.messages.stream(
            model=model,
            max_tokens=MAX_OUTPUT_TOKENS,
            system=system,
            messages=messages,
            tools=tools,
            cache_control={"type": "ephemeral"},
        ) as stream:
            async for chunk in stream.text_stream:
                text += chunk
                if on_token:
                    await on_token(chunk)
            final = await stream.get_final_message()

        return ToolTurn(
            text=text,
            tool_calls=[ToolCall(b.id, b.name, b.input) for b in final.content if b.type == "tool_use"],
            stop_reason=final.stop_reason,
            assistant_message={"role": "assistant", "content": final.content},
            input_tokens=final.usage.input_tokens,
            output_tokens=final.usage.output_tokens,
            cache_read_tokens=getattr(final.usage, "cache_read_input_tokens", 0) or 0,
            cache_write_tokens=getattr(final.usage, "cache_creation_input_tokens", 0) or 0,
        )

    def tool_results_message(self, results: list[dict]) -> dict:
        return {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": r["id"], "content": r["content"], "is_error": r["is_error"]}
                for r in results
            ],
        }
