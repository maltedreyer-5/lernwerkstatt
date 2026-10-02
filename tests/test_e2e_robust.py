# -*- coding: utf-8 -*-
"""Complete run with FAULTY model answers.

The other E2E test works with well-formed answers and produces only `text`
and `quiz`. The fault forms that real models produce never occur there —
each one is repaired and tested on its own, but not in combination.

This test sends all of them through in ONE run:

  1. `beschriftung` instead of `description` (would block delivery)
  2. invented block type `grafik`             (would end up in degradation)
  3. `<s>` and `<pad>` as a flashcard side    (would be deleted → empty cards)
  4. literal "\\n" sequences in task material  (visible to the learner)
  5. LaTeX `q_{m+1}` in a description         (would survive degradation)
  6. Mermaid stadium `A([Start])`             (would become `A("[Start]")`)
  7. categorisation with few target values    (would count as an error)
  8. Vega parameter without a label           (a warning nobody fixes)
  9. Markdown remnants in escaped fields
 10. `new_terms` as a list of strings        (would take a whole chapter down)

It checks not only that nothing crashes, but that every defect has ACTUALLY
been fixed — and that the finished file works at the end.
"""
import asyncio
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from mock_llm import MockLLM
from src.llm.legacy_keys import translate_legacy_keys  # noqa: E402

from src.pipeline.learning_pipeline import LearningPipeline  # noqa: E402
from src.unit.assembler import assemble  # noqa: E402

B = chr(92)


class HostileMock(MockLLM):
    """Delivers, for block generation, everything real models get wrong."""

    # Class-wide: `strong` and `fast` serve the same lessons, otherwise every
    # instance would keep its own books.
    _contaminated: set = set()

    def __init__(self, *a, **k):
        super().__init__(*a, **k)

    def _response(self, p: str) -> str:
        response = super()._response(p)
        # Contaminate only the generation of lesson blocks, and exactly once
        # per lesson — the repair run calls the same place again.
        if not ('"blocks"' in response or '"bloecke"' in response) or "Kernprinzip?" not in response:
            return self._terms_contaminate(p, response)
        mark = re.search(r'"id"\s*:\s*"([^"]+)"', response)
        mark = mark.group(1) if mark else str(len(self._contaminated))
        if mark in HostileMock._contaminated:
            return response
        HostileMock._contaminated.add(mark)
        # The base mock may still answer with the German field names of the
        # prompts; bring the answer into the format first, as the parser does.
        data_ = translate_legacy_keys(json.loads(response))
        data_["blocks"].extend([
            # 1 · alternative text under a wrong field name
            {"type": "diagram", "engine": "mermaid",
             # 6 · stadium nodes and brackets in the label
             "code": "flowchart LR\n  A([Start des Verfahrens]) --> B[Prüfung (formal)]",
             "caption": "Der Ablauf des Verfahrens im Überblick"},
            # 2 · invented block type with Mermaid content
            {"type": "grafik", "engine": "mermaid",
             "code": "stateDiagram-v2\n  [*] --> Offen\n  Offen --> Zu: Reiz",
             "description": "Zustände und ihre Übergänge im Regelkreis"},
            # 3 · special token as the front of a card
            {"type": "flashcards", "cards": [
                {"front": "<s>", "back": "Markiert den Beginn einer Sequenz."},
                {"front": "<pad>", "back": "Füllt kürzere Sequenzen auf."}]},
            # 4 · literale Escape-Folgen im Material
            {"type": "error_analysis", "title": "Fehler finden",
             "question": "Was stimmt hier nicht?",
             "material": "Eigenkapital: 1.200 TEUR" + B + "n" + B + "nSchritt 1: prüfen",
             "sample_solution": "Die Steuerabgrenzung fehlt."},
            # 5 · LaTeX in a description
            {"type": "formula", "latex": "a^2 + b^2 = c^2",
             "description": "Der Zusammenhang zwischen q_{m+1} und den Katheten"},
            # 7 · categorisation: few target values, many statements
            {"type": "matching", "task": "Ordne die Aussagen zu", "pairs": [
                {"left": "**Trägt** die Bedeutung", "right": "Embedding"},
                {"left": "Kodiert die Reihenfolge", "right": "Positional Encoding"},
                {"left": "Bleibt je Wort gleich", "right": "Embedding"},
                {"left": "Ändert sich bei Vertauschung", "right": "Positional Encoding"}]},
            # 8 · Vega parameter without a label
            {"type": "chart", "engine": "vegalite",
             "description": "Stelle alpha ein und beobachte den Verlauf",
             "spec": {"data": {"values": [{"x": 1, "y": 2}, {"x": 2, "y": 4}]},
                      "mark": "line",
                      "transform": [{"calculate": "datum.y * alpha_slider",
                                     "as": "skaliert"}],
                      "encoding": {"x": {"field": "x", "type": "quantitative"},
                                   "y": {"field": "skaliert", "type": "quantitative"}},
                      "params": [{"name": "alpha_slider", "value": 1,
                                  "bind": {"input": "range", "min": 0, "max": 2}}]}},
            # 9 · Markdown in an escaped field
            {"type": "table", "header": ["*Merkmal*", "Wert"],
             "rows": [["**Fett**", "1"]], "caption": "Übersicht der Merkmale"},
        ])
        return json.dumps(data_, ensure_ascii=False)

    def _terms_contaminate(self, p: str, response: str) -> str:
        """10 · `new_terms` as a list of strings instead of objects.

        Unchecked that breaks a whole chapter with `'str' object has no
        attribute 'get'`.
        """
        if "new_terms" not in response:
            return response
        try:
            data_ = json.loads(response)
        except json.JSONDecodeError:
            return response
        if isinstance(data_, dict) and data_.get("new_terms"):
            data_["new_terms"] = ["Regelschleife", "Soll-Zustand"]
            return json.dumps(data_, ensure_ascii=False)
        return response


