# -*- coding: utf-8 -*-
"""Decouples production from the browser session.

Production runs in a server-side task. The interface starts it and
afterwards only polls its state. Closing the window, coming back later and
attaching again is therefore possible — a run takes up to an hour, and
running it inside a Gradio event would end it when the window closes.

Deliberately process-local: restarting the application also ends running
tasks. Only a separate worker process would help against that — worth the
effort only if the container restarts regularly. What a restart does NOT
cost is the progress: that lies in `state.json` and `unit.json`.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from src.i18n import N_, Msg, render
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger("lernwerkstatt.auftragslauf")

MAX_LINES = 600


# Display labels for the status codes returned by Run.status().
STATUS_LABEL = {"waiting": N_("waiting"), "aborted": N_("aborted"), "error": N_("error"),
                "done": N_("done"), "running": N_("running"), "interrupted": N_("interrupted")}


@dataclass
class Run:
    """A running or finished production job."""
    job: int
    folder: Path
    pipeline: object
    rows: list[str] = field(default_factory=list)
    # Phase and log lines may be Msg objects: they are shown to whoever
    # watches the job, in that viewer's language, not in the language of
    # the session that started it.
    phase: object = field(default_factory=lambda: Msg("started"))
    share: float = 0.0
    done: bool = False
    errors: str | None = None
    aborted: bool = False
    started_at: float = field(default_factory=time.time)
    updated: float = field(default_factory=time.time)
    task: asyncio.Task | None = None
    # Waits for a free slot — not started yet.
    waiting: bool = False
    work: object = None

    def notify(self, text, phase=None,
              share: float | None = None) -> None:
        if text:
            self.rows.append(text)
            del self.rows[:-MAX_LINES]
        if phase:
            self.phase = phase
        if share is not None:
            self.share = min(max(share, 0.0), 1.0)
        self.updated = time.time()

    @property
    def running(self) -> bool:
        """Computing right now. A waiting job is NOT running."""
        return self.task is not None and not self.task.done()

    @property
    def log_lines(self) -> str:
        return self.log_text("en")

    def log_text(self, lang: str | None = None) -> str:
        return "\n".join(str(render(r, lang)) for r in self.rows[-400:])

    def status(self) -> str:
        if self.waiting and not self.done:
            return "waiting"
        if self.aborted:
            return "aborted"
        if self.errors:
            return "error"
        if self.done:
            return "done"
        return "running" if self.running else "interrupted"


_REGISTER: dict[int, Run] = {}


# How many jobs may compute AT THE SAME TIME. The rest waits visibly in a
# queue.
#
# Why at job level and not per request: a process-wide request limit acts like
# a queue without fairness — the first job occupies the slots, later ones only
# follow as it drains, and meanwhile look as if they were dead. Without any
# limit ten jobs flood the endpoint: every request waits THERE, runs into the
# client timeout and takes its job down with it.
#
# At job level every running job gets its full parallelism, the endpoint sees a
# predictable load, and waiting jobs report their position instead of staying
# silent.
def _parallel_limit() -> int:
    try:
        return max(int(os.getenv("JOBS_PARALLEL", "3")), 1)
    except ValueError:
        return 3


_QUEUE: list[int] = []


def _running() -> list[int]:
    return [no for no, l in _REGISTER.items() if l.running and not l.waiting]


def _start_next() -> None:
    """Starts waiting jobs as long as slots are free."""
    while _QUEUE and len(_running()) < _parallel_limit():
        no = _QUEUE.pop(0)
        run = _REGISTER.get(no)
        if run is None or run.done or run.aborted:
            continue
        run.waiting = False
        run.notify("Warteschlange verlassen — Produktion beginnt.",
                   phase=Msg("Chapter {done}/{total}", {"done": 0, "total": "?"}))
        run.task = asyncio.create_task(_wrapper(run))
        _write_status(run)
    _report_positions()


def _report_positions() -> None:
    for pos, no in enumerate(_QUEUE, 1):
        run = _REGISTER.get(no)
        if run is not None:
            run.phase = Msg("waiting · position {pos} of {total}", {"pos": pos, "total": len(_QUEUE)})
            run.updated = time.time()


async def _wrapper(run: "Run") -> None:
    """Does the work and releases the slot afterwards.

    An error ends ONLY this job: it is recorded in the run, the
    intermediate state stays on disk, and the next waiting job moves up.
    """
    try:
        await run.work(run)
    except asyncio.CancelledError:
        run.aborted = True
        run.notify(Msg("Aborted."), phase=Msg("aborted"))
        raise
    except Exception as e:  # noqa: BLE001 — the error belongs in the run
        run.errors = f"{type(e).__name__}: {e}"
        run.notify(Msg("⚠️ Aborted: {error}. The intermediate state is in the job folder; the job can "
                       "be continued with its pickup code.", {"error": run.errors}), phase=Msg("Error"))
        log.exception("Job %s aborted", run.job)
    finally:
        run.done = True
        run.updated = time.time()
        _write_status(run)
        # Release the slot, also after an error or an abort.
        try:
            _start_next()
        except Exception:  # noqa: BLE001
            log.exception("moving up from the queue failed")


def start(job: int, folder: Path, pipeline, work) -> Run:
    """Accepts a job — at once or into the queue.

    `work` is a coroutine function that gets the run as its only argument
    and reports through `run.notify(...)`.
    """
    alt = _REGISTER.get(job)
    if alt is not None and (alt.running or alt.waiting):
        return alt                      # running or waiting — not twice

    run = Run(job=job, folder=Path(folder), pipeline=pipeline)
    run.work = work
    _REGISTER[job] = run

    if len(_running()) >= _parallel_limit():
        run.waiting = True
        _QUEUE.append(job)
        _report_positions()
        run.notify(Msg("In the queue (position {pos}). {running} jobs run at the same time; this "
                       "one starts automatically as soon as a slot is free.",
                       {"pos": len(_QUEUE), "running": len(_running())}))
        _write_status(run)
        return run

    run.task = asyncio.create_task(_wrapper(run))
    _write_status(run)
    return run


def get_(job: int | None) -> Run | None:
    if job is None:
        return None
    try:
        return _REGISTER.get(int(job))
    except (TypeError, ValueError):
        return None


def abort(job: int, immediately: bool = False) -> bool:
    """Aborts a running job.

    First the pipeline's stop signal (clean exit at the next chapter
    boundary), then, as a last resort, cancelling the task. `immediately`
    skips the clean exit — for deletion, where the state is discarded
    anyway.
    """
    run = get_(job)
    if run is None:
        return False
    if run.waiting and not run.running:
        # Still in the queue: take it out, so it never starts. Without this a
        # queued job could not be stopped at all, and a job deleted while
        # waiting would later start on a folder that no longer exists.
        run.aborted = True
        run.waiting = False
        if job in _QUEUE:
            _QUEUE.remove(job)
        run.notify(Msg("Removed from the queue."))
        _report_positions()
        return True
    if not run.running:
        return False
    signal = getattr(run.pipeline, "stop_signal", None)
    if not immediately and signal is not None and hasattr(signal, "request"):
        signal.request()
        run.notify(Msg("Abort requested — stops at the next chapter boundary."))
        return True
    run.task.cancel()
    return True


def _write_status(run: Run) -> None:
    """Status file in the job folder — survives a process restart.

    Without it, after a restart one could not tell whether a job is still
    running or was aborted.
    """
    try:
        (run.folder / "run-status.json").write_text(json.dumps({
            # English text: the file is read by operators and scripts, and a
            # Msg object is not JSON.
            "job": run.job, "phase": str(render(run.phase, "en")),
            "share": round(run.share, 3), "status": run.status(),
            "errors": run.errors, "updated": run.updated,
            "started_at": run.started_at,
        }, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass


def overview(root: Path, at_most: int = 25) -> list[dict]:
    """All jobs in the work directory, with status.

    The source is the file system, enriched with the process register — so
    jobs from before a restart appear as well.
    """
    rows = []
    for folder in sorted(Path(root).glob("job-*"), reverse=True):
        z = folder / "state.json"
        if not z.exists():
            continue
        try:
            data_ = json.loads(z.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        no = data_.get("job")
        title = ((data_.get("gap") or {}).get("title")
                 or (data_.get("profile") or {}).get("thema") or folder.name)
        run = get_(no)
        if run is not None:
            status, phase = run.status(), run.phase
        else:
            status, phase = "interrupted", "—"
            try:
                s = json.loads((folder / "run-status.json").read_text(encoding="utf-8"))
                # After a restart nothing is running any more, whatever it says
                # there.
                status = "interrupted" if s.get("status") == "running" else s.get("status", "—")
                phase = s.get("phase", "—")
            except (OSError, json.JSONDecodeError):
                pass
            if (folder / "dist").exists() and any((folder / "dist").glob("*.html")):
                if status in ("—", "interrupted"):
                    status = "abgeschlossen"
        rows.append({"job": no, "title": title, "status": status,
                       "phase": phase, "folder": str(folder),
                       "changed": z.stat().st_mtime})
    rows.sort(key=lambda x: -x["changed"])
    return rows[:at_most]


def as_table(rows: list[dict]) -> list[list]:
    return [[z["job"], z["title"][:60], z["status"], z["phase"][:40]]
            for z in rows]
