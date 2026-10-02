#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Maintenance of the work directory.

Job folders can be deleted by hand — the job list reads what is on disk.
That leaves an orphaned row in the SQLite register, though. This tool
cleans that up and also offers a complete reset.

    python scripts/cleanup.py            # remove orphaned register rows
    python scripts/cleanup.py --list     # show what is there
    python scripts/cleanup.py --delete 12 13
    python scripts/cleanup.py --all      # delete EVERYTHING, counter back to 1
    python scripts/cleanup.py --code 12  # new pickup code for job 12
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import WORK_DIR_PATH  # noqa: E402
from src.core.jobs import JobRegister  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--list", dest="list_", action="store_true", help="show what is there")
    p.add_argument("--delete", nargs="+", type=int, metavar="NR",
                   help="delete single jobs including their folders")
    p.add_argument("--all", dest="all_", action="store_true",
                   help="empty the register and the work directory completely")
    p.add_argument("--code", type=int, metavar="NR",
                   help="issue a new pickup code for a job (the previous one becomes invalid)")
    p.add_argument("--yes", action="store_true", help="skip the confirmation")
    a = p.parse_args()

    reg = JobRegister(WORK_DIR_PATH / "jobs.sqlite")

    if a.list_:
        rows = reg.list_(200)
        if not rows:
            print("No jobs in the register.")
            return 0
        print(f"{'No':>5}  {'Status':<14} {'Folder':<8} Title")
        for z in rows:
            da = "yes" if z.get("folder") and Path(z["folder"]).exists() else "MISSING"
            print(f"{z['number']:>5}  {z.get('status',''):<14} {da:<8} {z.get('title','')[:50]}")
        return 0

    if a.code is not None:
        if reg.get_(a.code) is None:
            print(f"job {a.code}: not found")
            return 1
        print(f"job {a.code}: new pickup code {reg.issue_code(a.code)}")
        return 0

    if a.all_:
        if not a.yes:
            print(f"Deletes ALL jobs and folders under {WORK_DIR_PATH}.")
            if input("Really? [type 'delete'] ") != "delete":
                print("Cancelled.")
                return 1
        n = reg.delete_all(WORK_DIR_PATH)
        print(f"{n} jobs removed, counter reset to 1.")
        return 0

    if a.delete:
        for no in a.delete:
            print(f"job {no}: {'deleted' if reg.delete(no) else 'not found'}")
        return 0

    removed = reg.cleanup()
    print(f"{len(removed)} orphaned register rows removed"
          + (f": {removed}" if removed else "."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
