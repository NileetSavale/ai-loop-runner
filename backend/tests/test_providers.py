"""Runs each provider's real SDK against a local server that streams like the real API, slowly."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
import json
import threading
import time
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

import pytest

from providers.anthropic import AnthropicProvider
from providers.base import MAX_OUTPUT_TOKENS
from providers.gemini import GeminiProvider
from providers.mistral import MistralProvider
from providers.openai import OpenAIProvider

TOKENS = ["Hel", "lo ", "wor", "ld"]
DELAY = 0.1


def _anthropic(stop):
    message = {"id": "m", "type": "message", "role": "assistant", "content": [], "model": "x",
               "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 7, "output_tokens": 1}}
    yield "message_start", {"type": "message_start", "message": message}
    yield "content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}
    for t in TOKENS:
        yield "content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": t}}
    yield "content_block_stop", {"type": "content_block_stop", "index": 0}
    yield "message_delta", {"type": "message_delta", "delta": {"stop_reason": "max_tokens" if stop else "end_turn", "stop_sequence": None},
                            "usage": {"output_tokens": 11}}
    yield "message_stop", {"type": "message_stop"}


def _anthropic_tool():
    message = {"id": "m", "type": "message", "role": "assistant", "content": [], "model": "x", "stop_reason": None,
               "stop_sequence": None, "usage": {"input_tokens": 7, "output_tokens": 1, "cache_read_input_tokens": 100,
                                                 "cache_creation_input_tokens": 20}}
    yield "message_start", {"type": "message_start", "message": message}
    yield "content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "thinking", "thinking": "", "signature": ""}}
    yield "content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "signature_delta", "signature": "sig123"}}
    yield "content_block_stop", {"type": "content_block_stop", "index": 0}
    yield "content_block_start", {"type": "content_block_start", "index": 1, "content_block": {"type": "text", "text": ""}}
    yield "content_block_delta", {"type": "content_block_delta", "index": 1, "delta": {"type": "text_delta", "text": "Looking."}}
    yield "content_block_stop", {"type": "content_block_stop", "index": 1}
    yield "content_block_start", {"type": "content_block_start", "index": 2,
                                  "content_block": {"type": "tool_use", "id": "t1", "name": "read_file", "input": {}}}
    for part in ['{"path": ', '"src/a.py"}']:
        yield "content_block_delta", {"type": "content_block_delta", "index": 2, "delta": {"type": "input_json_delta", "partial_json": part}}
    yield "content_block_stop", {"type": "content_block_stop", "index": 2}
    yield "message_delta", {"type": "message_delta", "delta": {"stop_reason": "tool_use", "stop_sequence": None}, "usage": {"output_tokens": 11}}
    yield "message_stop", {"type": "message_stop"}


def _openai_style(stop):
    base = {"id": "c", "object": "chat.completion.chunk", "created": 1, "model": "x"}
    for t in TOKENS:
        yield None, {**base, "choices": [{"index": 0, "delta": {"role": "assistant", "content": t}, "finish_reason": None}]}
    yield None, {**base, "choices": [{"index": 0, "delta": {"content": ""}, "finish_reason": "length" if stop else "stop"}]}
    yield None, {**base, "choices": [], "usage": {"prompt_tokens": 7, "completion_tokens": 11, "total_tokens": 18}}


def _mistral(stop):
    base = {"id": "c", "object": "chat.completion.chunk", "created": 1, "model": "x"}
    for t in TOKENS:
        yield None, {**base, "choices": [{"index": 0, "delta": {"role": "assistant", "content": t}, "finish_reason": None}]}
    # Unlike OpenAI, Mistral sends usage on the same chunk as the finish reason
    yield None, {**base, "choices": [{"index": 0, "delta": {"content": ""}, "finish_reason": "length" if stop else "stop"}],
                 "usage": {"prompt_tokens": 7, "completion_tokens": 11, "total_tokens": 18}}


def _gemini(stop):
    for i, t in enumerate(TOKENS):
        last = i == len(TOKENS) - 1
        chunk = {"candidates": [{"content": {"role": "model", "parts": [{"text": t}]}}],
                 "usageMetadata": {"promptTokenCount": 7, "candidatesTokenCount": 11, "totalTokenCount": 18}}
        if last:
            chunk["candidates"][0]["finishReason"] = "MAX_TOKENS" if stop else "STOP"
        yield None, chunk


@pytest.fixture
def server():
    state = {"stop": False, "bodies": []}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            state["bodies"].append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            if self.path.startswith("/anthropic"):
                events = _anthropic_tool() if state.get("tool") else _anthropic(state["stop"])
            elif self.path.startswith("/openai"):
                events = _openai_style(state["stop"])
            elif self.path.startswith("/mistral"):
                events = _mistral(state["stop"])
            else:
                events = _gemini(state["stop"])
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for name, data in events:
                time.sleep(DELAY)
                prefix = f"event: {name}\n" if name else ""
                self.wfile.write(f"{prefix}data: {json.dumps(data)}\n\n".encode())
                self.wfile.flush()
            if self.path.startswith(("/openai", "/mistral")):
                self.wfile.write(b"data: [DONE]\n\n")

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    state["url"] = f"http://127.0.0.1:{httpd.server_address[1]}"
    yield state
    httpd.shutdown()


def _make(name, url):
    """The provider plus patches that point its real SDK at the local server."""
    if name == "anthropic":
        import anthropic
        return AnthropicProvider("k"), patch("providers.anthropic.sdk.AsyncAnthropic",
                                             partial(anthropic.AsyncAnthropic, base_url=f"{url}/anthropic"))
    if name == "openai":
        import openai
        return OpenAIProvider("k"), patch("providers.openai.AsyncOpenAI", partial(openai.AsyncOpenAI, base_url=f"{url}/openai"))
    if name == "mistral":
        from mistralai.client import Mistral
        return MistralProvider("k"), patch("providers.mistral.Mistral", partial(Mistral, server_url=f"{url}/mistral"))
    from google import genai
    return GeminiProvider("k"), patch("providers.gemini.genai.Client",
                                      partial(genai.Client, http_options={"base_url": f"{url}/gemini"}))


PROVIDERS = ["anthropic", "openai", "mistral", "gemini"]


def _complete(provider, on_token=None):
    return provider.complete("sys", "hi", "x", on_token)


@pytest.mark.parametrize("name", PROVIDERS)
def test_streams_text_and_usage(server, name):
    provider, sdk_patch = _make(name, server["url"])
    seen = []

    async def on_token(t):
        seen.append(t)

    with sdk_patch:
        result = asyncio.run(_complete(provider, on_token))
    assert result.text == "Hello world" and seen == TOKENS
    assert (result.input_tokens, result.output_tokens) == (7, 11)
    assert result.truncated is False


@pytest.mark.parametrize("name", PROVIDERS)
def test_reports_when_reply_was_cut_off(server, name):
    server["stop"] = True
    provider, sdk_patch = _make(name, server["url"])
    with sdk_patch:
        assert asyncio.run(_complete(provider)).truncated is True


@pytest.mark.parametrize("name", PROVIDERS)
def test_sends_the_output_limit(server, name):
    provider, sdk_patch = _make(name, server["url"])
    with sdk_patch:
        asyncio.run(_complete(provider))
    assert str(MAX_OUTPUT_TOKENS) in json.dumps(server["bodies"][-1])


@pytest.mark.parametrize("name", PROVIDERS)
def test_other_work_keeps_running_during_a_stream(server, name):
    """One user's LLM call must not freeze everyone else's requests."""
    provider, sdk_patch = _make(name, server["url"])

    async def scenario():
        ticks = 0
        task = asyncio.create_task(_complete(provider))
        while not task.done():
            await asyncio.sleep(0.01)
            ticks += 1
        await task
        return ticks

    with sdk_patch:
        ticks = asyncio.run(scenario())
    assert ticks >= 15  # the stream lasts at least 0.4s, so a free event loop ticks far more than this


def test_anthropic_tool_turn_round_trip(server):
    """The full wire format: a real SDK parses a tool call, then sends the answer back in the right shape."""
    server["tool"] = True
    provider, sdk_patch = _make("anthropic", server["url"])
    tools = [{"name": "read_file", "description": "d", "input_schema": {"type": "object", "properties": {}}}]
    messages = [{"role": "user", "content": "go"}]

    async def scenario():
        first = await provider.complete_with_tools("sys", messages, tools, "x")
        history = messages + [first.assistant_message, provider.tool_results_message(
            [{"id": first.tool_calls[0].id, "content": "file text", "is_error": False}])]
        await provider.complete_with_tools("sys", history, tools, "x")
        return first

    with sdk_patch:
        first = asyncio.run(scenario())
    call = first.tool_calls[0]
    assert (call.id, call.name, call.input) == ("t1", "read_file", {"path": "src/a.py"})
    assert first.stop_reason == "tool_use" and first.text == "Looking."
    assert (first.cache_read_tokens, first.cache_write_tokens) == (100, 20)
    sent = server["bodies"][-1]
    assert sent["cache_control"] == {"type": "ephemeral"}
    assert [b["type"] for b in sent["messages"][1]["content"]] == ["thinking", "text", "tool_use"]
    # Thinking goes back exactly as received, or the API rejects the request. SDK 0.40 failed this.
    assert sent["messages"][1]["content"][0] == {"type": "thinking", "thinking": "", "signature": "sig123"}
    assert sent["messages"][2]["content"] == [{"type": "tool_result", "tool_use_id": "t1", "content": "file text", "is_error": False}]
