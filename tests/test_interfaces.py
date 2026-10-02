# -*- coding: utf-8 -*-
"""Interface tests for the client, DAG and config modules.

Catches constructor/API drift WITHOUT an installed LLM stack: signatures are
read from the source via AST (client.py imports openai and cannot be imported
in environments without dependencies).
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

# src/ui/wizard.py::_client_from reads these fields from the LLMConfig block
# and passes them as keyword arguments to LLMClient(...).
USED_FIELDS = ("base_url", "api_key", "model", "family", "thinking",
                   "max_tokens", "temperature", "timeout", "max_concurrent")


def _init_params(source_file: Path, concept_class: str) -> set[str]:
    tree = ast.parse(source_file.read_text(encoding="utf-8"))
    for nodes in ast.walk(tree):
        if isinstance(nodes, ast.ClassDef) and nodes.name == concept_class:
            for fn in nodes.body:
                if isinstance(fn, ast.FunctionDef) and fn.name == "__init__":
                    return {a.arg for a in fn.args.args + fn.args.kwonlyargs} - {"self"}
    raise AssertionError(f"{concept_class}.__init__ nicht gefunden in {source_file}")


def test_llmclient_signature_matches_wizard():
    params = _init_params(REPO / "src" / "llm" / "client.py", "LLMClient")
    missing = set(USED_FIELDS) - params
    assert not missing, f"the wizard passes arguments LLMClient does not know: {missing}"


def test_llmconfig_has_all_used_fields():
    from src.config import load_config
    cfg = load_config()  # without .env: empty strings/defaults — the attributes exist
    for field_ in USED_FIELDS:
        assert hasattr(cfg.llm1, field_), f"LLMConfig without field '{field_}'"


def test_stop_signal_api():
    from src.core.stop_signal import StopSignal
    s = StopSignal()
    assert s.is_stopped is False
    s.request()
    assert s.is_stopped is True


def test_dagtask_fields_as_used_by_pipeline():
    params = _init_params(REPO / "src" / "pipeline" / "dag.py", "DAGTask") \
        if False else None
    # DAGTask is a @dataclass — check fields instead of __init__:
    tree = ast.parse((REPO / "src" / "pipeline" / "dag.py").read_text(encoding="utf-8"))
    fields_ = set()
    for nodes in ast.walk(tree):
        if isinstance(nodes, ast.ClassDef) and nodes.name == "DAGTask":
            fields_ = {z.target.id for z in nodes.body
                      if isinstance(z, ast.AnnAssign) and isinstance(z.target, ast.Name)}
    for f in ("id", "phase", "title", "prompt", "depends_on", "use_primary",
              "max_retries", "check_criteria"):
        assert f in fields_, f"DAGTask without field '{f}'"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn(); print(f"OK  {name}")
    print("\n4 tests passed.")
