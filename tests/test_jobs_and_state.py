# -*- coding: utf-8 -*-
"""Tests for the job register and pipeline persistence/resumption."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.core.jobs import JobRegister  # noqa: E402
from src.pipeline.gap_analysis import parse_gap  # noqa: E402
from src.pipeline.learning_pipeline import LearningPipeline  # noqa: E402

TMP = REPO / "tests" / "_tmp_arbeit"

GAP = {"kind": "extension", "interference": "medium", "interference_rationale": "x",
       "concepts": [{"id": "k1", "name": "Alpha", "concept_class": "V"},
                    {"id": "k2", "name": "Beta", "concept_class": "K"}],
       "chapters": [{"title": "Eins", "concepts": ["k1", "k2"], "learning_objectives": ["Kann A"]}],
       "unit_title": "Zustands-Test", "description": "…"}


def test_register_crud():
    shutil.rmtree(TMP, ignore_errors=True)
    reg = JobRegister(TMP / "jobs.sqlite")
    no = reg.new_()
    assert no >= 1 and reg.get_(no)["status"] == "created"
    reg.update(no, status="plan", title="Zustands-Test", folder="/x")
    rec = reg.get_(no)
    assert (rec["status"], rec["title"], rec["folder"]) == ("plan", "Zustands-Test", "/x")
    assert reg.list_(5)[0]["number"] == no
    assert reg.get_(99999) is None


def test_state_roundtrip_and_resumption():
    shutil.rmtree(TMP, ignore_errors=True)
    p = LearningPipeline(None, None, work_dir=TMP, job_number=7)
    p.profile = {"language": "de", "known_concepts": ["X"]}
    p.gap = parse_gap(GAP)
    p.folder = TMP / "job-0007-zustands-test"
    (p.folder / "content").mkdir(parents=True)
    p.approve([{"id": "k2", "concept_class": "D"}])
    p.scripts[0] = "<h3>Abschnitt</h3><p>Text</p>"
    p.detail_plans[0] = {"lessons": [{"id": "l1", "title": "Eins"}]}
    p.chapter_meta.append({"summary": "…", "new_terms": []})
    p._persist_state()

    q = LearningPipeline.load(p.folder)
    assert q.job_number == 7
    assert q.gap.title == "Zustands-Test"
    assert [k.concept_class for k in q.gap.concepts] == ["V", "D"]  # the edit survives the round trip
    assert q.unit["state"] == "draft" and q.unit["concepts"][1]["concept_class"] == "D"
    assert q.scripts[0].startswith("<h3>") and 0 in q.detail_plans
    assert q.next_chapter == 0 and not q.fully_produced

    # Handout from a loaded state: Markdown must always be produced
    md, _docx, message = q.script_handout()
    assert md.exists() and "### Abschnitt" in md.read_text(encoding="utf-8")
    assert "Markdown" in str(message)
    shutil.rmtree(TMP, ignore_errors=True)


def test_finalise_returns_draft_when_gate_blocks():
    shutil.rmtree(TMP, ignore_errors=True)
    p = LearningPipeline(None, None, work_dir=TMP)
    p.folder = TMP / "gate"
    (p.folder / "content").mkdir(parents=True)
    p.unit = {"id": "gate-test", "title": "Gate", "state": "draft",
              "lessons": [{"id": "l1", "title": "x",
                             "blocks": [{"type": "quiz", "questions": []}]}]}
    finding, result = p.finalise()
    assert not finding.passed
    assert result is not None and result.draft, \
        "a blocked gate must still deliver a draft"
    assert result.path_.name == "gate-test-draft.html" and result.path_.exists()
    assert "ENTWURF ·" in result.path_.read_text(encoding="utf-8")
    assert p.unit["state"] == "draft", "final must not stay set"
    shutil.rmtree(TMP, ignore_errors=True)


def test_coverage_guard_on_detail_plan_gap():
    """If the detail plan assigns a chapter concept to no lesson, the assembly
    attributes it to the first lesson — the final gate must never fail
    because of that."""
    from types import SimpleNamespace
    shutil.rmtree(TMP, ignore_errors=True)
    p = LearningPipeline(None, None, work_dir=TMP, job_number=9)
    p.profile = {"language": "de"}
    p.gap = parse_gap(GAP)
    p.folder = TMP / "job-0009-x"
    (p.folder / "content").mkdir(parents=True)
    p.approve([])
    plan = [{"id": "l1", "title": "Eins", "concepts": ["k1"]}]      # k2 fehlt im Plan!
    data_ = [{"id": "l1", "title": "Eins",
              "blocks": [{"type": "text", "html": "<p>x</p>"}]}]
    p._assemble_chapter(0, p.gap.chapters[0], SimpleNamespace(tasks=[]), plan, data_, [])
    tags = p.unit["lessons"][0]["concepts"]
    assert "k1" in tags and "k2" in tags, tags
    shutil.rmtree(TMP, ignore_errors=True)


def test_old_job_stays_retrievable():
    """A saved job must stay loadable and finalisable.

    Guards against a `gap_from_dict` that raises KeyError on a missing field,
    and against an `h_result` that sets its lock BEFORE the work — a single
    failure would then silence fetching the result for good.
    """
    import json as _json
    import shutil as _shutil
    import tempfile as _tempfile
    from src.pipeline.learning_pipeline import LearningPipeline

    tmp = Path(_tempfile.mkdtemp())
    folder = tmp / "job-0099-alt"
    (folder / "content").mkdir(parents=True)
    (folder / "dist").mkdir()
    unit = _json.loads((Path(__file__).resolve().parents[1]
                        / "examples" / "example-unit.json").read_text(encoding="utf-8"))
    (folder / "content" / "unit.json").write_text(
        _json.dumps(unit, ensure_ascii=False), encoding="utf-8")
    # Deliberately INCOMPLETE: that is what older states look like.
    (folder / "state.json").write_text(_json.dumps({
        "job": 99, "profile": {"thema": "T"},
        "gap": {"kind": "knowledge", "title": "Altauftrag",
                "concepts": [{"id": "k1", "name": "A", "concept_class": "V", "rationale": "b"}],
                "chapters": [{"title": "K1", "concepts": ["k1"],
                             "learning_objectives": [], "prerequisites": []}]},
    }, ensure_ascii=False), encoding="utf-8")

    p = LearningPipeline.load(folder, None, None)
    assert p.job_number == 99
    assert len(p.unit.get("lessons") or []) == len(unit["lessons"])
    assert p.fully_produced
    finding, result = p.finalise()
    assert result is not None, finding.report()

    # Usage figures: from the saved run, not from the empty counters of this
    # process — and the file must not be overwritten with zeros in the process.
    from src.pipeline import technical_report as _tb

    class _C:
        model = "m"; total_calls = 42
        total_input_tokens = 1000; total_output_tokens = 200
        total_truncated = total_empty = total_empty_rescued = 0

    class _P:
        llm = _C(); llm_fast = _C()
        losses = []; degradations = []
        terminology = None; teaching_script = None; coverage = {}

    _, real_ones = _tb.report(p.unit, _P())
    (folder / "99-technical-report.json").write_text(
        _tb.as_json(real_ones), encoding="utf-8")
    before = (folder / "99-technical-report.json").read_text(encoding="utf-8")

    # Resumption: the usage of THIS process is added to the saved state, not
    # put in its place.
    class _C2(_C):
        total_calls = 8
        total_input_tokens = 500
        total_output_tokens = 100

    p.llm = _C2(); p.llm_fast = _C2()
    p.technical_report()
    summed = _json.loads(
        (folder / "99-technical-report.json").read_text(encoding="utf-8"))
    assert all(m["calls"] == 50 for m in summed["llm"]), \
        f"usage not summed up: {[m['calls'] for m in summed['llm']]}"

    # Merely looking (counters at zero) must not touch the state.
    class _C0(_C):
        total_calls = total_input_tokens = total_output_tokens = 0

    p.llm = _C0(); p.llm_fast = _C0()
    before = (folder / "99-technical-report.json").read_text(encoding="utf-8")
    md = p.technical_report()
    assert "50" in md, "usage figures of the original run missing"
    assert (folder / "99-technical-report.json").read_text(encoding="utf-8") == before, \
        "the saved report was overwritten by viewing"
    assert "original production run" in md, "origin not shown"
    _shutil.rmtree(tmp, ignore_errors=True)
    print("OK  test_old_job_stays_retrievable")


def test_register_delete_and_cleanup():
    """Folders deleted by hand, targeted deletion and complete reset."""
    import shutil as _sh
    import tempfile as _tf
    from src.core.jobs import JobRegister

    tmp = Path(_tf.mkdtemp())
    reg = JobRegister(tmp / "jobs.sqlite")
    folder = {}
    for i in range(3):
        no = reg.new_(f"Auftrag {i}")
        o = tmp / f"job-{no:04d}-x"
        o.mkdir()
        reg.update(no, folder=str(o))
        folder[no] = o
    assert len(reg.list_()) == 3

    # A folder deleted by hand leaves an orphaned register row
    _sh.rmtree(folder[2])
    assert reg.cleanup() == [2]
    assert {z["number"] for z in reg.list_()} == {1, 3}

    # Targeted deletion removes row AND folder
    assert reg.delete(1) is True
    assert not folder[1].exists()
    assert reg.delete(999) is False

    # A complete reset also resets the counter
    reg.delete_all(tmp)
    assert reg.list_() == []
    assert reg.new_("neu") == 1
    assert not list(tmp.glob("job-*"))
    _sh.rmtree(tmp, ignore_errors=True)
    print("OK  test_register_delete_and_cleanup")


def test_parallel_operation():
    """Several jobs at the same time — separate states, no database conflict."""
    import asyncio as _a
    import shutil as _sh
    import tempfile as _tf
    from src.core.jobs import JobRegister
    from src.pipeline import job_runner as _al

    tmp = Path(_tf.mkdtemp())
    reg = JobRegister(tmp / "jobs.sqlite")
    nos = [reg.new_(f"Auftrag {i}") for i in range(3)]
    assert len(set(nos)) == 3, "job numbers not unique"

    async def _run():
        # Simultaneous status writes: without WAL and busy_timeout this ends in
        # "database is locked" as soon as two jobs run in parallel.
        async def writer(no):
            for i in range(40):
                reg.update(no, status=f"schritt-{i}")
                await _a.sleep(0.001)

        res = await _a.gather(*(writer(n) for n in nos), return_exceptions=True)
        assert not [e for e in res if isinstance(e, Exception)], \
            f"database conflict with parallel jobs: {res}"

        class _P:
            stop_signal = type("S", (), {"is_stopped": False,
                                         "stop": staticmethod(lambda: None)})

        async def work(run):
            for i in range(3):
                run.notify(f"Schritt {i}")
                await _a.sleep(0.01)

        for n in nos:
            (tmp / f"job-{n:04d}").mkdir(exist_ok=True)
            _al.start(n, tmp / f"job-{n:04d}", _P(), work)
        await _a.sleep(0.2)

    _a.run(_run())
    for n in nos:
        run = _al.get_(n)
        assert run is not None and run.status() == "done", f"job {n}: {run}"
        assert run.log_lines.count("Schritt 0") == 1, "logs mixed up"

    # Process-wide request limit: openai is missing in the test environment, so
    # mock it — only the semaphore logic is checked.
    import types as _t
    for _m in ("openai", "httpx"):
        if _m not in sys.modules:
            try:
                __import__(_m)
            except ImportError:
                _mod = _t.ModuleType(_m)
                _mod.__getattr__ = lambda a: object  # type: ignore[attr-defined]
                sys.modules[_m] = _mod
    # Process-wide limit: OFF by default. Otherwise it acts like a queue
    # without fairness — the first job occupies the slots, later ones only
    # follow.
    import importlib
    import os as _os
    import src.llm.client as _c
    _os.environ.pop("LLM_GLOBAL_MAX_CONCURRENT", None)
    importlib.reload(_c)
    assert _c._global_semaphore() is None, "the global limit is not off by default"
    _os.environ["LLM_GLOBAL_MAX_CONCURRENT"] = "8"
    importlib.reload(_c)

    async def _sem():
        s1 = _c._global_semaphore()
        assert s1 is not None and s1 is _c._global_semaphore(), \
            "a set limit gives no stable semaphore"
    _a.run(_sem())
    _os.environ.pop("LLM_GLOBAL_MAX_CONCURRENT", None)
    importlib.reload(_c)

    # Lock order: first the client's own, then the global one. The other way
    # round a task holds a global slot while it waits for its own.
    source = (Path(__file__).resolve().parents[1] / "src" / "llm" / "client.py"
              ).read_text(encoding="utf-8")
    assert "async with self._semaphore, (_global_semaphore() or _OPEN)" in source, \
        "wrong lock order: the global one must not be taken first"

    _sh.rmtree(tmp, ignore_errors=True)
    print("OK  test_parallel_operation")


def test_queue():
    """Ten jobs at the same time: none aborts, all finish.

    Without a limit they flood the endpoint, every request runs into the
    timeout there and takes its job down with it. With a REQUEST limit the
    later ones starve. The queue at JOB level solves both: every running job
    keeps its full parallelism, waiting ones report their position instead
    of staying silent.
    """
    import asyncio as _a
    import importlib
    import os as _os
    import shutil as _sh
    import tempfile as _tf

    _os.environ["JOBS_PARALLEL"] = "3"
    import src.pipeline.job_runner as _al
    importlib.reload(_al)

    class _P:
        stop_signal = type("S", (), {"is_stopped": False,
                                     "stop": staticmethod(lambda: None)})

    tmp = Path(_tf.mkdtemp())
    done = []

    async def _run():
        async def good(run):
            for i in range(3):
                run.notify(f"Schritt {i}")
                await _a.sleep(0.02)
            done.append(run.job)

        async def broken(run):
            await _a.sleep(0.01)
            raise RuntimeError("Endpunkt antwortet nicht")

        for n in range(10):
            (tmp / f"a{n}").mkdir()
            _al.start(n, tmp / f"a{n}", _P(), broken if n == 4 else good)

        # Immediately: three run, seven wait with a position
        assert len(_al._running()) == 3, f"running: {_al._running()}"
        assert len(_al._QUEUE) == 7
        pending = _al.get_(9)
        assert pending.status() == "waiting", pending.status()
        assert "position" in str(pending.phase), pending.phase

        for _ in range(400):
            if len(done) >= 9 and not _al._QUEUE:
                break
            await _a.sleep(0.02)

    _a.run(_run())

    # All but the deliberately faulty one are finished
    assert len(done) == 9, f"only {len(done)} of 9 finished"
    assert not _al._QUEUE, "queue not processed"
    broken_one = _al.get_(4)
    assert broken_one.status() == "error", broken_one.status()
    assert "intermediate state" in broken_one.log_lines, \
        "the error message does not name the intermediate state"
    # An error does NOT stop the queue
    assert all(_al.get_(n).status() == "done" for n in range(10) if n != 4)
    # Logs stay separate
    assert all(_al.get_(n).log_lines.count("Schritt 0") == 1
               for n in range(10) if n != 4)

    _os.environ.pop("JOBS_PARALLEL", None)
    _sh.rmtree(tmp, ignore_errors=True)
    print("OK  test_queue")


def test_job_loadable():
    """Express jobs must be loadable — their folder must be in the register.

    The folder is only created AFTER the gap analysis, because its name
    contains the title slug (job-0056-topic-xy). The express route must
    register it just like the checkpoint route; otherwise every pickup code
    would report "not found" although the job is running.
    """
    import json as _json
    import shutil as _sh
    import tempfile as _tf
    from src.core.jobs import JobRegister

    tmp = Path(_tf.mkdtemp())
    reg = JobRegister(tmp / "a.sqlite")
    no = reg.new_("Testauftrag")
    folder = tmp / f"job-{no:04d}-vergleichende-rechnungslegung"
    folder.mkdir()
    (folder / "state.json").write_text(_json.dumps({"job": no}), encoding="utf-8")

    # Without a register entry the fallback via the PREFIX must apply — the
    # folder name carries the title, so an exact name does not work.
    assert not (reg.get_(no) or {}).get("folder"), "starting point missed"
    hits = sorted(tmp.glob(f"job-{no:04d}-*"))
    candidate = next((k for k in hits if (k / "state.json").exists()), None)
    assert candidate == folder, f"fallback does not find the folder: {hits}"

    # With an entry as well
    reg.update(no, folder=str(folder))
    assert Path(reg.get_(no)["folder"]) == folder

    # Unknown number: no hit
    assert not sorted(tmp.glob("job-9999-*"))

    # The express route registers the folder
    source = (Path(__file__).resolve().parents[1] / "src" / "ui"
              / "wizard.py").read_text(encoding="utf-8")
    i = source.index("async def h_express")
    j = source.index("\n        s1_next.click", i)
    assert "_register_folder(pipeline)" in source[i:j], \
        "the express route does not register the folder"
    assert source.count("_register_folder(pipeline)") >= 2, \
        "both starting routes must register"

    _sh.rmtree(tmp, ignore_errors=True)
    print("OK  test_job_loadable")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"OK  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
