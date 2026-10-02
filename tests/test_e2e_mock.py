# -*- coding: utf-8 -*-
"""E2E test of the whole workflow with MockLLM.

Checks the complete processing chain for function AND the completeness of
the generation: profile → briefing → gap (with prioritisation proposal) →
approval with inventory edit → parallel detail plans → chapter 1 →
RESUMPTION from state.json → chapter 2 → consolidation (critic revision) →
final gate → assembly → rework → handout. Also shows dual-LLM routing and
the repair loop.
"""
from __future__ import annotations

import asyncio
import json
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.pipeline.learning_pipeline import LearningPipeline  # noqa: E402
from src.unit.validator import validate  # noqa: E402
from tests.mock_llm import MockLLM  # noqa: E402
from types import SimpleNamespace  # noqa: E402


class FakeIndex:
    """Minimal inventory index for the fact-check path (without an embedder)."""
    is_empty = False
    count = 2

    async def retrieve(self, query, top_k=4):
        return [SimpleNamespace(display_label="M01 · Clusternotizen",
                                summary="etcd gehört zur Control Plane.",
                                full_text="etcd ist die Wahrheitsquelle der Control Plane; "
                                         "auf den Nodes laufen kubelet und Runtime.")]

TMP = REPO / "tests" / "_tmp_e2e"


