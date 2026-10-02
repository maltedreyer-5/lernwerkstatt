"""LernWerkstatt — entry point: starts the wizard.

Behind the nginx reverse proxy the app runs under a path prefix
(APP_ROOT_PATH, e.g. /lernwerkstatt); locally without a prefix, simply
`python app.py`.
"""
import os

# Must be set before gradio is imported: Gradio reads it at import time and
# otherwise sends usage analytics to its vendor. The container image sets it
# too; this covers every other way of starting the application.
os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")

from src.ui.wizard import build_ui  # noqa: E402


def _service_diagnosis() -> dict[str, str]:
    """Checks embedder and reranker at start-up.

    Without this check it would only show in the middle of production that
    the uploaded material could not be indexed at all — and then only as a
    line in the log.
    """
    import asyncio
    from src.config import load_config
    cfg = load_config()
    result: dict[str, str] = {}

    emb = cfg.embedder.base_url
    if not emb:
        result["embedder"] = "not configured — material reaches the model as excerpts only"
    else:
        try:
            from src.pipeline.inventory import EmbedderClient
            c = EmbedderClient(emb, cfg.embedder.api_key, cfg.embedder.model)
            vec = asyncio.run(c.embed(["test"]))
            result["embedder"] = ("operational" if vec and vec[0]
                                    else "no vectors received — see the message above")
        except Exception as e:  # noqa: BLE001
            result["embedder"] = f"cannot be checked: {type(e).__name__}: {e}"

    rer = cfg.reranker.base_url
    if not rer:
        result["reranker"] = ("not configured — retrieval ranks without a relevance cut")
    else:
        try:
            from src.pipeline.inventory import RerankerClient
            c = RerankerClient(rer, cfg.reranker.api_key, cfg.reranker.model)
            hits = asyncio.run(c.rerank_scored(
                "test query", ["first document", "second document"], top_k=1))
            result["reranker"] = (
                f"operational (score {hits[0][1]:.2f})" if hits
                else "no score received — see the message above; expected format: "
                     "results[].relevance_score")
        except Exception as e:  # noqa: BLE001
            result["reranker"] = f"cannot be checked: {type(e).__name__}: {e}"
    return result


def _startup_diagnosis() -> None:
    """Reports at start-up which Node probes are operational.

    Without this output a missing build-time dependency would go unnoticed:
    in operation there would only be an unspecific warning per diagram.
    """
    from src import __version__
    print(f"[startup] LernWerkstatt {__version__}", flush=True)
    try:
        import shutil as _sh
        import subprocess as _sp
        if _sh.which("node"):
            try:
                v = _sp.run(["node", "--version"], capture_output=True,
                            text=True, timeout=10).stdout.strip()
                print(f"[startup] node: {v}", flush=True)
            except Exception:  # noqa: BLE001
                pass
        from src.unit.validator import probe_diagnose
        for name, state in probe_diagnose().items():
            print(f"[startup] {name}: {state}", flush=True)
        for name, state in _service_diagnosis().items():
            print(f"[startup] {name}: {state}", flush=True)
    except Exception as e:  # noqa: BLE001 — must never prevent start-up
        print(f"[startup] not possible: {e}", flush=True)

if __name__ == "__main__":
    from src.config import load_config
    cfg = load_config()
    _startup_diagnosis()
    build_ui().launch(
        server_name=cfg.server_name,
        server_port=cfg.server_port,
        root_path=cfg.root_path or None,
        max_file_size=f"{cfg.max_upload_mb}mb",
    )
