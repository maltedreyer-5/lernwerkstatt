# -*- coding: utf-8 -*-
"""The LLM client against a real HTTP endpoint (a local fake).

The other tests replace the client with a mock, so they would not notice a
change in the openai SDK. This test sends real requests to a minimal
OpenAI-compatible server on localhost and checks what arrives there. It
needs the installed openai package and is skipped without it.
"""
import asyncio
import http.server
import json
import sys
import threading
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _optional import installed  # noqa: E402

RECEIVED: list[dict] = []


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802 — name fixed by BaseHTTPRequestHandler
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        RECEIVED.append({"body": body, "auth": self.headers.get("Authorization")})
        out = json.dumps({
            "id": "x", "object": "chat.completion", "created": 0, "model": body["model"],
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": '{"ok": true}'}}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *args):
        pass


def test_requests_reach_the_endpoint():
    if not installed("openai"):
        print("  ---  openai not installed, skipped")
        return
    from src.llm.client import LLMClient
    server = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}/v1"
    try:
        # An empty key must work: endpoints without authentication are
        # configured that way, and newer SDK versions reject an empty key.
        client = LLMClient(url, "", "test-model", family="qwen3", max_retries=0)
        answer = asyncio.run(client.complete("hello", json_mode=True))
        assert answer == '{"ok": true}', answer
        sent = RECEIVED[-1]["body"]
        assert sent["model"] == "test-model"
        assert sent.get("response_format", {}).get("type") == "json_object", sent
        assert sent.get("chat_template_kwargs") == {"enable_thinking": False}, sent
        assert client._client.max_retries == 0, "SDK retries must stay off"
    finally:
        server.shutdown()
    print("  ok   request, JSON mode and thinking switch arrive at the endpoint")


if __name__ == "__main__":
    test_requests_reach_the_endpoint()
    print("LLM HTTP OK")
