# -*- coding: utf-8 -*-
"""unit.json against the published JSON Schema.

The pipeline does not validate against src/unit/schema/unit.schema.json at
run time; src/unit/validator.py checks the units with its own, stricter
rules. The schema documents the format for anyone reading or producing
unit.json. This test keeps the two from drifting apart: the example file and
a unit produced by the mocked pipeline must both conform. Needs the
jsonschema package (requirements-dev.txt) and is skipped without it.
"""
import asyncio
import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _optional import installed  # noqa: E402

SCHEMA = REPO / "src" / "unit" / "schema" / "unit.schema.json"


def _errors(data) -> list[str]:
    import jsonschema
    validator = jsonschema.Draft7Validator(json.loads(SCHEMA.read_text(encoding="utf-8")))
    return [f"{'/'.join(map(str, e.path)) or '(root)'}: {e.message[:120]}"
            for e in validator.iter_errors(data)]


async def _produce(tmp: Path) -> dict:
    from mock_llm import MockLLM
    from src.pipeline.learning_pipeline import LearningPipeline
    p = LearningPipeline(MockLLM("strong"), MockLLM("fast"), work_dir=tmp,
                     job_number=1, max_parallel=3)
    await p.collect_profile("Admin, knows Docker", "Learn Kubernetes", 40,
                          {"notes.txt": "cluster notes"})
    p.answer_briefing("version 1.30")
    await p.analyse_gap()
    p.approve([])
    await p.plan_all_chapters()
    async for _ in p.produce_all():
        pass
    async for _ in p.consolidate():
        pass
    return p.unit


def test_example_conforms():
    if not installed("jsonschema"):
        print("  ---  jsonschema not installed, skipped")
        return
    data = json.loads((REPO / "examples" / "example-unit.json").read_text(encoding="utf-8"))
    errors = _errors(data)
    assert not errors, errors
    print("  ok   example unit conforms to the schema")


def test_generated_unit_conforms():
    if not installed("jsonschema"):
        print("  ---  jsonschema not installed, skipped")
        return
    with tempfile.TemporaryDirectory() as tmp:
        unit = asyncio.run(_produce(Path(tmp)))
    errors = _errors(unit)
    assert not errors, errors
    print("  ok   unit produced by the mocked pipeline conforms to the schema")


if __name__ == "__main__":
    test_example_conforms()
    test_generated_unit_conforms()
    print("SCHEMA OK")
