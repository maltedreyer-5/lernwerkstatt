# -*- coding: utf-8 -*-
"""Uploaded originals are removed as soon as their text has been read.

Gradio stores every upload in its cache directory. The extracted text is all
the pipeline needs, so the original must not stay behind there. Needs the
installed gradio package and is skipped without it.
"""
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _optional import installed  # noqa: E402


def test_uploads_are_deleted_after_reading():
    if not installed("gradio"):
        print("  ---  gradio not installed, skipped")
        return
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["WORK_DIR"] = str(Path(tmp) / "work")
        from src.ui.wizard import _read_uploads
        good = Path(tmp) / "notes.md"
        good.write_text("# Notes\nSome content.", encoding="utf-8")
        bad = Path(tmp) / "broken.pdf"
        bad.write_bytes(b"not a pdf")
        texts = _read_uploads([str(good), str(bad)])
        assert "Some content." in texts["notes.md"]
        assert texts["broken.pdf"].startswith("[")
        assert not good.exists() and not bad.exists(), "upload left in the cache"
    print("  ok   uploads are read, then removed — also when reading fails")


if __name__ == "__main__":
    test_uploads_are_deleted_after_reading()
    print("UPLOAD CLEANUP OK")
