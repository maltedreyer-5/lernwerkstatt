# -*- coding: utf-8 -*-
"""German field names in model output are brought into the English format.

Models answering for a German unit sometimes use German keys — also the ones
this format used before it became English. Every parsed model answer passes
through the translation; Vega specs keep their own keys.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.llm.json_parser import parse_llm_json  # noqa: E402


def test_german_keys_and_values_become_english():
    raw = ('{"titel": "T", "lektionen": [{"id": "l1", "titel": "L", "bloecke": ['
           '{"typ": "hinweis", "variante": "merke", "html": "<p>x</p>"},'
           '{"typ": "zuordnung", "paare": [{"links": "a", "rechts": "b"}]},'
           '{"typ": "chart", "beschreibung": "d", "spec": {"data": {"values": [{"titel": 1}]}}}]}],'
           '"tiefenprofil": "kompakt"}')
    u = parse_llm_json(raw)
    assert set(u) == {"title", "lessons", "depth_profile"}, u
    assert u["depth_profile"] == "compact"
    b = u["lessons"][0]["blocks"]
    assert b[0]["variant"] == "key_point"
    assert b[1]["pairs"] == [{"left": "a", "right": "b"}]
    # the block type value itself is left to the type alias of the pipeline
    assert b[0]["type"] == "hinweis"
    assert b[2]["spec"] == {"data": {"values": [{"titel": 1}]}}, "Vega spec was changed"
    print("  ok   German keys and values translated, Vega spec untouched")


def test_english_wins_when_both_present():
    u = parse_llm_json('{"title": "english", "titel": "deutsch"}')
    assert u["title"] == "english" and u["titel"] == "deutsch", u
    print("  ok   an English key is never overwritten")


if __name__ == "__main__":
    test_german_keys_and_values_become_english()
    test_english_wins_when_both_present()
    print("LEGACY KEYS OK")
