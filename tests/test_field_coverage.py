# -*- coding: utf-8 -*-
"""Keeps renderer and normalisation congruent.

An ad-hoc fix for one field (such as `material` of an error analysis, where
literal "\\n" sequences would show in the task text) says nothing about
whether other fields have the same gap. This test answers exactly that.

Principle: every field the shell renders as TEXT must be in one of the field
lists — as an HTML field, as a text field or explicitly as taboo. A new field
then shows up in the next test run and not with the learner.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.unit.normalization import (FIELDS_HTML, FIELDS_TABOO,  # noqa: E402
                                     FIELDS_TEXT)

# Fields that are not text and therefore cannot be normalised.
NOT_TEXT = {
    "type", "id", "engine", "variant", "height", "breite", "display",
    "spec", "code", "latex", "html", "gaps", "questions", "cards",
    "items", "options", "multiple", "correct", "min", "max", "step",
    "value", "name", "header", "rows", "pairs", "parameters", "output",
    "hints", "language", "concepts",
}


def check(b, name):
    print(f"  {'ok  ' if b else 'FAIL'} {name}")
    return 0 if b else 1


def _renderer_fields() -> dict[str, set[str]]:
    """Which fields does each renderer read from the block?"""
    shell = (ROOT / "assets" / "shell.html").read_text(encoding="utf-8")
    i = shell.index("const renderer = {")
    blocks: dict[str, list[str]] = {}
    current, depth = None, 0
    for line in shell[i:].split("\n"):
        m = re.match(r"\s*(\w+)\s*:\s*(?:\(|b\s*=>)", line)
        if m and depth <= 1:
            current = m.group(1)
            blocks[current] = []
        if current:
            blocks[current].append(line)
        depth += line.count("{") - line.count("}")
        if current and depth <= 0:
            break
    return {t: set(re.findall(r"\bb\.(\w+)", "\n".join(z))) for t, z in blocks.items()}


def _covered(type_: str, field_: str) -> bool:
    if (type_, field_) in FIELDS_TABOO or field_ in NOT_TEXT:
        return True
    return any(p[0] == field_ for tab in (FIELDS_HTML, FIELDS_TEXT)
               for p in tab.get(type_, []))


def test_renderer_fields_normalised():
    print("renderer fields against normalisation")
    fields_ = _renderer_fields()
    f = check(len(fields_) >= 15, f"{len(fields_)} renderers found")

    gaps = {t: sorted(x for x in fs if not _covered(t, x))
               for t, fs in fields_.items()}
    gaps = {t: v for t, v in gaps.items() if v}
    for type_, missing in gaps.items():
        print(f"  FAIL {type_}: {', '.join(missing)} is rendered, "
              f"but never normalised")
    f += check(not gaps, "every rendered text field is normalised")
    return f


def test_no_duplicate_keys():
    """A second entry of the same type silently overwrites the first."""
    print("field lists without duplicate keys")
    import ast
    import collections
    source = (ROOT / "src" / "unit" / "normalization.py").read_text(encoding="utf-8")
    f = 0
    found = 0
    for nodes in ast.parse(source).body:
        # plain and annotated assignments alike
        t = getattr(nodes, "target", None) or (getattr(nodes, "targets", None) or [None])[0]
        target = getattr(t, "id", "") or ""
        if not target.startswith("FIELDS") or not isinstance(
                getattr(nodes, "value", None), ast.Dict):
            continue
        found += 1
        keys = [k.value for k in nodes.value.keys if isinstance(k, ast.Constant)]
        dop = [k for k, c in collections.Counter(keys).items() if c > 1]
        f += check(not dop, f"{target} without duplicate keys"
                    + (f" (duplicate: {dop})" if dop else ""))
    # Without this the check would pass silently if the lists were renamed.
    f += check(found >= 2, f"{found} field lists found")
    return f


def test_normalization_reaches_nested_fields():
    """The path descriptions must also apply in lists, not only at the top."""
    print("nested fields are reached")
    from src.unit.normalization import normalise_block
    B = chr(92)
    to = {"type": "matching", "task": "Ordne zu",
          "pairs": [{"left": "**Fett** markiert", "right": "Kategorie A"}]}
    normalise_block(to)
    f = check("**" not in to["pairs"][0]["left"], "matching.pairs[].left")

    sim = {"type": "simulator", "title": "T", "description": "B",
           "code": "function f(){}",
           "parameters": [{"name": "x", "label": "*Größe*", "unit": "Token"}]}
    normalise_block(sim)
    f += check("*" not in sim["parameters"][0]["label"], "simulator.parameters[].label")

    fa = {"type": "error_analysis", "title": "T", "question": "F", "sample_solution": "M",
          "material": "Zeile 1" + B + "nZeile 2"}
    normalise_block(fa)
    f += check(B not in fa["material"], "error_analysis.material")
    return f


if __name__ == "__main__":
    errors = (test_renderer_fields_normalised() + test_no_duplicate_keys()
              + test_normalization_reaches_nested_fields())
    print(f"\n{'FIELD COVERAGE OK' if not errors else f'{errors} FAILED'}")
    sys.exit(1 if errors else 0)
