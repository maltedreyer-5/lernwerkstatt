"""
Robust JSON parser for LLM output.

One component for every place that parses JSON from LLM answers.

Strategies (in order):
1. direct json.loads
2. JSON from a Markdown code block (```json ... ```)
3. first pair of curly braces (greedy)
4. first pair of square brackets (for lists)
5. closing a truncated answer

On failure: optional fallback or LLMJSONParseError.

Also offers llm_complete_json: a wrapper that retries with a stricter
instruction on parse errors.
"""

import json
import logging
import re
from typing import Any, Optional

from src.llm.legacy_keys import translate_legacy_keys

logger = logging.getLogger(__name__)


class LLMJSONParseError(Exception):
    """JSON parsing failed, no recovery possible."""


def parse_llm_json(
    text: str,
    expected_keys: Optional[list[str]] = None,
    context: str = "",
    fallback: Optional[Any] = None,
) -> Any:
    """Parses an LLM answer as JSON.

    Args:
        text: raw answer of the LLM.
        expected_keys: if set and the result is a dict, checks that these
                       keys are present (only warns, does not raise).
        context: descriptive context for logs ("analysis", "briefing", ...).
        fallback: if set, this value is returned on a parse error instead
                  of raising LLMJSONParseError.

    Returns:
        The parsed object (dict, list, or a primitive type).

    Raises:
        LLMJSONParseError: if all strategies fail and no fallback is set.
    """
    if not text or not text.strip():
        if fallback is not None:
            return fallback
        raise LLMJSONParseError(f"empty answer ({context})")

    cleaned = text.strip()

    # Strategy 1: parse directly (most frequent case)
    try:
        result = json.loads(cleaned)
        return _check_expected(result, expected_keys, context)
    except json.JSONDecodeError:
        pass

    # Strategy 2: extract a Markdown code block
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", cleaned, re.DOTALL)
    if match:
        candidate = match.group(1).strip()
        try:
            result = json.loads(candidate)
            return _check_expected(result, expected_keys, context)
        except json.JSONDecodeError:
            pass

    # Strategy 3: first pair of curly braces (for objects)
    obj_start = cleaned.find("{")
    obj_end = cleaned.rfind("}")
    if 0 <= obj_start < obj_end:
        try:
            result = json.loads(cleaned[obj_start : obj_end + 1])
            return _check_expected(result, expected_keys, context)
        except json.JSONDecodeError:
            pass

    # Strategy 4: first pair of square brackets (for lists)
    arr_start = cleaned.find("[")
    arr_end = cleaned.rfind("]")
    if 0 <= arr_start < arr_end:
        try:
            result = json.loads(cleaned[arr_start : arr_end + 1])
            return _check_expected(result, expected_keys, context)
        except json.JSONDecodeError:
            pass

    # Strategy 5: close a truncated answer.
    # With `finish_reason=length` the JSON is valid up to the cut — only the
    # closing brackets are missing. A lesson without its last one or two blocks
    # is far better than no lesson at all.
    repaired = _close_truncated_json(cleaned)
    if repaired is not None:
        try:
            result = json.loads(repaired)
            logger.warning(
                f"JSON was truncated and has been closed ({context}). The end of the answer may be missing."
            )
            return _check_expected(result, expected_keys, context)
        except json.JSONDecodeError:
            pass

    # All strategies failed
    if fallback is not None:
        logger.warning(
            f"JSON parsing failed ({context}). Start of answer: {text[:200]}. Fallback used."
        )
        return fallback

    raise LLMJSONParseError(
        f"JSON parsing failed ({context}). Start of answer: {text[:200]}"
    )


def _check_expected(
    result: Any,
    expected_keys: Optional[list[str]],
    context: str,
) -> Any:
    """Checks optional expected keys (logs a warning, does not raise)."""
    # Every successful parse ends here, so this is the one place where German
    # field names from model output are brought into the English format.
    result = translate_legacy_keys(result)
    if not expected_keys or not isinstance(result, dict):
        return result
    missing = [k for k in expected_keys if k not in result]
    if missing:
        logger.warning(
            f"Expected keys missing ({context}): {missing}. "
            f"Present: {list(result.keys())}"
        )
    return result


async def llm_complete_json(
    llm,
    prompt: str,
    expected_keys: Optional[list[str]] = None,
    context: str = "",
    max_retries: int = 1,
    fallback: Optional[Any] = None,
    **complete_kwargs,
) -> Any:
    """LLM call with automatic JSON parsing and a retry on parse errors.

    On a parse error the prompt is extended with a strict JSON instruction
    and tried again.

    Args:
        llm: LLMClient instance with a complete() method.
        prompt: initial prompt.
        expected_keys: keys expected in the JSON object.
        context: logging context.
        max_retries: number of additional attempts on a parse error.
        fallback: if set, this value is returned instead of an exception.
        **complete_kwargs: passed on to llm.complete().

    Returns:
        The parsed JSON object.
    """
    last_error: Optional[Exception] = None
    current_prompt = prompt

    for attempt in range(max_retries + 1):
        try:
            response = await llm.complete(
                current_prompt,
                json_mode=True,
                **complete_kwargs,
            )
            return parse_llm_json(
                response,
                expected_keys=expected_keys,
                context=context,
            )
        except LLMJSONParseError as e:
            last_error = e
            if attempt < max_retries:
                logger.warning(
                    f"JSON parse retry ({context}), attempt {attempt + 2}/{max_retries + 1}: {e}"
                )
                # On retry, extend the prompt with a strict instruction
                current_prompt = (
                    prompt
                    + ("\n\nIMPORTANT: answer ONLY as plain JSON. "
                    "No Markdown code block, no text before or after. "
                    "Begin with { or [, end with } or ].")
                )

    if fallback is not None:
        logger.warning(
            f"JSON parsing failed after {max_retries + 1} attempts "
            f"({context}). Fallback used."
        )
        return fallback

    raise last_error  # type: ignore[misc]


def _close_truncated_json(text: str) -> str | None:
    """Closes open strings, arrays and objects of a truncated answer.

    Only the last, incomplete element is discarded — the rest is kept.
    Returns None if there was nothing to close (then the error was
    elsewhere).
    """
    start = text.find("{")
    if start < 0:
        start = text.find("[")
    if start < 0:
        return None
    rest = text[start:]

    batch: list[str] = []
    in_string = False
    escape = False
    last_safe = None          # position after a completed element

    for i, z in enumerate(rest):
        if escape:
            escape = False
            continue
        if z == "\\" and in_string:
            escape = True
            continue
        if z == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if z in "{[":
            batch.append("}" if z == "{" else "]")
        elif z in "}]":
            if batch:
                batch.pop()
        elif z == "," and len(batch) <= 2:
            last_safe = i          # a complete element ends here

    if not batch and not in_string:
        return None                      # was not truncated

    # Always roll back to the last completed element, not only when the cut is
    # in the middle of a string. Otherwise a half-written block remains —
    # closing makes it syntactically valid, but its content is incomplete and
    # causes a cascade of "html missing", "questions missing", "cards[0]:
    # front/back missing" later.
    if last_safe is not None:
        rest = rest[:last_safe]
        batch, in_string, escape = [], False, False
        for z in rest:
            if escape:
                escape = False
                continue
            if z == "\\" and in_string:
                escape = True
                continue
            if z == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if z in "{[":
                batch.append("}" if z == "{" else "]")
            elif z in "}]" and batch:
                batch.pop()
    elif in_string:
        rest += '"'

    return rest.rstrip().rstrip(",") + "".join(reversed(batch))
