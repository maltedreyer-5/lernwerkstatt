# -*- coding: utf-8 -*-
"""Tests of the unit layer (validator + assembler) — runs without the LLM stack.

Run:  python -m pytest tests/ -q      (or: python tests/test_unit_layer.py)
"""
from __future__ import annotations

import copy
import json
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.unit.assembler import assemble  # noqa: E402
from src.unit.validator import validate  # noqa: E402

EXAMPLE = json.loads((REPO / "examples" / "example-unit.json").read_text(encoding="utf-8"))

def broken_fixture() -> dict:
    """Covers many check paths; expected count: 12 errors, 8 warnings."""
    u = copy.deepcopy(EXAMPLE)
    u["depth_profile"] = "detailed"
    u["lessons"][1]["blocks"][1]["code"] = "function modell(p){ while(true){} }"
    del u["lessons"][0]["blocks"][2]["description"]
    u["lessons"][0]["blocks"][4]["questions"][0]["options"][1]["correct"] = False
    u["modules"][0]["lessons"] = ["l1", "l1", "l99"]
    u["glossary"][0].pop("definition")
    u["concepts"] = [{"id": "kx", "name": "Testkonzept", "concept_class": "V"}]
    return u


def test_example_unit_is_clean():
    b = validate(EXAMPLE)
    assert b.errors == [], b.report()
    assert b.warnings_ == [], b.report()


def test_broken_fixture_counts_as_expected():
    """Counts the findings of the deliberately broken fixture.

    The numbers grow when new checks are added — so it is also checked that
    the essential findings are present by name. That shows if a check
    disappears silently instead of only shifting the total.
    """
    b = validate(broken_fixture())
    assert len(b.errors) == 12, b.report()
    # 8. Warning under rule B8: a very short 'detailed' lesson is reported even
    # if it is rich in interaction (interactions are no replacement for text).
    assert len(b.warnings_) == 8, b.report()
    expected = ["description (alternative text) is required",
                "no correct option marked",
                "is assigned to several modules",
                "references unknown lesson",
                "definition missing",
                "appears in NO lesson"]
    for part in expected:
        assert any(part in f for f in b.errors), f"missing: {part}\n{b.report()}"
    assert any("interactions do not replace developing running text" in w
               for w in b.warnings_), b.report()


def test_concept_coverage_gate():
    """state=draft → warning; final → error (blocks delivery)."""
    u = copy.deepcopy(EXAMPLE)
    u["concepts"] = [{"id": "k1", "name": "Nirgends behandelt", "concept_class": "K"}]
    for l in u["lessons"]:
        l["concepts"] = []
    u["state"] = "draft"
    b = validate(u, node_probe=False)
    assert any("NO lesson" in w for w in b.warnings_) and b.passed
    u["state"] = "final"
    b = validate(u, node_probe=False)
    assert any("NO lesson" in f for f in b.errors) and not b.passed


def test_simulator_probe_catches_endless_loop():
    if shutil.which("node") is None:
        return  # without Node only the static check — then the warning path applies
    u = copy.deepcopy(EXAMPLE)
    u["lessons"][1]["blocks"][1]["code"] = "function modell(p){ while(true){} }"
    b = validate(u)
    assert any("trial run" in f for f in b.errors), b.report()


def cjk_fixture() -> dict:
    u = copy.deepcopy(EXAMPLE)
    u["lessons"][0]["blocks"][0]["html"] += " 配置很重要"
    return u


def test_language_discipline():
    from src.unit.validator import check_lesson
    u = cjk_fixture()
    b = validate(u, node_probe=False)
    assert sum("CJK characters" in w for w in b.warnings_) == 1 and b.passed
    b2 = check_lesson(u["lessons"][0], node_probe=False, language="de")
    assert any("CJK characters" in f for f in b2.errors), "per lesson: error (repair trigger)"
    assert not check_lesson(u["lessons"][0], node_probe=False).errors, \
        "without a language no language error"


def test_assembler_replaces_placeholders(tmp_path=None):
    target = Path(tmp_path) if tmp_path else REPO / "tests" / "_tmp_dist"
    res = assemble(EXAMPLE, target)
    html = res.path_.read_text(encoding="utf-8")
    for placeholder in ("__UNIT_DATA__", "__TITLE__", "__PROVENANCE__", "<!--VENDOR:SCRIPTS-->"):
        assert placeholder not in html
    assert EXAMPLE["id"] in html and res.kilobytes > 10
    assert res.engines == ["chartjs"]
    shutil.rmtree(target, ignore_errors=True)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"OK  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
