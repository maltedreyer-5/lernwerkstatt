"""
LLM client: OpenAI-compatible client with thinking control.

Supports vLLM model families with different thinking APIs:
- qwen3:   chat_template_kwargs.enable_thinking (bool), default ON
- kimi_k2: chat_template_kwargs.thinking (bool), default ON
- glm:     chat_template_kwargs.enable_thinking (bool), default ON
- gemma4:  chat_template_kwargs.enable_thinking (bool), default OFF
- generic: no extra_body (OpenAI, Anthropic proxy, etc.)
"""

import asyncio
import logging
import os
import openai
from openai import AsyncOpenAI

from src.core.env import env_bool

logger = logging.getLogger(__name__)


# Transient error types for which a retry makes sense (network, rate limit,
# 5xx, timeout). Built defensively with getattr, so that a name missing in an
# SDK version does not break the import. If the list is empty (a test stub,
# for instance), the retry silently falls back to no retry — `except ()`
# catches nothing.
_RETRYABLE_NAMES = (
    "APITimeoutError",
    "APIConnectionError",
    "RateLimitError",
    "InternalServerError",
)
RETRYABLE_EXCEPTIONS = tuple(
    getattr(openai, _n) for _n in _RETRYABLE_NAMES if hasattr(openai, _n)
)


# Mapping: family -> (kwarg_name, default_thinking_state)
FAMILY_THINKING_MAP = {
    "qwen3":   ("enable_thinking", True),
    "kimi_k2": ("thinking",        True),
    "glm":     ("enable_thinking", True),
    "gemma4":  ("enable_thinking", False),
    "generic": (None,              None),
}


_GLOBAL_SEM: dict[int, asyncio.Semaphore] = {}


def _global_semaphore() -> asyncio.Semaphore | None:
    """Optional upper limit across ALL jobs of the process.

    DEFAULT: OFF. Every job already has its own limits
    (LLM1/2_MAX_CONCURRENT). An additional process-wide limit acts like a
    queue without fairness: the first job occupies the slots, later ones
    only follow as it drains. In operation it looks as if only the first
    parallel run gets through.

    It is only useful if the endpoint is overloaded by several jobs — then
    set `LLM_GLOBAL_MAX_CONCURRENT` and accept that jobs slow each other
    down.

    One per event loop: a semaphore binds itself to the running loop on the
    first `await`; in another loop the caller would otherwise wait forever.
    """
    raw = os.getenv("LLM_GLOBAL_MAX_CONCURRENT", "").strip()
    if not raw or raw in ("0", "aus", "off"):
        return None
    try:
        limit = max(int(raw), 1)
    except ValueError:
        return None
    try:
        key = id(asyncio.get_running_loop())
    except RuntimeError:
        key = 0
    if key not in _GLOBAL_SEM:
        _GLOBAL_SEM[key] = asyncio.Semaphore(limit)
    return _GLOBAL_SEM[key]


