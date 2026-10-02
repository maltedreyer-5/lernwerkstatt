# -*- coding: utf-8 -*-
"""Sankey labels outside the German transliteration table.

The sankey-beta lexer accepts ASCII only, so labels are transliterated.
German umlauts go through a fixed table; every other character is decomposed
with Unicode NFKD. That second path raised a NameError (missing import) and
hit every Sankey diagram in French, Spanish or Italian units.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.unit.normalization import _sankey_ascii  # noqa: E402


def test_umlauts_use_the_table():
    log: list = []
    assert _sankey_ascii("sankey-beta\nKäse,Brot,5", log) == "sankey-beta\nKaese,Brot,5"
    print("  ok   umlauts transliterated by table")


def test_other_accents_are_decomposed():
    log: list = []
    out = _sankey_ascii("sankey-beta\nCafé,Économie,5\nNiño,Città,3", log)
    assert out.isascii(), out
    assert "Cafe,Economie,5" in out and "Nino,Citta,3" in out, out
    assert log, "the change is not reported"
    print("  ok   accents outside the table are decomposed to ASCII")


if __name__ == "__main__":
    test_umlauts_use_the_table()
    test_other_accents_are_decomposed()
    print("SANKEY OK")
