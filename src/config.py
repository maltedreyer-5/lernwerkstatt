"""
Configuration of the LernWerkstatt — loads values from .env or the environment.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

from src.core.env import DEFAULT_MAX_UPLOAD_MB, max_upload_mb, parse_bool

load_dotenv()


def _bool(val: str) -> bool:
    return bool(parse_bool(val, False))


# Model families supported for thinking control
SUPPORTED_FAMILIES = {"qwen3", "kimi_k2", "glm", "gemma4", "generic"}


# Working directory for the job register and the job folders. Resolved to an
# absolute path once, at import: the register stores folder paths, and a
# relative path would silently point elsewhere as soon as a script runs from
# a different current directory.
WORK_DIR_PATH = Path(os.getenv("WORK_DIR") or "work").resolve()


@dataclass
class LLMConfig:
    base_url: str
    api_key: str
    model: str
    family: str = "generic"       # qwen3 | kimi_k2 | glm | gemma4 | generic
    thinking: bool = True         # thinking/reasoning on/off
    max_tokens: int = 16000
    temperature: float = 0.3
    timeout: int = 300            # timeout in seconds
    max_concurrent: int = 3       # max concurrent calls (semaphore)

    def __post_init__(self):
        if self.family not in SUPPORTED_FAMILIES:
            raise ValueError(
                f"Unknown model family '{self.family}'. "
                f"Allowed: {', '.join(sorted(SUPPORTED_FAMILIES))}"
            )


@dataclass
class EmbedderConfig:
    base_url: str = ""
    api_key: str = ""
    model: str = "default"


@dataclass
class RerankerConfig:
    base_url: str = ""
    api_key: str = ""
    # Only needed if the service requires a model name (Cohere, Jina).
    # TEI and vLLM ignore it.
    model: str = ""


@dataclass
class AppConfig:
    title: str = "LernWerkstatt"
    root_path: str = ""
    # Loopback by default: outside a container the interface is not meant to
    # be reachable from the network. The container image sets 0.0.0.0.
    server_name: str = "127.0.0.1"
    server_port: int = 7860
    max_upload_mb: int = DEFAULT_MAX_UPLOAD_MB

    # LLM
    llm1: LLMConfig = field(default_factory=lambda: LLMConfig("", "", ""))
    llm2: LLMConfig | None = None

    # Embedder + Reranker
    embedder: EmbedderConfig = field(default_factory=EmbedderConfig)
    reranker: RerankerConfig = field(default_factory=RerankerConfig)


def load_config() -> AppConfig:
    """Loads the configuration from environment variables."""
    llm1 = LLMConfig(
        base_url=os.getenv("LLM1_BASE_URL", ""),
        api_key=os.getenv("LLM1_API_KEY", ""),
        model=os.getenv("LLM1_MODEL", ""),
        family=os.getenv("LLM1_FAMILY", "generic"),
        thinking=_bool(os.getenv("LLM1_THINKING", "true")),
        max_tokens=int(os.getenv("LLM1_MAX_TOKENS", "16000")),
        temperature=float(os.getenv("LLM1_TEMPERATURE", "0.3")),
        timeout=int(os.getenv("LLM1_TIMEOUT", "300")),
        max_concurrent=int(os.getenv("LLM1_MAX_CONCURRENT", "3")),
    )

    llm2 = None
    if os.getenv("LLM2_BASE_URL") and os.getenv("LLM2_MODEL"):
        llm2 = LLMConfig(
            base_url=os.getenv("LLM2_BASE_URL", ""),
            api_key=os.getenv("LLM2_API_KEY", llm1.api_key),
            model=os.getenv("LLM2_MODEL", ""),
            family=os.getenv("LLM2_FAMILY", llm1.family),
            thinking=_bool(os.getenv("LLM2_THINKING", "false")),
            max_tokens=int(os.getenv("LLM2_MAX_TOKENS", "8000")),
            temperature=float(os.getenv("LLM2_TEMPERATURE", "0.2")),
            timeout=int(os.getenv("LLM2_TIMEOUT", "300")),
            max_concurrent=int(os.getenv("LLM2_MAX_CONCURRENT", "2")),
        )

    return AppConfig(
        title=os.getenv("APP_TITLE", "LernWerkstatt"),
        root_path=os.getenv("APP_ROOT_PATH", ""),
        server_name=os.getenv("GRADIO_SERVER_NAME", "127.0.0.1"),
        server_port=int(os.getenv("GRADIO_SERVER_PORT", "7860")),
        max_upload_mb=max_upload_mb(),
        llm1=llm1,
        llm2=llm2,
        embedder=EmbedderConfig(
            base_url=os.getenv("EMBEDDER_BASE_URL", ""),
            api_key=os.getenv("EMBEDDER_API_KEY", ""),
            model=os.getenv("EMBEDDER_MODEL", "default"),
        ),
        reranker=RerankerConfig(
            base_url=os.getenv("RERANKER_BASE_URL", ""),
            api_key=os.getenv("RERANKER_API_KEY", ""),
            model=os.getenv("RERANKER_MODEL", ""),
        ),
    )


# ── Budget of the block phase ──────────────────────────────────────────
# The `blocks` tasks produce the largest outputs of the pipeline. Whether a
# larger budget helps depends on the endpoint: with models that take thinking
# tokens from the same budget, a higher value can even empty the output
# (observed: 16000 tokens, 0 characters). Hence configurable instead of
# guessed — and the technical report counts how often answers were cut off.
BLOCKS_MAX_TOKENS = int(os.getenv("BLOCKS_MAX_TOKENS", "14000"))
# "" = coupled to use_primary, "0"/"false" = off, "1"/"true" = on
_bt = os.getenv("BLOCKS_THINKING", "false")
BLOCKS_THINKING = None if _bt.strip() == "" else _bool(_bt)
