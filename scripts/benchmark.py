# -*- coding: utf-8 -*-
"""Benchmark: five reference concepts against the configured models.

The validator is the yardstick: for each case script → transformation →
deterministic check (including the simulator trial run) → if needed one
repair loop. Output: a table with errors/warnings/durations per case.

In the container:   python scripts/benchmark.py          (real models, .env)
Dry run (CI):       python scripts/benchmark.py --mock
Exit 0 = all cases free of errors after at most one repair.
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.llm.json_parser import parse_llm_json  # noqa: E402
from src.prompts import learning  # noqa: E402
from src.unit.validator import check_lesson  # noqa: E402

PROFILE = {"context": "Admin im Hochschulumfeld, Docker-Vorwissen",
          "target_level": "verstehen und anwenden", "language": "de"}
CROSS = "Terminologie: Desired State = Soll-Zustand; Reconciliation = Regelschleife."

CASES = [
    ("Text+Quiz (V)", {"id": "b1", "title": "Desired State verstehen",
        "concepts": ["k1"], "learning_objectives": ["Kann deklarativ von imperativ abgrenzen"],
        "media_plan": ["text mit h3-Gliederung", "quiz"],
        "check_criteria": ["Fehlvorstellung 'Befehlskette' adressiert"]},
     {"id": "k1", "name": "Desired State", "concept_class": "V"}),
    ("Chart (level 2)", {"id": "b2", "title": "Wachstum visualisiert",
        "concepts": ["k2"], "learning_objectives": ["Kann exponentielles Wachstum einordnen"],
        "media_plan": ["text", "chart (chartjs, Daten inline)", "quiz"],
        "check_criteria": ["Chart trägt eine Kernaussage, kein Deko-Chart"]},
     {"id": "k2", "name": "Exponentielles Wachstum", "concept_class": "V"}),
    ("Simulator (level 3)", {"id": "b3", "title": "Rolling Update erkunden",
        "concepts": ["k3"], "learning_objectives": ["Kann maxSurge/maxUnavailable vorhersagen"],
        "media_plan": ["text", "simulator (reine Funktion, Liniendiagramm)", "quiz"],
        "check_criteria": ["Simulator mit konkreter Erkundungsaufgabe"]},
     {"id": "k3", "name": "Rolling Update", "concept_class": "V"}),
    ("Matching + cloze", {"id": "b4", "title": "Begriffe festigen",
        "concepts": ["k4"], "learning_objectives": ["Kann Docker- und K8s-Begriffe zuordnen"],
        "media_plan": ["text", "matching", "cloze"],
        "check_criteria": ["rechts-Werte eindeutig", "Lücken konsistent definiert"]},
     {"id": "k4", "name": "Begriffswelt", "concept_class": "K"}),
]
TASK_CONCEPTS = [{"id": "k1", "name": "Desired State", "concept_class": "V"},
                     {"id": "k3", "name": "Rolling Update", "concept_class": "V"}]


def _llms(mock: bool):
    if mock:
        from tests.mock_llm import MockLLM
        return MockLLM("strong"), MockLLM("fast")
    from src.config import load_config
    from src.llm.client import LLMClient

    def build(c):
        if not (c.base_url and c.model):
            sys.exit("LLM configuration incomplete — check .env (template: .env.example)")
        return LLMClient(base_url=c.base_url, api_key=c.api_key, model=c.model,
                         family=c.family, thinking=c.thinking, max_tokens=c.max_tokens,
                         temperature=c.temperature, timeout=c.timeout,
                         max_concurrent=c.max_concurrent)
    cfg = load_config()
    strong = build(cfg.llm1)
    return strong, (build(cfg.llm2) if getattr(cfg, "llm2", None) else strong)


async def _case(strong, fast, name, plan, concept):
    t0 = time.monotonic()
    script = await strong.complete(
        learning.script_prompt(concept, plan, PROFILE, "detailed", "")
        .replace("{dep:cross}", CROSS) + "\n\n" + learning.language_rule("de"))
    t1 = time.monotonic()
    raw = await fast.complete(
        learning.transform_prompt(plan, script[:8000], "detailed")
        + "\n\n" + learning.language_rule("de"), json_mode=True)
    lesson = parse_llm_json(raw)
    t2 = time.monotonic()
    finding = check_lesson(lesson, language="de")
    repaired = False
    if finding.errors:
        repaired = True
        new_ = parse_llm_json(await fast.complete(
            ("Repair the following lesson (unit.json format). Fix ONLY "
             "the errors listed.\n\nERRORS:\n")
            + "\n".join(f"- {f}" for f in finding.errors[:10])
            + "\n\n" + learning.language_rule("de")
            + "\n\nLEKTION:\n" + json.dumps(lesson, ensure_ascii=False)[:12000]
            + "\n\n" + learning.JSON_ONLY, json_mode=True))
        finding = check_lesson(new_, language="de")
    return {"case": name, "errors": len(finding.errors), "warnings": len(finding.warnings_),
            "repaired": repaired, "t_script": t1 - t0, "t_transform": t2 - t1,
            "details": finding.errors[:3]}


async def _case_tasks(strong):
    t0 = time.monotonic()
    detail_plan = {"application_part": [{"type": "prediction", "concepts": ["k1"],
                                    "short_description": "festlegen, dann prüfen"}],
                "case_task": {"concepts": ["k1", "k3"], "short_description": "integriert"}}
    raw = await strong.complete(
        learning.tasks_prompt("Benchmark chapter", detail_plan, TASK_CONCEPTS)
        .replace("{dep:cross}", CROSS) + "\n\n" + learning.language_rule("de"), json_mode=True)
    exercises = parse_llm_json(raw).get("exercises") or []
    finding = check_lesson({"id": "ex", "title": "Anwendungsteil", "blocks": exercises},
                            language="de")
    errors = [f for f in finding.errors]
    return {"case": "Application part (tasks)", "errors": len(errors),
            "warnings": len(finding.warnings_), "repaired": False,
            "t_script": 0.0, "t_transform": time.monotonic() - t0, "details": errors[:3]}


async def main() -> int:
    mock = "--mock" in sys.argv
    strong, fast = _llms(mock)
    print(f"Benchmark — models: strong={strong.model}, fast={fast.model}"
          + ("  [MOCK]" if mock else ""))
    results_ = [await _case(strong, fast, *f) for f in CASES]
    results_.append(await _case_tasks(strong))

    print(f"\n{'Case':<26}{'Errors':>8}{'Warn.':>7}{'Rep.':>6}{'Script s':>10}{'Transf. s':>10}")
    print("-" * 68)
    for e in results_:
        print(f"{e['case']:<28}{e['errors']:>7}{e['warnings']:>7}"
              f"{'ja' if e['repaired'] else '—':>6}"
              f"{e['t_script']:>10.1f}{e['t_transform']:>10.1f}")
        for d in e["details"]:
            print(f"    ↳ {d}")
    bad = [e for e in results_ if e["errors"]]
    print("\n" + ("PASSED: all cases free of errors after at most one repair."
                  if not bad else
                  (f"NOT passed: {len(bad)} case(s) with remaining errors — "
                   "check the model choice and prompts (docs).")))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