class _Open:
    """Placeholder when no process-wide limit is set."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


_OPEN = _Open()


class LLMClient:
    """OpenAI-compatible client with thinking control per model family.

    Usage:
        client = LLMClient(base_url=..., api_key=..., model=..., family="qwen3")

        # thinking on (for analysis, quality checks):
        response = await client.complete("prompt", thinking=True)

        # thinking off (for fast section processing):
        response = await client.complete("prompt", thinking=False)

        # default: thinking follows the model default
        response = await client.complete("prompt")
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        family: str = "generic",
        thinking: bool = True,
        max_tokens: int = 16000,
        temperature: float = 0.3,
        timeout: int = 300,
        max_concurrent: int = 3,
        max_retries: int = 2,
        retry_base_delay: float = 1.5,
    ):
        self.model = model
        self.family = family
        self.thinking_enabled = thinking
        # Value sent to generic endpoints with thinking=False. Empty = feature
        # switched off (not every endpoint knows it).
        self.reasoning_effort_off = os.getenv("LLM_REASONING_EFFORT_OFF", "").strip()
        # Only set this if the endpoint demonstrably handles thinking AND
        # guided decoding together.
        self.json_thinking_allowed = bool(env_bool("LLM_JSON_THINKING", False))
        # Figures for the technical report: how often was an answer cut off at
        # the budget, and how often did nothing come back at all? Both could
        # otherwise only be picked laboriously from the logs.
        self.total_truncated = 0
        self.total_empty = 0
        self.total_empty_rescued = 0
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.max_concurrent = max_concurrent
        self.max_retries = max_retries
        self.retry_base_delay = retry_base_delay
        # Per-client limit. A process-wide limit exists in addition (see
        # _global_semaphore): every job builds its own clients with their own
        # semaphore, so three parallel jobs would otherwise mean three times
        # the concurrent requests against an endpoint others may share as
        # well. That one is not fetched here, because the client is often
        # created outside the event loop it is used in later.
        self._semaphore = asyncio.Semaphore(max_concurrent)
        # max_retries=0: retries happen in _create_with_retry. The SDK's own
        # default (2) would multiply with them — up to nine attempts, each
        # with the full timeout, for a single failing call.
        # Endpoints without authentication (a local vLLM, for instance) are
        # configured with an empty key. The openai SDK from version 2 on
        # refuses an empty key outright, so a placeholder is sent instead;
        # servers without authentication ignore the header.
        self._client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key or "EMPTY",
            timeout=timeout,
            max_retries=0,
        )

        # Token tracking (cumulative over all calls)
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_calls = 0

        kwarg_name, default_state = FAMILY_THINKING_MAP.get(
            family, (None, None)
        )
        self._thinking_kwarg_name = kwarg_name
        self._thinking_default = default_state

        logger.info(
            f"LLMClient: model={model}, family={family}, "
            f"thinking={thinking}, kwarg={kwarg_name}, "
            f"max_concurrent={max_concurrent}"
        )

    def _track_usage(self, response):
        """Records token usage from the API response."""
        self.total_calls += 1
        if hasattr(response, "usage") and response.usage:
            self.total_input_tokens += response.usage.prompt_tokens or 0
            self.total_output_tokens += response.usage.completion_tokens or 0

    @property
    def total_tokens(self) -> int:
        return self.total_input_tokens + self.total_output_tokens

    def reset_tracking(self):
        """Resets the token counters."""
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_calls = 0

    def _build_extra_body(self, thinking: bool | None) -> dict | None:
        """Builds extra_body for vLLM chat_template_kwargs.

        Args:
            thinking: True/False to control thinking explicitly.
                      None = use self.thinking_enabled from the config.

        Returns:
            A dict for extra_body, or None (with family=generic).
        """
        if self._thinking_kwarg_name is None:
            # generic (OpenAI-compatible): thinking cannot be controlled
            # through chat_template_kwargs. Many of these endpoints know
            # `reasoning_effort`, though — without it `thinking=False` has no
            # effect here, and the budget can go entirely into thinking
            # (observed: 16000 tokens, 0 characters of output).
            if self.reasoning_effort_off and thinking is False:
                return {"reasoning_effort": self.reasoning_effort_off}
            return None

        # None -> Config-Default
        use_thinking = thinking if thinking is not None else self.thinking_enabled

        return {
            "chat_template_kwargs": {
                self._thinking_kwarg_name: use_thinking,
            }
        }

    async def _create_with_retry(self, kwargs: dict):
        """Runs a (non-streaming) completion call with retry and exponential
        backoff on transient errors.

        The semaphore is held per attempt and released during the backoff,
        so that a waiting call does not block the concurrency slots.
        """
        last_exc = None
        for attempt in range(self.max_retries + 1):
            try:
                # The order is decisive: FIRST the client's own lock, THEN the
                # process-wide one. The other way round a task holds a global
                # slot while it waits for its client's own — once all global
                # slots are held by such waiters, nobody gets through and
                # nobody releases. Parallel jobs come to a standstill that way.
                async with self._semaphore, (_global_semaphore() or _OPEN):
                    return await self._client.chat.completions.create(**kwargs)
            except RETRYABLE_EXCEPTIONS as e:
                last_exc = e
                if attempt < self.max_retries:
                    delay = self.retry_base_delay * (2 ** attempt)
                    logger.warning(
                        f"LLM call failed transiently "
                        f"({type(e).__name__}: {str(e)[:120]}) — "
                        f"Retry {attempt + 1}/{self.max_retries} in {delay:.1f}s"
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        f"LLM call failed for good after {self.max_retries} retries: "
                        f"{type(e).__name__}: {e}"
                    )
                    raise
        # Unreachable (the loop ends with return or raise), but to be safe:
        if last_exc:
            raise last_exc

    async def complete(
        self,
        prompt: str,
        system: str = "",
        json_mode: bool = False,
        max_tokens: int | None = None,
        temperature: float | None = None,
        thinking: bool | None = None,
    ) -> str:
        """Single LLM call, waits for the complete answer.

        Args:
            thinking: True = force thinking, False = switch it off,
                      None = model default.
        """
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        # json_mode sets guided decoding (`response_format`). A thinking model
        # wants to emit thinking tokens first — but the grammar forbids
        # anything that is not valid JSON. The model then spins until the
        # budget is used up and returns NOTHING. Observed exactly like that:
        # 16000 tokens, 0 characters, and only on json_mode calls (teaching
        # script, detail plan, blocks) — text calls (script, assembly) always
        # went through. Hence: json_mode switches thinking off unless
        # explicitly asked otherwise.
        if json_mode and thinking is None and not self.json_thinking_allowed:
            thinking = False

        kwargs = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens or self.max_tokens,
            "temperature": temperature if temperature is not None else self.temperature,
        }

        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        extra_body = self._build_extra_body(thinking)
        if extra_body:
            kwargs["extra_body"] = extra_body

        logger.debug(
            f"LLM-Call: model={self.model}, thinking={thinking}, "
            f"tokens={kwargs['max_tokens']}"
        )

        response = await self._create_with_retry(kwargs)
        self._track_usage(response)
        content = response.choices[0].message.content or ""

        # Safety net: budget used up, but nothing came back. That is not a
        # length problem — it is thinking that burnt the budget. A second
        # attempt with thinking explicitly off usually brings the answer. Only
        # ONE attempt, otherwise the run time doubles.
        if (not content.strip()
                and getattr(response.choices[0], "finish_reason", None) == "length"
                and thinking is not False):
            logger.warning(
                "empty answer despite exhausted budget (%s tokens) — retry without thinking.", kwargs["max_tokens"])
            self.total_empty_rescued += 1
            second = dict(kwargs)
            extra_off = self._build_extra_body(False)
            if extra_off:
                second["extra_body"] = extra_off
            else:
                second.pop("extra_body", None)
            response = await self._create_with_retry(second)
            self._track_usage(response)
            content = response.choices[0].message.content or ""

        # Truncation detection: with finish_reason="length" the model has
        # exceeded its max_tokens budget. JSON answers are then usually
        # unparseable (cut off in the middle of a string). A clear warning
        # instead of only a fallback in the parser.
        finish_reason = getattr(response.choices[0], "finish_reason", None)
        if finish_reason == "length":
            self.total_truncated += 1
            self.total_empty += 1 if not (content or "").strip() else 0
            logger.warning(
                f"LLM answer cut off at max_tokens={kwargs['max_tokens']} "
                f"(finish_reason=length). {len(content)} characters received. "
                f"The caller should retry with a higher max_tokens or "
                f"reduce the input."
            )

        logger.debug(f"LLM answer: {len(content)} characters, finish={finish_reason}")
        return content

    async def chat(
        self,
        messages: list[dict],
        max_tokens: int | None = None,
        temperature: float | None = None,
        thinking: bool | None = None,
    ) -> str:
        """Chat completion with the full message history."""
        kwargs = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens or self.max_tokens,
            "temperature": temperature if temperature is not None else self.temperature,
        }

        extra_body = self._build_extra_body(thinking)
        if extra_body:
            kwargs["extra_body"] = extra_body

        response = await self._create_with_retry(kwargs)
        self._track_usage(response)
        return response.choices[0].message.content or ""

    async def stream(
        self,
        messages: list[dict],
        max_tokens: int | None = None,
        temperature: float | None = None,
        thinking: bool | None = None,
    ):
        """Streaming-Chat-Completion. Yields Text-Chunks."""
        kwargs = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens or self.max_tokens,
            "temperature": temperature if temperature is not None else self.temperature,
            "stream": True,
        }

        extra_body = self._build_extra_body(thinking)
        if extra_body:
            kwargs["extra_body"] = extra_body

        async with self._semaphore:
            # Retry only for establishing the connection (before the first
            # chunk). A retry mid-stream would duplicate chunks already
            # emitted, hence deliberately not here.
            last_exc = None
            stream = None
            for attempt in range(self.max_retries + 1):
                try:
                    stream = await self._client.chat.completions.create(**kwargs)
                    break
                except RETRYABLE_EXCEPTIONS as e:
                    last_exc = e
                    if attempt < self.max_retries:
                        delay = self.retry_base_delay * (2 ** attempt)
                        logger.warning(
                            f"Stream connection failed "
                            f"({type(e).__name__}) — retry {attempt + 1}/"
                            f"{self.max_retries} in {delay:.1f}s"
                        )
                        await asyncio.sleep(delay)
                    else:
                        raise
            if stream is None and last_exc:
                raise last_exc
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
