# -*- coding: utf-8 -*-
"""Embedder and reranker requests, as they go over the wire.

Local embedding and rerank services usually run without a key. An empty
key must therefore produce no Authorization header at all: "Bearer " with
nothing after it is an illegal header value, and httpx refuses to send the
request, so neither service would ever work without a key.
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests._optional import installed  # noqa: E402


def _transport(seen):
    import httpx

    def handle(request):
        seen.append(dict(request.headers))
        body = json.loads(request.content or b"{}")
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "m"}]})
        if request.url.path.endswith("/embeddings"):
            return httpx.Response(200, json={"data": [{"index": i, "embedding": [1.0, 0.0]}
                                                      for i, _ in enumerate(body["input"])]})
        return httpx.Response(200, json={"results": [{"index": 0, "relevance_score": 0.9}]})
    return httpx.MockTransport(handle)


def _run(key):
    import httpx
    from src.pipeline.inventory import EmbedderClient, RerankerClient
    seen = []
    emb = EmbedderClient("http://embed.test/v1", key, "m")
    emb._client = httpx.AsyncClient(transport=_transport(seen))
    rr = RerankerClient("http://rerank.test/rerank", key)
    rr._client = httpx.AsyncClient(transport=_transport(seen))
    vectors = asyncio.run(emb.embed(["a", "b"]))
    scored = asyncio.run(rr.rerank_scored("q", ["d1", "d2"], top_k=1))
    return vectors, scored, seen


def test_without_key():
    if not installed("httpx"):
        print("  ---  httpx not installed, skipped")
        return
    vectors, scored, seen = _run("")
    assert vectors and len(vectors) == 2, f"no vectors without a key: {vectors!r}"
    assert scored, "no reranker score without a key"
    assert all("authorization" not in h for h in seen), "Authorization header sent without a key"
    print("  ok   embedder and reranker work without a key, no Authorization header")


def test_with_key():
    if not installed("httpx"):
        print("  ---  httpx not installed, skipped")
        return
    _, _, seen = _run("secret")
    assert seen and all(h.get("authorization") == "Bearer secret" for h in seen)
    print("  ok   with a key every request carries it")


if __name__ == "__main__":
    test_without_key()
    test_with_key()
    print("INVENTORY HTTP OK")
