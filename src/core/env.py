# -*- coding: utf-8 -*-
"""Reading typed values from environment variables.

Kept free of side effects (no .env loading) so that any module, including
the LLM client, can use it without triggering configuration loading.
"""
from __future__ import annotations

import os

# The German spellings are accepted because existing configurations use them.
_TRUE = {"1", "true", "yes", "on", "ja", "an"}
_FALSE = {"0", "false", "no", "off", "nein", "aus"}


def parse_bool(value: str | None, default: bool | None = False) -> bool | None:
    """Interpret a boolean setting; unknown or empty values give `default`."""
    v = (value or "").strip().lower()
    if v in _TRUE:
        return True
    if v in _FALSE:
        return False
    return default


def env_bool(name: str, default: bool | None = False) -> bool | None:
    return parse_bool(os.getenv(name), default)


# Upload limit in megabytes. Read here, not in src.config, so that the file
# reader can use it without loading the whole configuration.
DEFAULT_MAX_UPLOAD_MB = 50


def max_upload_mb() -> int:
    try:
        return max(int(os.getenv("APP_MAX_UPLOAD_MB", str(DEFAULT_MAX_UPLOAD_MB))), 1)
    except ValueError:
        return DEFAULT_MAX_UPLOAD_MB
