# -*- coding: utf-8 -*-
"""Checks localisation across the WHOLE output chain.

A select field alone is not enough: the controls of the generated file must
follow the unit's language. A Spanish learning unit with German buttons
looks like a bug, not like a missing feature.

So the test checks not the table but the RESULT: one assembled unit per
language in which no German control text remains.
"""
import json
import re
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

from src.unit import i18n  # noqa: E402
from src.unit.assembler import assemble  # noqa: E402

# Control terms that have no place in a non-German unit.
GERMAN_CONTROLS = (
    "Antwort prüfen", "Auflösung anzeigen", "Musterlösung anzeigen",
    "Fortschritt zurücksetzen", "Zum Überblick", "Weitere Lektionen",
    "Ihre Vorhersage", "Ihre Lösung", "Glossar filtern", "Lückentext",
    "In der Einheit suchen", "Keine Treffer für", "Das können Sie danach",
    "Vorausgesetzt wird", "Ziele dieser Lektion", "Anwenden und Abtesten",
    "Loslegen", "– wählen –", "Zurück",
)


def check(b, name):
    print(f"  {'ok  ' if b else 'FAIL'} {name}")
    return 0 if b else 1


def _build(language: str) -> str:
    u = json.loads((ROOT / "examples" / "example-unit.json").read_text(encoding="utf-8"))
    u["language"] = language
    target = Path(tempfile.mkdtemp())
    res = assemble(u, target)
    path_ = getattr(res, "path_", res)
    return Path(path_).read_text(encoding="utf-8")


def _without_unit_data(html: str) -> str:
    """The unit itself is German here — only the shell is to be checked."""
    i = html.index("const UNIT =")
    j = html.index("\n", i)
    return html[:i] + html[j:]


def _check_js(html: str, mark: str) -> int:
    """Runs `node --check` over the embedded JavaScript.

    The localisation test otherwise checks only the ABSENCE of German texts
    — not whether the file still runs at all. A replacement that puts a
    backtick INSIDE a template literal ends it early; the units would no
    longer start, and no other test would notice.
    """
    import shutil
    import subprocess
    if not shutil.which("node"):
        print(f"  ---  {mark}: node missing, JS unchecked")
        return 0
    js = re.findall(r"<script(?![^>]*src=)[^>]*>(.*?)</script>", html, re.S)
    if not js:
        return check(False, f"{mark}: no script block found")
    file = Path(tempfile.mkdtemp()) / "shell.js"
    file.write_text(js[-1], encoding="utf-8")
    r = subprocess.run(["node", "--check", str(file)],
                       capture_output=True, text=True, timeout=30)
    if r.returncode:
        line = [x for x in r.stderr.splitlines() if "Error" in x or ".js:" in x]
        print(f"  FAIL {mark}: JavaScript broken — {'; '.join(line[:2])[:110]}")
        return 1
    return check(True, f"{mark}: JavaScript free of errors")


def test_table_complete():
    print("language table")
    f = check(not i18n.missing_ones(),
               f"all {len(i18n.TEXTS)} keys in {len(i18n.LANGUAGES)} languages")
    f += check(len(i18n.CHOICES) == 5, "five languages to choose from")
    f += check(all(c in i18n.LANGUAGES for c, _ in i18n.CHOICES),
                "select list and table agree")
    # An unknown language falls back cleanly to English
    f += check(i18n.table_("xx") == i18n.table_("en"), "falls back to English")
    return f


def test_shell_without_german_controls():
    print("assembled unit per language")
    f = 0
    for code in ("en", "fr", "es", "it"):
        html = _build(code)
        f += check(re.search(rf'<html lang="{code}"', html),
                    f"{code}: lang attribute set")
        f += check("__I18N__" not in html and "__LANGUAGE__" not in html,
                    f"{code}: no unreplaced placeholders")
        shell = _without_unit_data(html)
        remainders = [t for t in GERMAN_CONTROLS if t in shell]
        f += check(not remainders, f"{code}: no German controls"
                    + (f" (gefunden: {remainders[:3]})" if remainders else ""))
        # And the target language really is in it
        expected = i18n.table_(code)["check_answer"]
        f += check(expected in shell, f"{code}: '{expected}' appears")
        f += _check_js(html, code)
    return f


def test_german_unchanged():
    print("German stays German")
    html = _build("de")
    shell = _without_unit_data(html)
    f = check('<html lang="de"' in html, "lang=de")
    f += check("Antwort prüfen" in shell and "Glossar" in shell,
                "German controls present unchanged")
    f += _check_js(html, "de")
    return f


def test_selector_wired():
    print("select field in the interface")
    source = (ROOT / "src" / "ui" / "wizard.py").read_text(encoding="utf-8")
    f = check("i18n.CHOICES" in source, "the select field uses the language list")
    f += check(source.count("time_budget, language, uploads") >= 2,
                "both starting routes pass the language on")
    pipe = (ROOT / "src" / "pipeline" / "learning_pipeline.py").read_text(encoding="utf-8")
    f += check('self.profile["language"]' in pipe,
                "the pipeline writes the language into the profile")
    f += check("i18n.table_(self.language)" in pipe,
                "the handout uses the language table")
    return f


def test_no_hardcoded_german_in_shell():
    """No German text of the unit table appears literally in the shell.

    Every text a learner sees must come from the table, otherwise it shows in
    German in every unit. A fixed list of forbidden words misses new texts;
    the German column of the table itself is the complete list.
    """
    from src.unit import i18n
    print("no hardcoded German in the shell")
    shell = (ROOT / "assets" / "shell.html").read_text(encoding="utf-8")
    import re
    found = sorted({v["de"] for v in i18n.TEXTS.values()
                    if len(v["de"]) >= 6 and v["de"] != v.get("en")
                    and re.search(rf"(?<!\w){re.escape(v['de'])}(?!\w)", shell)})
    return check(not found, "every German text comes from the table"
                 + (f" (hardcoded: {found[:5]})" if found else ""))


if __name__ == "__main__":
    errors = (test_table_complete() + test_shell_without_german_controls()
              + test_german_unchanged() + test_selector_wired()
              + test_no_hardcoded_german_in_shell())
    print(f"\n{'LOCALISATION OK' if not errors else f'{errors} FAILED'}")
    sys.exit(1 if errors else 0)
