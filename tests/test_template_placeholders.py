# -*- coding: utf-8 -*-
"""Every str.format() call on a module-level template passes exactly its placeholders.

Templates such as the inventory prompt are plain strings with {name}
placeholders, filled in elsewhere with .format(name=...). If a placeholder
and its keyword drift apart — through a rename, for instance — the call
raises KeyError at run time; where the caller catches it, the feature
silently stops working. This test finds every such call in the code base
and compares the keyword names with the placeholders of the template.
"""
import ast
import sys
from pathlib import Path
from string import Formatter

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def _placeholders(text: str) -> set[str]:
    return {f.split(".")[0].split("[")[0] for _, f, _, _ in Formatter().parse(text) if f}


def _module_constants() -> dict[str, str]:
    """All module-level string constants in src, by name."""
    found: dict[str, str] = {}
    for p in (REPO / "src").rglob("*.py"):
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for n in tree.body:
            if isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant) \
                    and isinstance(n.value.value, str):
                for t in n.targets:
                    if isinstance(t, ast.Name):
                        found[t.id] = n.value.value
    return found


def problems() -> list[str]:
    consts = _module_constants()
    out = []
    for p in list((REPO / "src").rglob("*.py")) + list((REPO / "scripts").rglob("*.py")):
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "format" \
                    and isinstance(n.func.value, ast.Name) and n.func.value.id in consts \
                    and not any(k.arg is None for k in n.keywords) and not n.args:
                want = _placeholders(consts[n.func.value.id])
                have = {k.arg for k in n.keywords}
                if want != have:
                    out.append(f"{p.relative_to(REPO)}:{n.lineno} {n.func.value.id}: "
                               f"template {sorted(want)} vs call {sorted(have)}")
    return out


def test_template_placeholders_match():
    found = problems()
    assert not found, "\n".join(found)
    print("  ok   every .format() on a module template passes exactly its placeholders")


if __name__ == "__main__":
    test_template_placeholders_match()
    print("TEMPLATE PLACEHOLDERS OK")