def check(b, name):
    print(f"  {'ok  ' if b else 'FAIL'} {name}")
    return 0 if b else 1


def _blocks(unit):
    for l in unit.get("lessons") or []:
        for b in l.get("blocks") or []:
            if isinstance(b, dict):
                yield b
    for m in unit.get("modules") or []:
        for b in m.get("exercises") or []:
            if isinstance(b, dict):
                yield b


async def _run(folder: Path):
    p = LearningPipeline(HostileMock("stark"), HostileMock("schnell"),
                     work_dir=folder, job_number=1)
    await p.collect_profile("Docker-Grundlagen", "Kubernetes verstehen", 45, None)
    await p.analyse_gap()
    await p.create_teaching_script()
    p.approve([])
    await p.plan_all_chapters()
    async for _ in p.produce_all():
        pass
    async for _ in p.consolidate():
        pass
    return p, *p.finalise()


def test_hostile_run():
    print("run with faulty model answers")
    folder = Path(tempfile.mkdtemp())
    try:
        pipeline, finding, result = asyncio.run(_run(folder))
    except Exception as e:  # noqa: BLE001
        import traceback
        traceback.print_exc(limit=6)
        return check(False, f"pipeline crashed: {type(e).__name__}: {e}")

    unit = pipeline.unit
    bl = list(_blocks(unit))
    f = check(len(unit.get("lessons") or []) >= 2,
               f"{len(unit.get('lessons') or [])} lessons created")
    f += check(len(bl) >= 15, f"{len(bl)} blocks created")

    # 10 · the chapter must not have failed because of new_terms
    f += check(not pipeline.losses,
                f"no lost lessons{f' ({pipeline.losses})' if pipeline.losses else ''}")

    # 1 · alternative text under a wrong field name
    diag = [b for b in bl if b.get("type") == "diagram"]
    f += check(diag and all(b.get("description") for b in diag),
                "diagrams have an alternative text")

    # 2 · invented block type was mapped, not downgraded
    f += check(not [b for b in bl if b.get("type") == "grafik"],
                "invented block type 'grafik' resolved")
    f += check(any("stateDiagram" in (b.get("code") or "") for b in diag),
                "and kept as a state diagram")

    # 3 · special tokens on flashcards
    cards = [k for b in bl if b.get("type") == "flashcards"
              for k in (b.get("cards") or [])]
    f += check(cards and all(k.get("front") for k in cards),
                "flashcards have a front")
    f += check(any("<s>" in (k.get("front") or "") for k in cards),
                "special tokens stayed unchanged")

    # 4 · literale Escape-Folgen
    material = " ".join(b.get("material") or "" for b in bl)
    f += check(material and B + "n" not in material,
                "no literal escape sequences in the material")

    # 5 · LaTeX in descriptions
    caption_text = " ".join(b.get("description") or "" for b in bl)
    f += check("q_{" not in caption_text, "LaTeX resolved in descriptions")

    # 6 · Mermaid-Knotenformen
    codes = " ".join(b.get("code") or "" for b in diag)
    f += check("A([Start des Verfahrens])" in codes,
                "stadium node intact")
    f += check('B["Prüfung (formal)"]' in codes,
                "label with brackets quoted, shape kept")

    # 8 · controls named
    binds = [q.get("bind", {}) for b in bl if b.get("type") == "chart"
             for q in ((b.get("spec") or {}).get("params") or [])]
    f += check(binds and all(x.get("name") for x in binds),
                "all controls carry a label")

    # 9 · Markdown in escapten Feldern
    tab = [b for b in bl if b.get("type") == "table"]
    f += check(tab and not any("**" in str(z) for b in tab for z in (b.get("rows") or [])),
                "Markdown removed from table cells")

    # 7 · categorisation must not block
    f += check(not [x for x in finding.errors if "right" in x],
                "categorisation does not block")

    # Overall verdict: after all this the unit must be deliverable
    f += check(result is not None,
                "the unit was created" + (f" — {finding.errors[:2]}" if not result else ""))
    f += check(finding.passed,
                "final gate passed"
                + (f" — offen: {finding.errors[:3]}" if not finding.passed else ""))
    return f, pipeline, folder