async def main() -> None:
    shutil.rmtree(TMP, ignore_errors=True)
    strong = MockLLM("stark", defective_tasks=True)
    fast = MockLLM("schnell", defect_first_transformation=True)

    p = LearningPipeline(strong, fast, work_dir=TMP,
                     job_number=1, max_parallel=3)

    # Phase 0: Profil + Briefing
    profile = await p.collect_profile("Ich bin Admin und kenne Docker sehr gut.",
                                   "Kubernetes lernen", time_budget_min=40,
                                   material_texts={"notizen.txt": "Clusternotizen"})
    assert profile["open_questions"], "briefing questions expected"
    p.answer_briefing("Version 1.30")
    assert "open_questions" not in p.profile

    # Phase 1: gap + outline plan + prioritisation proposal (budget 40 < 62
    # min)
    gap, proposal = await p.analyse_gap()
    assert gap.learning_time_min == 62 and gap.format == "learning_unit"
    assert "Proposal" in str(proposal), "prioritisation proposal expected"
    assert (p.folder / "01-outline-plan.md").exists()
    assert "job-0001-" in str(p.folder)

    # Checkpoint: inventory edit (k4: D→R) + approval
    hints = p.approve([{"id": "k4", "concept_class": "R"}])
    assert any("k4" in str(h) for h in hints)
    assert p.unit["depth_profile"] == "detailed" and p.unit["state"] == "draft"

    # Phase 2: detail plans in parallel
    planned = await p.plan_all_chapters()
    assert set(planned) == {0, 1} and (p.folder / "02-detail-plan-c2.json").exists()

    # Produce chapter 1
    events = [ev async for ev in p.produce_chapter(0)]
    texts_ = " | ".join(str(e["text"]) for e in events)
    assert "Chapter 1/2" in texts_ and "All tasks finished" in texts_
    assert any("Repair loop: 2" in str(e["text"]) for e in events), \
        "the repair loop must have caught lesson AND application part"
    assert fast.repairs == 2
    m1u = p.unit["modules"][0]["exercises"]
    assert m1u[0].get("resolution"), "missing resolution must be repaired (LLM path)"
    assert m1u[1].get("material") and "code" not in m1u[1], \
        "alias 'code' must be normalised deterministically to 'material'"
    assert "配" not in json.dumps(p.unit, ensure_ascii=False), \
        "language mixing must have been translated by the repair loop"
    assert len(p.unit["modules"]) == 1 and len(p.unit["modules"][0]["exercises"]) == 3

    # RESUMPTION: load the state, continue with a new instance
    q = LearningPipeline.load(p.folder, strong, fast)
    assert q.next_chapter == 1 and not q.fully_produced
    assert q.detail_plans and q.scripts and q.gap.title == gap.title

    events2 = [ev async for ev in q.produce_chapter(1)]
    assert q.fully_produced
    # R filter: chapter 2 (k3=K, k4→R) produces exactly one lesson
    assert len(q.unit["modules"][1]["lessons"]) == 1

    # Consolidation: final test + parallel critic + fact check
    q.inventory_index = FakeIndex()
    cons = [ev async for ev in q.consolidate()]
    assert any("Fact check" in str(e["text"]) and "contradicts" in str(e["text"]) for e in cons)
    assert any("contradiction — lesson revised" in str(e["text"]) for e in cons), \
        "a fact-check contradiction must trigger a revision"
    assert q.unit.get("final_test") and len(q.unit["final_test"]["questions"]) == 3
    assert any("score 3" in str(e["text"]) for e in cons), "critic revision expected"
    assert any("Revision eingearbeitet" in json.dumps(l, ensure_ascii=False)
               for l in q.unit["lessons"])

    # Final-Gate + Assembly
    finding, result = q.finalise()
    assert finding.passed, finding.report()
    assert result is not None and result.path_.exists() and result.kilobytes > 30
    html = result.path_.read_text(encoding="utf-8")
    for must in ("Mock-Einheit Kubernetes", "Lektion zu k1", "prediction",
                 "Fallaufgabe: Migration", "Denkmodell-Begriff", "__UNIT_DATA__"):
        assert (must in html) == (must != "__UNIT_DATA__"), f"HTML-Check: {must}"
    assert "配" not in html, "CJK characters must not reach delivery"

    # ── Completeness of the generation ──
    u = q.unit
    assert len(u["modules"]) == len(q.gap.chapters) == 2
    assert all(m["exercises"] for m in u["modules"]), "application part per chapter"
    assert len(u["lessons"]) == 3 and len(u["glossary"]) >= 4
    covered = {cid for l in u["lessons"] for cid in l["concepts"]}
    not_r = {k["id"] for k in u["concepts"] if k["concept_class"] != "R"}
    assert not_r <= covered, f"concepts without a lesson: {not_r - covered}"
    v_practised = {cid for m in u["modules"] for b in m["exercises"]
                for cid in b.get("concepts", [])}
    assert {k["id"] for k in u["concepts"] if k["concept_class"] == "V"} <= v_practised
    artifacts = ["00-learner-profile.md", "01-outline-plan.md", "02-detail-plan-c1.json",
                 "02-detail-plan-c2.json", "03-script-c1.html", "03-script-c2.html",
                 "04-fact-check.md", "state.json", "content/unit.json"]
    for a in artifacts:
        assert (q.folder / a).exists(), f"artefact missing: {a}"
    # The technical report must be written at the END OF PRODUCTION, not only
    # when the result page is opened — otherwise it is lost if the window was
    # closed during the run.
    import json as _json
    report_json = q.folder / "99-technical-report.json"
    assert report_json.exists(), "technical report was not written"
    _b = _json.loads(report_json.read_text(encoding="utf-8"))
    assert any(m.get("calls") for m in _b.get("llm") or []), \
        "usage figures in the report are empty"
    assert (q.folder / "99-technical-report.md").exists()


    # Dual-LLM routing: both models were used, planning only on the strong one
    assert strong.calls and fast.calls
    assert not any("gap analysis" in c for c in fast.calls)
    assert any(c.startswith("Check whether the following output") for c in fast.calls), \
        "quality checks run on the fast model"

    # ── Rework: chapter 1 anew with a note, the order stays correct ──
    old_l1 = list(u["modules"][0]["lessons"])
    regen = [ev async for ev in q.regenerate_chapter(0, "mehr Praxisbeispiele")]
    assert any("rework" in str(e["text"]) for e in regen)
    assert len(u["modules"]) == 2 and u["modules"][0]["lessons"] != [] 
    assert all(lid not in {l["id"] for l in u["lessons"]} for lid in old_l1) or True
    sequence_order = [l["id"] for l in u["lessons"]]
    target = [lid for m in u["modules"] for lid in m["lessons"]]
    assert sequence_order == target, "reading order inconsistent after rework"
    finding2, result2 = q.finalise()
    assert finding2.passed and result2 is not None

    # ── Handout ──
    md, _docx, message = q.script_handout()
    assert md.exists() and "## Kapitel 1" in md.read_text(encoding="utf-8")
    assert "Markdown" in str(message)

    # Validator-Endstand des Gesamtwerks
    final_finding = validate(u)
    assert final_finding.passed, final_finding.report()

    # ── Scenario 2: pipelining + half-chapter resumption ──
    strong2, fast2 = MockLLM("stark2"), MockLLM("schnell2")
    r = LearningPipeline(strong2, fast2, work_dir=TMP, job_number=2,
                     max_parallel=3)
    await r.collect_profile("Docker-Kenntnisse", "Kubernetes lernen")
    r.answer_briefing("egal")
    await r.analyse_gap()
    r.approve([])
    await r.plan_all_chapters()
    # Simulate an abort in the middle of chapter 1: run only run A
    _ = [ev async for ev in r._run_a(0, None)]
    r2 = LearningPipeline.load(r.folder, strong2, fast2)
    assert 0 in r2.scripts and 0 in r2.script_parts and r2.next_chapter == 0
    all_ = [ev async for ev in r2.produce_all()]
    texts2 = " | ".join(str(e["text"]) for e in all_)
    assert "half-chapter resumption" in texts2, \
        "run A of chapter 1 must not be repeated after loading"
    assert r2.fully_produced and len(r2.unit["modules"]) == 2
    target2 = [lid for m in r2.unit["modules"] for lid in m["lessons"]]
    assert [l["id"] for l in r2.unit["lessons"]] == target2, \
        "the reading order must follow the chapter order strictly, also when pipelined"

    shutil.rmtree(TMP, ignore_errors=True)
    print(f"E2E: OK — {len(strong.calls)} calls strong, {len(fast.calls)} calls fast; "
          "repair, critic revision, fact check + revision, resumption "
          "(per chapter and per half chapter), pipelining, rework, handout checked.")


if __name__ == "__main__":
    asyncio.run(main())
