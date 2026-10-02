# -*- coding: utf-8 -*-
"""Guards the json_mode/thinking rule in the LLM client.

`response_format={"type":"json_object"}` forces guided decoding. A thinking
model then cannot emit its thinking tokens, spins until the budget is used
up and delivers 0 characters — observed only on json_mode calls (teaching
script, detail plan, blocks), never on text calls.
"""
import asyncio
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Mock third-party libraries so that the client can be imported.
for name in ("openai", "httpx"):
    if name not in sys.modules:
        try:
            __import__(name)
        except ImportError:
            m = types.ModuleType(name)
            m.__getattr__ = lambda a: object  # type: ignore[attr-defined]
            sys.modules[name] = m

from src.llm.client import LLMClient  # noqa: E402


def check(b, name):
    print(f"  {'ok  ' if b else 'FAIL'} {name}")
    return 0 if b else 1


class _Response:
    def __init__(self, text, finish="stop"):
        self.choices = [types.SimpleNamespace(
            message=types.SimpleNamespace(content=text), finish_reason=finish)]
        self.usage = types.SimpleNamespace(
            prompt_tokens=10, completion_tokens=5, total_tokens=15)


def _client(family="qwen3"):
    c = LLMClient.__new__(LLMClient)
    c.model, c.max_tokens, c.temperature = "m", 16000, 0.3
    c.thinking_enabled = True
    c._thinking_kwarg_name = None if family == "generic" else "enable_thinking"
    c._thinking_default = True
    c.reasoning_effort_off = ""
    c.json_thinking_allowed = False
    c.total_calls = c.total_input_tokens = c.total_output_tokens = 0
    c.total_truncated = c.total_empty = c.total_empty_rescued = 0
    return c


def test_json_mode_turns_thinking_off():
    print("json_mode and thinking")
    c = _client()
    seen = []

    async def fake(kwargs):
        seen.append(kwargs)
        return _Response('{"a":1}')

    c._create_with_retry = fake
    c._track_usage = lambda r: None

    asyncio.run(c.complete("p", json_mode=True))
    f = check(seen[-1]["extra_body"]["chat_template_kwargs"]["enable_thinking"] is False,
               "json_mode → thinking off")

    seen.clear()
    asyncio.run(c.complete("p"))
    body = seen[-1].get("extra_body")
    f += check(body is None or body["chat_template_kwargs"]["enable_thinking"] is True,
                "a text call keeps thinking")

    seen.clear()
    asyncio.run(c.complete("p", json_mode=True, thinking=True))
    f += check(seen[-1]["extra_body"]["chat_template_kwargs"]["enable_thinking"] is True,
                "explicit thinking=True wins")

    c.json_thinking_allowed = True
    seen.clear()
    asyncio.run(c.complete("p", json_mode=True))
    f += check(seen[-1]["extra_body"]["chat_template_kwargs"]["enable_thinking"] is True,
                "LLM_JSON_THINKING lifts the rule")
    return f


def test_empty_response_is_rescued():
    print("rescue on an empty answer")
    c = _client()
    call = []

    async def fake(kwargs):
        call.append(kwargs)
        return _Response("", "length") if len(call) == 1 else _Response('{"a":1}')

    c._create_with_retry = fake
    c._track_usage = lambda r: None
    out = asyncio.run(c.complete("p", thinking=True))
    f = check(out.strip() == '{"a":1}', "the second attempt delivers content")
    f += check(len(call) == 2, "exactly one retry")
    f += check(call[1]["extra_body"]["chat_template_kwargs"]["enable_thinking"] is False,
                "retry without thinking")
    f += check(c.total_empty_rescued == 1, "rescue counted")

    # thinking already off → no second round, otherwise endless repetition
    c2 = _client(); call2 = []

    async def fake2(kwargs):
        call2.append(kwargs)
        return _Response("", "length")

    c2._create_with_retry = fake2
    c2._track_usage = lambda r: None
    asyncio.run(c2.complete("p", thinking=False))
    f += check(len(call2) == 1, "no second attempt if thinking was already off")
    return f


if __name__ == "__main__":
    errors = test_json_mode_turns_thinking_off() + test_empty_response_is_rescued()
    print(f"\n{'LLM RULES OK' if not errors else f'{errors} FAILED'}")
    sys.exit(1 if errors else 0)
