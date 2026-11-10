import base64
import os
import uuid

from google import genai
from google.genai import types as genai_types
from .base import LLMProvider, LLMResult, MAX_OUTPUT_TOKENS, TokenCallback, ToolCall, ToolTurn

# Finish reasons that mean the model wouldn't answer, which the agent loop treats like Anthropic's "refusal"
_REFUSED = {"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "RECITATION"}
_LEVELS = {"low": "LOW", "medium": "MEDIUM", "high": "HIGH", "xhigh": "HIGH", "max": "HIGH"}


def vertex_enabled() -> bool:
    """Vertex AI bills the Google Cloud project (and its credits); an AI Studio key doesn't."""
    return os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in ("1", "true")


def _usage(meta) -> tuple[int, int, int]:
    """(input, output, cache_read). Thinking is billed as output, and cached prompt tokens are part of the prompt
    count, so they're split out to be priced as cache reads."""
    if not meta:
        return 0, 0, 0
    cached = meta.cached_content_token_count or 0
    return ((meta.prompt_token_count or 0) - cached,
            (meta.candidates_token_count or 0) + (meta.thoughts_token_count or 0), cached)


def _signature(part) -> dict:
    # Gemini 3 rejects a function call sent back without the signature it came with
    sig = getattr(part, "thought_signature", None)
    return {"signature": base64.b64encode(sig).decode()} if sig else {}


def _part(block: dict, names: dict[str, str]) -> genai_types.Part:
    sig = {"thought_signature": base64.b64decode(block["signature"])} if block.get("signature") else {}
    if block["type"] == "tool_use":
        return genai_types.Part(function_call=genai_types.FunctionCall(name=block["name"], args=block["input"]), **sig)
    if block["type"] == "tool_result":
        key = "error" if block.get("is_error") else "output"
        return genai_types.Part(function_response=genai_types.FunctionResponse(
            name=names[block["tool_use_id"]], response={key: block["content"]}))
    return genai_types.Part(text=block["text"], **sig)


def to_contents(messages: list[dict]) -> list[genai_types.Content]:
    """The agent loop keeps its conversation in Anthropic's shape (text, tool_use and tool_result blocks); Gemini
    wants contents with parts, and names each function response after its call."""
    names, contents = {}, []
    for m in messages:
        blocks = m["content"] if isinstance(m["content"], list) else [{"type": "text", "text": m["content"]}]
        names.update({b["id"]: b["name"] for b in blocks if b["type"] == "tool_use"})
        role = "model" if m["role"] == "assistant" else "user"
        # Vertex rejects a turn mixing function responses with text (as "Requests ending with a model turn are not
        # supported"), which the loop makes when a retry adds its prompt after the last tool results. Each goes in
        # its own turn.
        results = [b for b in blocks if b["type"] == "tool_result"]
        rest = [b for b in blocks if b["type"] != "tool_result"]
        for group in (results, rest) if results and rest else (blocks,):
            contents.append(genai_types.Content(role=role, parts=[_part(b, names) for b in group]))
    return contents


class GeminiProvider(LLMProvider):
    """An api_key goes to AI Studio. Without one, requests go to Vertex AI in GOOGLE_CLOUD_PROJECT, authorised by the
    machine's gcloud application-default login."""
    supports_tools = True

    def _client(self):
        if self.api_key:
            return genai.Client(api_key=self.api_key)
        return genai.Client(vertexai=True, project=os.environ["GOOGLE_CLOUD_PROJECT"],
                            location=os.getenv("GOOGLE_CLOUD_LOCATION", "global"))

    @staticmethod
    def _config(system: str, model: str, effort: str | None, **extra) -> genai_types.GenerateContentConfig:
        thinking = ({"thinking_config": genai_types.ThinkingConfig(thinking_level=_LEVELS[effort])}
                    if effort in _LEVELS and model.startswith("gemini-3") else {})
        return genai_types.GenerateContentConfig(system_instruction=system, max_output_tokens=MAX_OUTPUT_TOKENS,
                                                 **thinking, **extra)

    async def complete(self, system: str, prompt: str, model: str, on_token: TokenCallback = None,
                       effort: str | None = None) -> LLMResult:
        client = self._client()
        full_text = ""
        meta = None
        truncated = False

        stream = await client.aio.models.generate_content_stream(
            model=model, contents=prompt, config=self._config(system, model, effort))
        async for chunk in stream:
            token = chunk.text or ""
            full_text += token
            if on_token and token:
                await on_token(token)
            if chunk.candidates and chunk.candidates[0].finish_reason == genai_types.FinishReason.MAX_TOKENS:
                truncated = True
            meta = chunk.usage_metadata or meta

        input_tokens, output_tokens, cached = _usage(meta)
        return LLMResult(text=full_text, input_tokens=input_tokens, output_tokens=output_tokens, truncated=truncated,
                         cache_read_tokens=cached)

    async def complete_with_tools(self, system, messages, tools, model, on_token=None, effort=None,
                                 context_editing=None) -> ToolTurn:
        """context_editing is Anthropic's and is ignored here. Gemini caches repeated prompt prefixes by itself."""
        client = self._client()
        declarations = [genai_types.FunctionDeclaration(name=t["name"], description=t["description"],
                                                        parameters_json_schema=t["input_schema"]) for t in tools]
        config = self._config(system, model, effort, tools=[genai_types.Tool(function_declarations=declarations)],
                              automatic_function_calling=genai_types.AutomaticFunctionCallingConfig(disable=True))
        blocks, meta, finish, blocked = [], None, None, False

        stream = await client.aio.models.generate_content_stream(model=model, contents=to_contents(messages), config=config)
        async for chunk in stream:
            meta = chunk.usage_metadata or meta
            blocked = blocked or bool(chunk.prompt_feedback and chunk.prompt_feedback.block_reason)
            if not chunk.candidates:
                continue
            candidate = chunk.candidates[0]
            finish = candidate.finish_reason or finish
            for part in (candidate.content.parts if candidate.content and candidate.content.parts else []):
                if part.thought:
                    continue
                if part.function_call:
                    blocks.append({"type": "tool_use", "id": f"call_{uuid.uuid4().hex[:12]}",
                                   "name": part.function_call.name, "input": dict(part.function_call.args or {}),
                                   **_signature(part)})
                elif part.text:
                    if on_token:
                        await on_token(part.text)
                    if blocks and blocks[-1]["type"] == "text" and not _signature(part):
                        blocks[-1]["text"] += part.text
                    else:
                        blocks.append({"type": "text", "text": part.text, **_signature(part)})
                elif _signature(part) and blocks:
                    blocks[-1].update(_signature(part))  # a signature can arrive on an empty closing part

        calls = [ToolCall(b["id"], b["name"], b["input"]) for b in blocks if b["type"] == "tool_use"]
        reason = getattr(finish, "value", finish)
        if blocked or reason in _REFUSED:
            stop = "refusal"
        elif reason == "MAX_TOKENS":
            stop = "max_tokens"
        else:
            stop = "tool_use" if calls else ("end_turn" if reason in (None, "STOP") else str(reason).lower())
        input_tokens, output_tokens, cached = _usage(meta)
        return ToolTurn(
            text="".join(b["text"] for b in blocks if b["type"] == "text"),
            tool_calls=calls,
            stop_reason=stop,
            assistant_message={"role": "assistant", "content": blocks},
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cached,
        )

    def tool_results_message(self, results: list[dict]) -> dict:
        return {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": r["id"], "content": r["content"], "is_error": r["is_error"]}
                for r in results
            ],
        }
