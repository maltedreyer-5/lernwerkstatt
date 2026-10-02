#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Checks the configured endpoints and says what is wrong.

A 404 on /v1/embeddings can have three very different causes: the route
is missing (the host serves chat only), the key does not match, or the
model name is unknown. This tool tells them apart.

    python scripts/check_services.py
"""
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def _call(url: str, key: str, data_: dict | None = None, timeout: int = 20):
    """Returns (status, body). status None = no connection."""
    header = {"Content-Type": "application/json", **({"Authorization": f"Bearer {key}"} if key else {})}
    body = json.dumps(data_).encode() if data_ is not None else None
    req = urllib.request.Request(url, data=body, headers=header,
                                 method="POST" if data_ is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(2000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read(2000).decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"


def _models(basis: str, key: str) -> list[str]:
    status, body = _call(f"{basis.rstrip('/')}/models", key)
    if status != 200:
        return []
    try:
        return [m.get("id", "?") for m in (json.loads(body).get("data") or [])]
    except json.JSONDecodeError:
        return []


def check_embedder() -> None:
    basis = (os.getenv("EMBEDDER_BASE_URL") or "").rstrip("/")
    key = os.getenv("EMBEDDER_API_KEY", "")
    # Same default as src/config.py, so the check sends what the pipeline sends.
    model = os.getenv("EMBEDDER_MODEL", "default")
    print("\n── Embedder ──")
    if not basis:
        print("  EMBEDDER_BASE_URL not set — material reaches the model as excerpts only.")
        return
    print(f"  Base:   {basis}\n  Model:  {model or '(not set)'}")

    models = _models(basis if basis.endswith("/v1") else basis + "/v1", key)
    if models:
        print(f"  The server offers {len(models)} model(s):")
        for m in models[:20]:
            mark = "  ← configured" if m == model else ""
            print(f"      {m}{mark}")
        if model and model not in models:
            print(f"  ⚠️  EMBEDDER_MODEL={model!r} is NOT in this list.")
    else:
        print("  /v1/models does not answer — does the base URL point to the right service?")

    without_v1 = basis[:-3].rstrip("/") if basis.endswith("/v1") else basis
    paths, seen = [], set()
    for u in (f"{basis}/embeddings", f"{basis}/embed",
              f"{without_v1}/v1/embeddings", f"{without_v1}/embeddings", f"{without_v1}/embed"):
        if u not in seen:
            seen.add(u); paths.append(u)

    print("  Route probes:")
    for u in paths:
        status, body = _call(u, key, {"model": model or "default", "input": ["test"]})
        interpretation = {
            200: "OK — works",
            404: "route does not exist",
            401: "key rejected (EMBEDDER_API_KEY)",
            403: "access denied",
            400: "route exists, call rejected — usually a wrong model name",
            422: "route exists, payload rejected",
        }.get(status, "unexpected" if status else "no connection")
        print(f"      {str(status):>5}  {interpretation:<45} {u}")
        if status not in (None, 200, 404):
            print(f"             answer: {body[:160]}")
        if status == 200:
            return


def check_llm() -> None:
    print("\n── Language models ──")
    for role, prefix in (("LLM1 (strong)", "LLM1"), ("LLM2 (fast)", "LLM2")):
        basis = (os.getenv(f"{prefix}_BASE_URL") or "").rstrip("/")
        if not basis:
            print(f"  {role}: not set"
                  + (" — LLM1 is used" if prefix == "LLM2" else ""))
            continue
        model = os.getenv(f"{prefix}_MODEL", "")
        family = os.getenv(f"{prefix}_FAMILY", "generic")
        valid = {"qwen3", "kimi_k2", "glm", "gemma4", "generic"}
        models = _models(basis if basis.endswith("/v1") else basis + "/v1",
                           os.getenv(f"{prefix}_API_KEY", ""))
        print(f"  {role}: {basis}")
        print(f"      model {model!r}"
              + ("" if not models else
                 "  ✓ available" if model in models else
                 f"  ⚠️ NOT in the server's list ({', '.join(models[:6])})"))
        if family not in valid:
            print((f"      ⚠️ {prefix}_FAMILY={family!r} is invalid "
                   f"— valid: {', '.join(sorted(valid))}. "
                   f"Otherwise the thinking control does not apply."))


def check_reranker() -> None:
    basis = (os.getenv("RERANKER_BASE_URL") or "").rstrip("/")
    print("\n── Reranker ──")
    if not basis:
        print("  Not set — retrieval gives a ranking without a relevance cut.")
        return
    status, body = _call(basis, os.getenv("RERANKER_API_KEY", ""),
                         {"query": "test", "documents": ["a", "b"], "top_n": 1})
    print(f"  {basis}\n      HTTP {status}"
          + ("  OK" if status == 200 else f"  — {body[:160]}"))


if __name__ == "__main__":
    print("LernWerkstatt service check")
    check_llm()
    check_embedder()
    check_reranker()
    print(("\nNote: without an embedder production continues — uploaded material\n"
           "then reaches planning only as excerpts, and material coverage is skipped."))
