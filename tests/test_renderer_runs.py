# -*- coding: utf-8 -*-
"""Actually runs the renderers of the delivered unit.

A file can open without a single script running — no navigation, no
exercises, no search — if a change breaks the embedded JavaScript (a
backtick INSIDE a template literal, for instance). Checking that no German
text remains says nothing about whether the file still works.

This test builds a unit with ALL block types, loads the embedded script into
Node with a minimal browser mock and calls every renderer. It thus catches
syntax errors AND run-time errors while drawing.
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.unit.assembler import assemble  # noqa: E402

BLOCKS = [
    {"type": "text", "html": "<p>Ein Absatz.</p>"},
    {"type": "note", "variant": "info", "html": "<p>Ein Hinweis.</p>"},
    {"type": "table", "header": ["A", "B"], "rows": [["1", "2"]],
     "caption": "Vergleich der Verfahren"},
    {"type": "accordion", "items": [{"title": "T", "html": "<p>Inhalt.</p>"}]},
    {"type": "code", "language": "python", "content": "print(1)"},
    {"type": "diagram", "engine": "mermaid", "code": "flowchart LR\n  A-->B",
     "description": "Der Ablauf im Überblick dargestellt"},
    {"type": "chart", "engine": "chartjs",
     "description": "Verlauf der Werte über die Zeit",
     "spec": {"type": "line", "data": {"labels": ["a", "b"],
                                       "datasets": [{"label": "L", "data": [1, 2]}]}}},
    {"type": "chart", "engine": "vegalite",
     "description": "Stelle K auf verschiedene Werte und beobachte den Verlauf",
     "spec": {"data": {"values": [{"x": 1, "y": 2}]}, "mark": "line",
              "encoding": {"x": {"field": "x", "type": "quantitative"},
                           "y": {"field": "y", "type": "quantitative"}},
              "params": [{"name": "k", "value": 1,
                          "bind": {"input": "range", "name": "K", "min": 0, "max": 2}}]}},
    {"type": "formula", "latex": "E = mc^2",
     "description": "Die Äquivalenz von Masse und Energie"},
    {"type": "quiz", "questions": [{"question": "F?", "options": [
        {"text": "A", "correct": True, "feedback": "x"},
        {"text": "B", "correct": False, "feedback": "y"}]}]},
    {"type": "cloze", "html": "<p>Ein {{1}} Satz.</p>",
     "gaps": {"1": {"answers": ["kurzer"]}}},
    {"type": "matching", "task": "Ordne zu",
     "pairs": [{"left": "L1", "right": "R1"}, {"left": "L2", "right": "R2"}]},
    {"type": "flashcards", "cards": [{"front": "V", "back": "H"},
                                     {"front": "V2", "back": "H2"}]},
    {"type": "prediction", "question": "Was passiert?", "resolution": "Das hier."},
    {"type": "simulator", "title": "S",
     "description": "Stelle X ein und beobachte Y",
     "code": "function berechne(p){return {y: p.x*2};}",
     "parameters": [{"name": "x", "label": "X", "min": 0, "max": 10,
                    "step": 1, "value": 5}],
     "output": {"kind": "line", "x_label": "X", "y_label": "Y"}},
    {"type": "widget", "html": "<p>Widget</p>",
     "description": "Ein gekapseltes Element zur Erkundung"},
    {"type": "task", "title": "A", "task": "Tu dies.",
     "sample_solution": "So geht es."},
    {"type": "error_analysis", "title": "F", "question": "Was ist falsch?",
     "material": "Text", "sample_solution": "Das."},
]


def check(b, name):
    print(f"  {'ok  ' if b else 'FAIL'} {name}")
    return 0 if b else 1


def _unit(language: str = "de") -> dict:
    return {"id": "alle", "title": "Alle Blocktypen", "language": language,
            "state": "final", "depth_profile": "compact", "duration_minutes": 10,
            "learning_objectives": ["Z"], "concepts": [],
            "glossary": [{"term": "B", "short": "K", "definition": "D"}],
            "lessons": [{"id": "l1", "title": "L", "concepts": [],
                           "blocks": [dict(b) for b in BLOCKS]}],
            "modules": [{"title": "M", "lessons": ["l1"],
                        "exercises": [dict(BLOCKS[-2]), dict(BLOCKS[-1])]}]}


def _probe(language: str) -> tuple[int, dict]:
    res = assemble(_unit(language), Path(tempfile.mkdtemp()))
    html = Path(getattr(res, "path_", res)).read_text(encoding="utf-8")
    js = re.findall(r"<script(?![^>]*src=)[^>]*>(.*?)</script>", html, re.S)
    tmp = Path(tempfile.mkdtemp())
    (tmp / "shell.js").write_text(js[-1], encoding="utf-8")
    r = subprocess.run(["node", str(ROOT / "assets" / "render_probe.mjs"),
                        str(tmp / "shell.js")],
                       capture_output=True, text=True, timeout=60)
    # The probe outputs multi-line JSON — collect from the end until it parses
    # instead of taking only the last line.
    rows = r.stdout.strip().splitlines()
    for i in range(len(rows)):
        try:
            return r.returncode, json.loads("\n".join(rows[i:]))
        except json.JSONDecodeError:
            continue
    return r.returncode, {"fatal": (r.stdout + r.stderr)[:300]}


def test_alle_renderer():
    print("run the renderers of all block types")
    if not shutil.which("node"):
        print("  ---  node missing, renderers unchecked")
        return 0
    f = 0
    for language in ("de", "en"):
        code, res = _probe(language)
        if res.get("fatal"):
            f += check(False, f"{language}: {res['fatal'][:110]}")
            continue
        f += check(not res.get("errors"),
                    f"{language}: {res.get('checked', 0)} blocks drawn"
                    + (f" — {res['errors'][:2]}" if res.get("errors") else ""))
        f += check(len(res.get("types") or []) >= 16,
                    f"{language}: {len(res.get('types') or [])} block types covered")
    return f


if __name__ == "__main__":
    errors = test_alle_renderer()
    print(f"\n{'RENDERER OK' if not errors else f'{errors} FAILED'}")
    sys.exit(1 if errors else 0)
