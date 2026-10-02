# -*- coding: utf-8 -*-
"""Checks that the configuration can be loaded at all.

Guards against a configuration that the application accepts at start-up but
that fails on the FIRST job — `load_config` is only called there, so a
mismatch between `load_config()` and a config data class (an unknown field
such as `model=` for `RerankerConfig`) would show only then.

Also checks that a configured reranker actually ends up in the index.
"""
import os
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

for _m in ("openai", "httpx", "dotenv"):
    if _m not in sys.modules:
        try:
            __import__(_m)
        except ImportError:
            _mod = types.ModuleType(_m)
            _mod.__getattr__ = lambda a: (lambda *x, **k: None)  # type: ignore[attr-defined]
            sys.modules[_m] = _mod


def check(b, name):
    print(f"  {'ok  ' if b else 'FAIL'} {name}")
    return 0 if b else 1


def _environment(**values):
    """Clean environment: a local .env must not interfere here."""
    for k in list(os.environ):
        if k.startswith(("LLM1_", "LLM2_", "EMBEDDER_", "RERANKER_", "APP_", "PIPELINE_")):
            del os.environ[k]
    os.environ.update(values)


def test_load_config():
    print("load the configuration")
    import src.config as c
    c.load_dotenv = lambda *a, **k: None

    _environment(LLM1_BASE_URL="https://beispiel.invalid/v1", LLM1_MODEL="m",
              LLM1_FAMILY="qwen3")
    cfg = c.load_config()
    f = check(cfg.llm1.model == "m", "minimal configuration loads")
    # Without LLM2_BASE_URL llm2 stays None; the caller then uses LLM1.
    f += check(cfg.llm2 is None, "without LLM2 configuration llm2 stays empty")
    _environment(LLM1_BASE_URL="https://beispiel.invalid/v1", LLM1_MODEL="m",
              LLM1_FAMILY="qwen3",
              LLM2_BASE_URL="https://zweit.invalid/v1", LLM2_MODEL="m2")
    cfg2 = c.load_config()
    f += check(cfg2.llm2 is not None and cfg2.llm2.family == "qwen3",
                "LLM2 inherits the family of LLM1")

    # Every field load_config passes must be known to the data class
    _environment(LLM1_BASE_URL="https://beispiel.invalid/v1", LLM1_MODEL="m",
              LLM1_FAMILY="kimi_k2",
              EMBEDDER_BASE_URL="https://beispiel.invalid/v1",
              EMBEDDER_MODEL="bge", EMBEDDER_API_KEY="k",
              RERANKER_BASE_URL="https://beispiel.invalid/v1/rerank",
              RERANKER_MODEL="rerank-v1", RERANKER_API_KEY="k")
    cfg = c.load_config()
    f += check(cfg.reranker.model == "rerank-v1", "RERANKER_MODEL arrives")
    f += check(cfg.embedder.model == "bge", "EMBEDDER_MODEL arrives")

    # An invalid family must fail clearly, not fall back to generic silently
    _environment(LLM1_BASE_URL="https://beispiel.invalid/v1", LLM1_MODEL="m",
              LLM1_FAMILY="kimi")
    try:
        c.load_config()
        f += check(False, "invalid model family is reported")
    except ValueError as e:
        f += check("kimi_k2" in str(e), "invalid model family names the valid ones")
    return f


def test_reranker_is_wired():
    print("Reranker im Index")
    import src.config as c
    c.load_dotenv = lambda *a, **k: None
    _environment(LLM1_BASE_URL="https://beispiel.invalid/v1", LLM1_MODEL="m",
              LLM1_FAMILY="qwen3",
              EMBEDDER_BASE_URL="https://beispiel.invalid/v1", EMBEDDER_MODEL="bge",
              RERANKER_BASE_URL="https://beispiel.invalid/v1/rerank",
              RERANKER_MODEL="rerank-v1")

    source = (ROOT / "src" / "ui" / "wizard.py").read_text(encoding="utf-8")
    i = source.index("def _inventory_index")
    block = source[i:source.index("\ndef ", i + 10)]
    f = check("RerankerClient(" in block,
               "the index creates a reranker if configured")
    f += check("InventoryIndex(" in block and "reranker" in block,
                "the reranker is passed to the index")

    from src.pipeline.inventory import RerankerClient
    r = RerankerClient("https://beispiel.invalid/v1/rerank", "k", "rerank-v1")
    f += check(r.model == "rerank-v1", "the client accepts the model name")
    return f


if __name__ == "__main__":
    errors = test_load_config() + test_reranker_is_wired()
    print(f"\n{'CONFIGURATION OK' if not errors else f'{errors} FAILED'}")
    sys.exit(1 if errors else 0)
