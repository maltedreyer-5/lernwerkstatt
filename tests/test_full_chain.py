# -*- coding: utf-8 -*-
"""Integration test across the whole chain up to the delivered file.

The other tests check that nothing crashes. This one checks whether the
result is RIGHT: whether the repair chain turns contaminated model output
into a deliverable unit, whether the assembled file contains the unit
intact, and whether the drawn components keep their promises — as many input
fields as gaps, deduplicated selection, embedded libraries.

Order as in the application: type alias -> field alias -> normalisation ->
validation -> degradation -> assembly.
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

for _m in ("openai", "httpx"):
    if _m not in sys.modules:
        try:
            __import__(_m)
        except ImportError:
            _mod = types.ModuleType(_m)
            _mod.__getattr__ = lambda a: object  # type: ignore[attr-defined]
            sys.modules[_m] = _mod

from src.pipeline.learning_pipeline import _resolve_field_aliases  # noqa: E402
from src.unit import degradation as degr  # noqa: E402
from src.unit.assembler import assemble  # noqa: E402
from src.unit.normalization import normalise_unit  # noqa: E402
from src.unit.validator import validate  # noqa: E402


def check(b, name):
    print(f"  {'ok  ' if b else 'FAIL'} {name}")
    return 0 if b else 1


# ── A unit as a model REALLY delivers it: with alias names, Markdown
#    remnants, literal escapes, invented types, LaTeX in text fields and one
#    component that is broken beyond rescue.
def _raw_unit() -> dict:
    B = chr(92)
    return {
        "id": "kette", "title": "Gesamtkette", "language": "de", "state": "final",
        "depth_profile": "compact", "duration_minutes": 20, "learning_objectives": ["Z1"],
        "concepts": [{"id": "k1", "name": "Wasserpotential", "concept_class": "V",
                      "rationale": "tragend"}],
        "glossary": [{"term": "Wasserpotential", "short": "Kurzform",
                     "definition": "Die **Definition**."}],
        "lessons": [{"id": "l1", "title": "Lektion", "concepts": ["k1"], "blocks": [
            # Markdown-Rest in HTML
            {"type": "text", "html": "<p>Das **Wasserpotential** Ψ_{s} steuert alles.</p>"},
            # invented type with Mermaid source + bracket in the label
            {"type": "grafik", "engine": "mermaid",
             "code": "flowchart LR\n  A([Start (Boden)]) --> B[Xylem]",
             "caption": "Der Weg des Wassers von der Wurzel bis zum Blatt"},
            # special tokens that look like tags
            {"type": "flashcards", "cards": [
                {"front": "<s>", "back": "Beginn einer Sequenz."},
                {"front": "<pad>", "back": "Füllt auf."}]},
            # categorisation with repeated target value
            {"type": "matching", "task": "Ordne zu", "pairs": [
                {"left": "**A1**", "right": "Gruppe X"},
                {"left": "A2", "right": "Gruppe X"},
                {"left": "A3", "right": "Gruppe Y"}]},
            # control without a label
            {"type": "chart", "engine": "vegalite",
             "description": "Stelle Alpha ein und beobachte den Verlauf",
             "spec": {"data": {"values": [{"x": 1, "y": 2}, {"x": 2, "y": 4}]},
                      "transform": [{"calculate": "datum.y * alpha_slider", "as": "sk"}],
                      "mark": "line",
                      "encoding": {"x": {"field": "x", "type": "quantitative"},
                                   "y": {"field": "sk", "type": "quantitative"}},
                      "params": [{"name": "alpha_slider", "value": 1,
                                  "bind": {"input": "range", "min": 0, "max": 2}}]}},
            # cloze with two gaps
            {"type": "cloze", "html": "<p>Von {{1}} nach {{2}}.</p>",
             "gaps": {"1": {"answers": ["Wurzel"]}, "2": {"answers": ["Blatt"]}}},
            # quiz with three options
            {"type": "quiz", "questions": [{"question": "Warum?", "options": [
                {"text": "A", "correct": True, "feedback": "richtig"},
                {"text": "B", "correct": False, "feedback": "falsch"},
                {"text": "C", "correct": False, "feedback": "falsch"}]}]},
            # beyond rescue: formula without LaTeX, but with a usable
            # description
            {"type": "formula", "description": "Die Bilanzgleichung des Wasserhaushalts"},
        ]}],
        "modules": [{"title": "Modul", "lessons": ["l1"], "exercises": [
            {"type": "error_analysis", "title": "F", "question": "Was stimmt nicht?",
             "material": "Zeile 1" + B + "nZeile 2", "sample_solution": "Das."}]}],
        "final_test": {"questions": [{"question": "F?", "options": [
            {"text": "A", "correct": True, "feedback": "x"},
            {"text": "B", "correct": False, "feedback": "y"}]}]},
    }


def _chain(unit: dict):
    """The route through the application, in exactly this order."""
    for l in unit["lessons"]:
        for b in l["blocks"]:
            _resolve_field_aliases(b)
    for m in unit.get("modules") or []:
        for b in m.get("exercises") or []:
            _resolve_field_aliases(b)
    log_ = normalise_unit(unit)
    finding = validate(unit, node_probe=False)
    replaced = degr.downgrade(unit, finding)
    if replaced:
        finding = validate(unit, node_probe=False)
    return log_, finding, replaced


def test_repair_chain():
    print("repair chain: contaminated output becomes deliverable")
    u = _raw_unit()
    prior = validate(json.loads(json.dumps(u)), node_probe=False)
    log_, finding, replaced = _chain(u)
    f = check(prior.errors, f"raw: {len(prior.errors)} errors (starting point)")
    real = [x for x in finding.errors if "formula could not" not in x]
    f += check(not real, f"free of errors after the chain"
                + (f" — offen: {real[:2]}" if real else ""))

    bl = u["lessons"][0]["blocks"]
    f += check(bl[1]["type"] == "diagram", "invented type 'grafik' was mapped")
    f += check("A([" in bl[1]["code"], "stadium node shape was kept")
    f += check(bl[1].get("description"), "beschriftung became description")
    f += check(all(k["front"] for k in bl[2]["cards"]),
                "special tokens on the cards survived")
    f += check("**" not in bl[3]["pairs"][0]["left"],
                "Markdown removed in matching pairs")
    f += check(bl[4]["spec"]["params"][0]["bind"].get("name"),
                "control was named")
    f += check("**" not in bl[0]["html"] and "Ψ" in bl[0]["html"],
                "Markdown removed, formula characters kept")
    mat = u["modules"][0]["exercises"][0]["material"]
    f += check(chr(92) not in mat, "literal escape sequence in the material resolved")
    f += check(len(replaced) == 1 and "formula" in str(replaced[0]),
                f"exactly the component beyond rescue was downgraded ({len(replaced)})")
    f += check(bl[4]["type"] == "chart", "the usable chart stayed a chart")

    # Counter-check: a dead slider IS an error and gets downgraded.
    tot = _raw_unit()
    tot["lessons"][0]["blocks"][4]["spec"].pop("transform")
    tot["lessons"][0]["blocks"][4]["spec"]["encoding"]["y"]["field"] = "y"
    _, bt, et = _chain(tot)
    f += check(any("chart" in str(x) for x in et),
                "a dead slider leads to the downgrade")
    return f


def test_assembly_roundtrip():
    """The assembled file must contain the unit intact."""
    print("assembly: round trip through the delivered file")
    u = _raw_unit()
    _chain(u)
    res = assemble(u, Path(tempfile.mkdtemp()))
    html = Path(getattr(res, "path_", res)).read_text(encoding="utf-8")

    m = re.search(r"const UNIT\s*=\s*(\{.*?\});\s*\n", html, re.S)
    f = check(m, "UNIT can be read again")
    if not m:
        return f
    back = json.loads(m.group(1))
    f += check(back["id"] == u["id"], "identifier unchanged")
    f += check(len(back["lessons"][0]["blocks"])
                == len(u["lessons"][0]["blocks"]), "number of blocks unchanged")
    f += check(not validate(back, node_probe=False).errors
                or all("formula could not" in x
                       for x in validate(back, node_probe=False).errors),
                "the unit read back is still valid")
    f += check("</script" not in json.dumps(back),
                "no unmasked </script in the data")

    # Embedded libraries instead of fetching from third parties. Without
    # `assets/vendor` the assembler deliberately falls back to a CDN — then the
    # file is not usable offline, and that is a statement about the
    # ENVIRONMENT, not about the application. The Docker build fills the
    # directory.
    vendor = ROOT / "assets" / "vendor"
    has_vendor = vendor.exists() and any(vendor.glob("*.js"))
    if has_vendor:
        f += check("cdn.jsdelivr" not in html and "unpkg.com" not in html,
                    "no CDN references — the file works offline")
    else:
        print("  ---  assets/vendor empty: CDN fallback expected, offline unchecked")
    f += check("mermaid" in html.lower(), "Mermaid is embedded")
    f += check(html.count("<script") >= 2, "renderer libraries present")
    # Glossary terms are marked during assembly and lie JSON-escaped in the
    # data — so do not search for the raw attribute.
    f += check('class="term"' in html.replace(chr(92), ""),
                "glossary terms marked in the text")
    f += check('data-term=' in html.replace(chr(92), ""), "the marking carries its anchor")
    return f


def test_components_keep_promises():
    """The drawn HTML must match the data structure."""
    print("drawn components against their data structure")
    if not shutil.which("node"):
        print("  ---  node missing, HTML promises unchecked")
        return 0
    u = _raw_unit()
    _chain(u)
    res = assemble(u, Path(tempfile.mkdtemp()))
    html_file = Path(getattr(res, "path_", res)).read_text(encoding="utf-8")
    js = re.findall(r"<script(?![^>]*src=)[^>]*>(.*?)</script>", html_file, re.S)[-1]
    tmp = Path(tempfile.mkdtemp())
    (tmp / "shell.js").write_text(js, encoding="utf-8")
    r = subprocess.run(["node", str(ROOT / "assets" / "render_probe.mjs"),
                        str(tmp / "shell.js")], capture_output=True, text=True, timeout=60)
    rows = r.stdout.strip().splitlines()
    res_json = None
    for i in range(len(rows)):
        try:
            res_json = json.loads("\n".join(rows[i:]))
            break
        except json.JSONDecodeError:
            continue
    if not res_json or res_json.get("fatal"):
        return check(False, f"probe failed: {(res_json or {}).get('fatal', r.stderr)[:110]}")

    f = check(not res_json.get("errors"), "all components drawn")
    h = res_json.get("html") or {}

    # Cloze: as many input fields as placeholders
    lt = h.get("cloze", "")
    f += check(lt.count('class="gap"') == 2,
                f"cloze: 2 input fields (found {lt.count('class=' + chr(34) + 'gap' + chr(34))})")
    # Quiz: as many options as in the data
    qz = h.get("quiz", "")
    f += check(qz.count('type="radio"') + qz.count('type="checkbox"') == 3,
                "quiz: three options")
    # Matching: three statements, two target values — every select field shows
    # both target values EXACTLY ONCE. Without deduplication "Gruppe X" would
    # be in it twice.
    to = h.get("matching", "")
    selects = re.findall(r"<select.*?</select>", to, re.S)
    f += check(len(selects) == 3, f"matching: three select fields ({len(selects)})")
    if selects:
        opt = [o for o in re.findall(r"<option[^>]*>([^<]*)</option>", selects[0])
               if o.strip() and "wähl" not in o and "elect" not in o
               and "chois" not in o and "scegl" not in o and "eleg" not in o]
        f += check(len(opt) == len(set(opt)) == 2,
                    f"matching: selection deduplicated ({opt})")

    # Flashcards and diagrams draw DELAYED through a DOM hook; the string
    # returned is only the shell. So the shell is checked, not the content.
    fc = h.get("flashcards", "")
    f += check("card3d" in fc and "fc-counter" in fc,
                "flashcards: shell with card area and counter")
    dg = h.get("diagram", "")
    f += check(re.search(r'id="mm', dg) and "block" in dg,
                "diagram: shell with drawing area")
    # Alternative texts must be in the data structure
    f += check(all(b.get("description") for l in u["lessons"]
                    for b in l["blocks"]
                    if b.get("type") in ("diagram", "chart", "simulator", "widget")),
                "all displays carry an alternative text")
    return f


if __name__ == "__main__":
    errors = (test_repair_chain() + test_assembly_roundtrip()
              + test_components_keep_promises())
    print(f"\n{'FULL CHAIN OK' if not errors else f'{errors} FAILED'}")
    sys.exit(1 if errors else 0)
