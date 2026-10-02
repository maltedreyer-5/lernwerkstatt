# -*- coding: utf-8 -*-
"""Degradation finds broken blocks wherever the validator reports them.

The degradation matches blocks by the path prefix in the validator's error
messages. If the two spell a path differently, broken blocks at that place
are never downgraded and keep blocking the final gate. Checked for every
place a block can be: lessons and the application part of each module.
"""
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.unit import degradation  # noqa: E402
from src.unit.validator import validate  # noqa: E402

REPO = Path(__file__).resolve().parents[1]

BROKEN_CHART = {"type": "chart", "engine": "chartjs", "spec": {"type": "bar"},
                "description": "Bar chart: replica count rises from one to three."}


def _unit_with(where: str) -> dict:
    unit = json.loads((REPO / "examples" / "example-unit.json").read_text(encoding="utf-8"))
    unit = copy.deepcopy(unit)
    if where == "lesson":
        unit["lessons"][0]["blocks"].append(copy.deepcopy(BROKEN_CHART))
    else:
        unit["modules"][0].setdefault("exercises", []).append(copy.deepcopy(BROKEN_CHART))
    return unit


def test_downgrade_everywhere():
    for where in ("lesson", "exercises"):
        unit = _unit_with(where)
        before = validate(unit)
        assert before.errors, f"{where}: the broken chart must be an error first"
        replaced = degradation.downgrade(unit, before)
        after = validate(unit)
        assert replaced, f"{where}: nothing was downgraded ({before.errors[:2]})"
        assert not after.errors, f"{where}: errors remain after degradation: {after.errors[:2]}"
        print(f"  ok   broken chart in {where} is downgraded, no error remains")


if __name__ == "__main__":
    test_downgrade_everywhere()
    print("DEGRADATION PATHS OK")
