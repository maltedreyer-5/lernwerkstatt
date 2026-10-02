# -*- coding: utf-8 -*-
"""Every interface text used in the code is translated, with the same placeholders.

Source texts are found in the code itself: the first argument of every
tr(...), Msg(...) and N_(...) call that is a string literal — and of t(...),
the local shorthand for tr(text, lang) used in report writers. A text missing from a
catalog would silently appear in English; a placeholder missing or added in
a translation would raise at the moment the message is shown.
"""
import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.i18n import LANGUAGES, catalog, placeholders  # noqa: E402


def source_texts() -> dict[str, str]:
    found = {}
    for p in list((REPO / "src").rglob("*.py")) + [REPO / "app.py"]:
        for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            if isinstance(n, ast.Call) and getattr(n.func, "id", getattr(n.func, "attr", "")) in ("tr", "Msg", "N_", "t") \
                    and n.args and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str):
                found.setdefault(n.args[0].value, f"{p.relative_to(REPO)}:{n.lineno}")
            # validator messages: b.F(location, template, ...) / b.W(...)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in ("F", "W") \
                    and len(n.args) > 1 and isinstance(n.args[1], ast.Constant) and isinstance(n.args[1].value, str):
                found.setdefault(n.args[1].value, f"{p.relative_to(REPO)}:{n.lineno}")
            # interface texts registered through ui_(...) in the wizard
            if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "ui_":
                for kw in n.keywords:
                    if kw.arg in ("label", "value", "placeholder", "info") and \
                            isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                        found.setdefault(kw.value.value, f"{p.relative_to(REPO)}:{n.lineno}")
                    if kw.arg == "headers" and isinstance(kw.value, ast.List):
                        for el in kw.value.elts:
                            if isinstance(el, ast.Constant):
                                found.setdefault(el.value, f"{p.relative_to(REPO)}:{n.lineno}")
    return found


def test_catalogs_complete():
    texts = source_texts()
    problems = []
    for lang in LANGUAGES:
        if lang == "en":
            continue
        cat = catalog(lang)
        for text, where in texts.items():
            if text not in cat:
                problems.append(f"[{lang}] missing ({where}): {text[:70]}")
            elif placeholders(cat[text]) != placeholders(text):
                problems.append(f"[{lang}] placeholders differ ({where}): {text[:70]}")
        for text in cat:
            if text not in texts:
                problems.append(f"[{lang}] unused entry: {text[:70]}")
    assert not problems, "\n".join(problems)
    print(f"  ok   {len(texts)} source texts, all translated with matching placeholders")


if __name__ == "__main__":
    test_catalogs_complete()
    print("I18N CATALOG OK")
