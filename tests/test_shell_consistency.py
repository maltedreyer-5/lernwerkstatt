# -*- coding: utf-8 -*-
"""Names the shell's script expects must exist in its markup and styles.

The script finds elements by class, id and data attribute. If a name in the
script and the name in the markup drift apart, nothing fails loudly: the
element is simply not found, a quiz stops scoring, a style stops applying.
This test compares the names on both sides without a browser.
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SHELL = REPO / "assets" / "shell.html"


def _built_markup() -> str:
    """Markup that Python writes into units at build time (terms, formulas)."""
    return "\n".join(p.read_text(encoding="utf-8") for p in (REPO / "src" / "unit").glob("*.py"))


def _parts(src: str):
    style = "\n".join(re.findall(r"<style>([\s\S]*?)</style>", src))
    script = "\n".join(re.findall(r"<script>([\s\S]*?)</script>", src))
    return style, script


def _kebab(name: str) -> str:
    return re.sub(r"([A-Z])", lambda m: "-" + m.group(1).lower(), name)


def check_shell(src: str) -> list[str]:
    style, script = _parts(src)
    problems = []
    # data attributes: every dataset.x read in the script needs data-x in markup
    built = _built_markup()
    written = set(re.findall(r"data-([a-z][a-z0-9-]*)", src + built))
    for prop in sorted(set(re.findall(r"\.dataset\.([A-Za-z]\w*)", script))):
        if _kebab(prop) not in written:
            problems.append(f"dataset.{prop}: no data-{_kebab(prop)} attribute")
    # classes used in selectors must be defined or produced somewhere
    known = set(re.findall(r"\.([A-Za-z][\w-]*)", re.sub(r"\{[^}]*\}", "{}", style)))
    for m in re.finditer(r'class=\\?"([^"\\]*)', src + built):
        known.update(t for t in re.split(r"\s+|\$\{[^}]*\}", m.group(1)) if t)
    known.update(re.findall(r'classList\.(?:add|toggle)\("([\w-]+)"', script))
    known.update(re.findall(r'className\s*=\s*"([\w-]+)', script))
    selectors = re.findall(r'(?:querySelector(?:All)?|closest|matches|\$)\??\.?\(\s*["\'`]([^"\'`$]+)["\'`]', script)
    for sel in selectors:
        for cls in re.findall(r"\.([A-Za-z][\w-]*)", sel):
            if cls not in known:
                problems.append(f"selector '{sel}': class '{cls}' is never set")
    # ids looked up must exist
    ids = set(re.findall(r'\bid="([\w-]+)"', src)) | set(re.findall(r'\.id\s*=\s*"([\w-]+)"', script))
    looked_up = set(re.findall(r'getElementById\("([\w-]+)"\)', script))
    for sel in selectors:
        looked_up.update(re.findall(r"#([A-Za-z][\w-]*)", sel))
    for i in sorted(looked_up - ids):
        problems.append(f"id '{i}' is looked up but never set")
    return problems


def test_shell_names_consistent():
    problems = check_shell(SHELL.read_text(encoding="utf-8"))
    assert not problems, "\n".join(problems)
    print("  ok   data attributes, classes and ids match between script and markup")


if __name__ == "__main__":
    if len(sys.argv) > 1:                       # check another file (counter-check)
        print("\n".join(check_shell(Path(sys.argv[1]).read_text(encoding="utf-8"))) or "no problems")
        sys.exit(0)
    test_shell_names_consistent()
    print("SHELL CONSISTENCY OK")
