# -*- coding: utf-8 -*-
"""Ensures that `terms.slug` matches the `slug` function in
`assets/shell.html`.

Why a separate test: the hover looks up the definition through
`TERM_INDEX[data-term]`. If the Python key differs from the JS key, the
popover silently gives nothing — no error, no message, only a dead marking.
That happens as soon as one side unicode-normalises and the other does not:
"Naïve Bayes" would become "naive-bayes" once and "na-ve-bayes" once.

The test extracts the real JS function from shell.html and runs it with Node
— it checks against the delivered code, not against a copy of it.
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.unit.terms import slug  # noqa: E402

SHELL = Path(__file__).resolve().parents[1] / "assets" / "shell.html"

SAMPLES = [
    "Morphem", "Anbieter (KI-Verordnung)", "ISO/IEC 42001", "Résumé",
    "Naïve Bayes", "Fließtext", "Größe", "Über-Ich", "e-Learning",
    "Wasserpotential Ψ", "±", "A/B-Test", "Poincaré-Schnitt", "  ",
    "Ökosystem-Ansatz", "Freies Morphem", "EU-Konformitätserklärung",
    "Hochrisiko-KI-System", "Technische Dokumentation (Anhang IV)",
    "Daten-Drift", "FAIR-Daten", "μ-Rezeptor", "3D-Modell", "C++",
]


def js_slug_source() -> str:
    """Fetches the slug definition from the delivered shell."""
    text = SHELL.read_text(encoding="utf-8")
    m = re.search(r"const slug = t =>.*?;\n", text, re.S)
    if not m:
        raise AssertionError("slug-Funktion in shell.html nicht gefunden — "
                             "wurde sie umbenannt? Dann bricht der Hover.")
    return m.group(0)


def test_parity():
    if shutil.which("node") is None:
        print("  ---  SKIPPED (no Node available)")
        return 0
    runner = js_slug_source() + (
        'let raw=""; process.stdin.on("data",d=>raw+=d);\n'
        'process.stdin.on("end",()=>console.log('
        'JSON.stringify(JSON.parse(raw).map(slug))));\n')
    with tempfile.TemporaryDirectory() as tmp:
        path_ = Path(tmp) / "slug.mjs"
        path_.write_text(runner, encoding="utf-8")
        proc = subprocess.run(["node", str(path_)], input=json.dumps(SAMPLES),
                              capture_output=True, text=True, timeout=20)
        if proc.returncode != 0:
            print("  FAIL node call:", proc.stderr[:200])
            return 1
        js = json.loads(proc.stdout)

    errors = 0
    for term, js_wert in zip(SAMPLES, js):
        py_value = slug(term)
        if py_value == js_wert:
            print(f"  ok   {term!r:42} -> {py_value}")
        else:
            print(f"  FAIL {term!r:42} Python={py_value!r} JS={js_wert!r}")
            errors += 1
    return errors


if __name__ == "__main__":
    print("slug parity Python ↔ shell.html")
    f = test_parity()
    print(f"\n{'PARITY CONFIRMED' if not f else f'{f} DEVIATIONS'}")
    sys.exit(1 if f else 0)