def _delivered_file_runs(pipeline):
    """The finished file must actually work in the browser."""
    print("run the delivered file")
    if not shutil.which("node"):
        print("  ---  node missing, renderers unchecked")
        return 0
    res = assemble(pipeline.unit, Path(tempfile.mkdtemp()))
    html = Path(getattr(res, "path_", res)).read_text(encoding="utf-8")
    js = re.findall(r"<script(?![^>]*src=)[^>]*>(.*?)</script>", html, re.S)
    tmp = Path(tempfile.mkdtemp())
    (tmp / "shell.js").write_text(js[-1], encoding="utf-8")
    r = subprocess.run(["node", str(ROOT / "assets" / "render_probe.mjs"),
                        str(tmp / "shell.js")],
                       capture_output=True, text=True, timeout=60)
    rows = r.stdout.strip().splitlines()
    data_ = {}
    for i in range(len(rows)):
        try:
            data_ = json.loads("\n".join(rows[i:]))
            break
        except json.JSONDecodeError:
            continue
    if data_.get("fatal"):
        return check(False, f"script broken: {data_['fatal'][:110]}")
    f = check(not data_.get("errors"),
               f"{data_.get('checked', 0)} blocks drawn"
               + (f" — {data_['errors'][:2]}" if data_.get("errors") else ""))
    f += check(len(data_.get("types") or []) >= 8,
                f"{len(data_.get('types') or [])} block types in the run")
    return f


if __name__ == "__main__":
    result = test_hostile_run()
    if isinstance(result, tuple):
        errors, pipeline, folder = result
        errors += _delivered_file_runs(pipeline)
        shutil.rmtree(folder, ignore_errors=True)
    else:
        errors = result
    print(f"\n{'ROBUSTNESS OK' if not errors else f'{errors} FAILED'}")
    sys.exit(1 if errors else 0)
