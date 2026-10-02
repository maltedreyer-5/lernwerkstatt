# -*- coding: utf-8 -*-
"""Pickup codes, deletion and aborting queued jobs.

Jobs are reachable only through their pickup code; the register stores its
hash, never the code. Deleting a job removes its folder and its register row.
A job still waiting in the queue must be removable without ever starting.
"""
import asyncio
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.core.jobs import JobRegister, normalise_code  # noqa: E402


def _register(tmp: str) -> JobRegister:
    return JobRegister(Path(tmp) / "jobs.sqlite")


def test_code_roundtrip_and_hash_only():
    with tempfile.TemporaryDirectory() as tmp:
        reg = _register(tmp)
        no = reg.new_("A")
        code = reg.issue_code(no)
        assert len(normalise_code(code)) == 12
        assert reg.find_by_code(code)["number"] == no
        # Case, separators and look-alike letters do not matter.
        assert reg.find_by_code(code.lower().replace("-", " "))["number"] == no
        raw = (Path(tmp) / "jobs.sqlite").read_bytes()
        assert normalise_code(code).encode() not in raw, "code stored in plain text"
        print("  ok   code finds its job; only the hash is stored")


def test_wrong_and_reissued_codes():
    with tempfile.TemporaryDirectory() as tmp:
        reg = _register(tmp)
        no = reg.new_("A")
        old = reg.issue_code(no)
        assert reg.find_by_code("0000-0000-0000") is None
        assert reg.find_by_code("") is None and reg.find_by_code("ÄÖÜ") is None
        new = reg.issue_code(no)
        assert reg.find_by_code(old) is None, "reissuing must invalidate the old code"
        assert reg.find_by_code(new)["number"] == no
        print("  ok   unknown codes fail; a reissued code replaces the old one")


def test_codes_are_distinct():
    with tempfile.TemporaryDirectory() as tmp:
        reg = _register(tmp)
        codes = {reg.issue_code(reg.new_(str(i))) for i in range(50)}
        assert len(codes) == 50
        print("  ok   50 jobs, 50 distinct codes")


def test_delete_removes_folder_and_row():
    with tempfile.TemporaryDirectory() as tmp:
        reg = _register(tmp)
        no = reg.new_("A")
        folder = Path(tmp) / f"job-{no:04d}-a"
        folder.mkdir()
        (folder / "00-material-full-text.txt").write_text("secret", encoding="utf-8")
        reg.update(no, folder=str(folder))
        code = reg.issue_code(no)
        assert reg.delete(no, with_folder=True)
        assert not folder.exists() and reg.get_(no) is None
        assert reg.find_by_code(code) is None
        print("  ok   deleting removes folder, full text and register row")


def test_delete_refuses_paths_outside_work_dir():
    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as other:
        reg = _register(tmp)
        no = reg.new_("A")
        victim = Path(other) / "keep"
        victim.mkdir()
        reg.update(no, folder=str(victim))
        assert not reg.delete(no, with_folder=True)
        reg.delete_all(Path(tmp))
        assert victim.exists(), "delete_all removed a folder outside the work dir"
        print("  ok   folders outside the work directory are never deleted")


def test_queued_job_can_be_aborted():
    from src.pipeline import job_runner as al

    class _P:
        stop_signal = None

    started: list[int] = []

    async def work(run):
        started.append(run.job)
        await asyncio.sleep(0.2)

    async def main(tmp):
        os.environ["JOBS_PARALLEL"] = "1"
        try:
            first = al.start(9001, Path(tmp), _P(), work)
            queued = al.start(9002, Path(tmp), _P(), work)
            assert queued.waiting, "second job should wait"
            assert al.abort(9002), "a queued job must be abortable"
            assert not queued.waiting and queued.status() == "aborted"
            await first.task
            await asyncio.sleep(0.05)
            assert 9002 not in started, "aborted queued job was started anyway"
        finally:
            os.environ.pop("JOBS_PARALLEL", None)
            for no in (9001, 9002):
                al._REGISTER.pop(no, None)

    with tempfile.TemporaryDirectory() as tmp:
        asyncio.run(main(tmp))
    print("  ok   a queued job is removed from the queue and never starts")


if __name__ == "__main__":
    test_code_roundtrip_and_hash_only()
    test_wrong_and_reissued_codes()
    test_codes_are_distinct()
    test_delete_removes_folder_and_row()
    test_delete_refuses_paths_outside_work_dir()
    test_queued_job_can_be_aborted()
    print("PICKUP CODE OK")
