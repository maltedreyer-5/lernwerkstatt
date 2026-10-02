# -*- coding: utf-8 -*-
"""Job register: SQLite database with job numbers to remember.

Deliberately data-minimal: only title, status, folder and the hash of the
pickup code are stored — no learner profiles, no prior knowledge. The
actual pipeline state lies as state.json in the job's folder.
"""
from __future__ import annotations

import hashlib
import secrets
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

# Pickup codes use Crockford's base32: no I, L, O or U, so a code read aloud
# or copied by hand is hard to get wrong. 12 characters carry 60 bits.
_CODE_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_CODE_LENGTH = 12


def normalise_code(code: str) -> str:
    """Canonical form of a pickup code: upper case, no separators, and the
    look-alike letters mapped the way Crockford's base32 prescribes."""
    c = "".join(ch for ch in (code or "").upper() if ch.isalnum())
    return c.translate(str.maketrans({"O": "0", "I": "1", "L": "1"}))


def _code_hash(code: str) -> str:
    # A plain hash is enough: with 60 random bits there is nothing to guess
    # from a dictionary, so a salt would add no protection.
    return hashlib.sha256(normalise_code(code).encode("utf-8")).hexdigest()


class JobRegister:
    def __init__(self, path_: str | Path):
        self.path_ = Path(path_)
        self.path_.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS jobs (
                number INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL DEFAULT '(pending)',
                status TEXT NOT NULL DEFAULT 'created',
                folder TEXT,
                created TEXT NOT NULL,
                updated TEXT NOT NULL,
                code_hash TEXT)""")
            columns = {z["name"] for z in db.execute("PRAGMA table_info(jobs)")}
            if "code_hash" not in columns:
                db.execute("ALTER TABLE jobs ADD COLUMN code_hash TEXT")
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS jobs_code "
                       "ON jobs(code_hash)")

    def _db(self) -> sqlite3.Connection:
        # WAL and a busy timeout are needed for parallel operation: when
        # several jobs run at the same time, they write their status every
        # second. Without WAL every write locks the file, and the second job
        # fails with "database is locked".
        db = sqlite3.connect(self.path_, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA busy_timeout=15000")
        return db

    def new_(self, title: str = '(pending)') -> int:
        now = datetime.now().isoformat(timespec="seconds")
        with self._db() as db:
            cur = db.execute(
                "INSERT INTO jobs (title, status, created, updated) VALUES (?,?,?,?)",
                (title, "created", now, now))
            return int(cur.lastrowid)

    def update(self, number: int, status: str | None = None,
                     title: str | None = None, folder: str | None = None) -> None:
        fields_, values = ["updated = ?"], [datetime.now().isoformat(timespec="seconds")]
        for name, value in (("status", status), ("title", title), ("folder", folder)):
            if value is not None:
                fields_.append(f"{name} = ?")
                values.append(value)
        with self._db() as db:
            db.execute(f"UPDATE jobs SET {', '.join(fields_)} WHERE number = ?",
                       (*values, number))

    def issue_code(self, number: int) -> str:
        """Issue a new pickup code for a job and return it in readable form.

        Only the hash is stored; the code itself is shown to the user once
        and cannot be recovered. Issuing a new code invalidates the old one.
        """
        raw = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))
        with self._db() as db:
            db.execute("UPDATE jobs SET code_hash = ? WHERE number = ?",
                       (_code_hash(raw), number))
        return "-".join(raw[i:i + 4] for i in range(0, _CODE_LENGTH, 4))

    def find_by_code(self, code: str) -> dict | None:
        """Look a job up by its pickup code. Unknown codes give None."""
        if len(normalise_code(code)) != _CODE_LENGTH:
            return None
        with self._db() as db:
            line = db.execute("SELECT * FROM jobs WHERE code_hash = ?",
                               (_code_hash(code),)).fetchone()
            return dict(line) if line else None

    def get_(self, number: int) -> dict | None:
        with self._db() as db:
            line = db.execute("SELECT * FROM jobs WHERE number = ?", (number,)).fetchone()
            return dict(line) if line else None

    def delete(self, number: int, with_folder: bool = True) -> bool:
        """Removes a job from the register and optionally from disk.

        Deleting the folder in the file system alone works too — the job list
        reads what is on disk — but leaves an orphaned row in the database.
        `cleanup()` removes such rows afterwards.
        """
        rec = self.get_(number)
        if rec is None:
            return False
        if with_folder and rec.get("folder"):
            folder = Path(rec["folder"])
            # Safety net: only delete directories below the register file, so
            # that a tampered entry cannot hit anything else.
            if not self._inside_work_dir(folder):
                return False
            shutil.rmtree(folder, ignore_errors=True)
        with self._db() as db:
            db.execute("DELETE FROM jobs WHERE number = ?", (number,))
        return True

    def _inside_work_dir(self, folder: Path) -> bool:
        try:
            folder.resolve().relative_to(self.path_.parent.resolve())
            return True
        except ValueError:
            return False

    def cleanup(self) -> list[int]:
        """Removes register rows whose folder no longer exists.

        This keeps the register consistent even when job folders were
        deleted by hand.
        """
        removed = []
        with self._db() as db:
            for line in db.execute("SELECT number, folder FROM jobs").fetchall():
                folder = line["folder"]
                if folder and not Path(folder).exists():
                    db.execute("DELETE FROM jobs WHERE number = ?", (line["number"],))
                    removed.append(line["number"])
        return removed

    def delete_all(self, root: Path | str | None = None) -> int:
        """Empties the register and the work directory completely.

        The counter starts at 1 again afterwards. Running productions are
        NOT aborted — they should be finished beforehand.
        """
        count = 0
        with self._db() as db:
            for line in db.execute("SELECT folder FROM jobs").fetchall():
                if line["folder"] and Path(line["folder"]).exists() \
                        and self._inside_work_dir(Path(line["folder"])):
                    shutil.rmtree(line["folder"], ignore_errors=True)
                count += 1
            db.execute("DELETE FROM jobs")
            db.execute("DELETE FROM sqlite_sequence WHERE name = 'jobs'")
        # Also remove folders that were never in the register
        basis = Path(root) if root else self.path_.parent
        for rest in basis.glob("job-*"):
            if rest.is_dir():
                shutil.rmtree(rest, ignore_errors=True)
                count += 1
        return count

    def list_(self, n: int = 20) -> list[dict]:
        with self._db() as db:
            return [dict(z) for z in db.execute(
                "SELECT * FROM jobs ORDER BY number DESC LIMIT ?", (n,))]
