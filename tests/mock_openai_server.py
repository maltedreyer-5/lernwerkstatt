"""OpenAI-compatible test server backed by the deterministic mock of the test suite.

Usage:  python tests/mock_openai_server.py PORT [CALL_LOG]

Routes: GET /v1/models, POST /v1/chat/completions (also streaming),
POST /v1/embeddings, POST /rerank. One MockLLM instance per model name, so
the strong and the fast role keep separate state as with real endpoints.
"""
import hashlib, json, math, re, sys, threading, time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
from tests.mock_llm import MockLLM

LOCK = threading.RLock()
MOCKS: dict[str, MockLLM] = {}
LOG = open(sys.argv[2], "a", buffering=1) if len(sys.argv) > 2 else open(__import__("os").devnull, "w")

def mock_for(model):
    with LOCK:
        if model not in MOCKS:
            MOCKS[model] = MockLLM(model)
        return MOCKS[model]

def vec(text, dim=64):
    v = [0.0] * dim
    for w in re.findall(r"\w{3,}", text.lower()):
        h = int(hashlib.md5(w.encode()).hexdigest(), 16)
        v[h % dim] += 1.0
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        if self.path.rstrip("/").endswith("/models"):
            return self._json(200, {"object": "list", "data": [{"id": m, "object": "model"}
                                     for m in ("mock-strong", "mock-fast", "mock-embed")]})
        self._json(404, {"error": "not found"})
    def do_POST(self):
        data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        if self.path.endswith("/chat/completions"):
            msgs = data.get("messages", [])
            prompt = "\n".join(m["content"] for m in msgs if m.get("role") == "user")
            model = data.get("model", "mock")
            try:
                with LOCK:
                    text = mock_for(model)._response(prompt)
            except AssertionError as e:
                LOG.write(json.dumps({"model": model, "unknown_prompt": prompt[:120]}) + "\n")
                return self._json(500, {"error": {"message": str(e)[:200]}})
            LOG.write(json.dumps({"model": model, "first_line": prompt.split("\n", 1)[0][:90],
                                  "lang_rule": "LANGUAGE RULE" in prompt,
                                  "json_mode": bool(data.get("response_format")),
                                  "extra": data.get("chat_template_kwargs") or data.get("reasoning_effort")}) + "\n")
            usage = {"prompt_tokens": len(prompt) // 4, "completion_tokens": len(text) // 4,
                     "total_tokens": (len(prompt) + len(text)) // 4}
            if data.get("stream"):
                self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
                for i in range(0, len(text), 400):
                    chunk = {"id": "c", "object": "chat.completion.chunk", "created": int(time.time()), "model": model,
                             "choices": [{"index": 0, "delta": {"content": text[i:i + 400]}, "finish_reason": None}]}
                    self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
                end = {"id": "c", "object": "chat.completion.chunk", "created": int(time.time()), "model": model,
                       "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}
                self.wfile.write(f"data: {json.dumps(end)}\n\ndata: [DONE]\n\n".encode()); return
            return self._json(200, {"id": "c", "object": "chat.completion", "created": int(time.time()),
                                    "model": model, "usage": usage,
                                    "choices": [{"index": 0, "finish_reason": "stop",
                                                 "message": {"role": "assistant", "content": text}}]})
        if self.path.endswith("/embeddings"):
            inp = data.get("input"); inp = [inp] if isinstance(inp, str) else inp
            return self._json(200, {"object": "list", "model": data.get("model"),
                                    "data": [{"object": "embedding", "index": i, "embedding": vec(t)}
                                             for i, t in enumerate(inp)]})
        if self.path.endswith("/rerank"):
            q = set(re.findall(r"\w{4,}", data["query"].lower()))
            res = []
            for i, d in enumerate(data["documents"]):
                w = set(re.findall(r"\w{4,}", d.lower()))
                res.append({"index": i, "relevance_score": round(len(q & w) / (len(q) or 1), 3)})
            res.sort(key=lambda r: -r["relevance_score"])
            return self._json(200, {"results": res[: data.get("top_n") or len(res)]})
        self._json(404, {"error": "not found"})

if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
