# -*- coding: utf-8 -*-
"""Marks glossary terms in the lesson text for the hover explanation.

Deliberately at ASSEMBLY time, not in `unit.json`: the marking is
presentation, not content. So the unit stays the editable source, rework
and repeated runs stay idempotent, and the Word export gets the text
unmarked (there the overall glossary at the end carries it).

Deterministic, not produced by the model — otherwise the markup would be
inconsistent, cost tokens and drift between lessons.

The definition is NOT in the markup but looked up by `shell.html` in
`UNIT.glossary`. With forty occurrences of a term it would otherwise be in
the file forty times.
"""
from __future__ import annotations

import re

# Zones in which nothing is marked: source code, formulas, existing links
# and headings (the markup disturbs the typography there).
_TABU = re.compile(
    r"(<code\b.*?</code>|<pre\b.*?</pre>|<math\b.*?</math>|<a\b.*?</a>"
    r"|<h[34]\b.*?</h[34]>|<span class=\"term\".*?</span>)", re.S | re.I)
_TAG = re.compile(r"<[^>]+>")

# Inflection endings that may follow a term without making it another word.
# Without this tolerance "Konformitätsbewertungen" would stay unmarked while
# "Konformitätsbewertung" is marked — exactly the inconsistency that shows.
_ENDINGS = r"(?:en|es|er|em|ns|n|e|s)?"
# Adjective endings in multi-word terms: "Freies Morphem" appears in the
# text as "freie Morpheme" or "des freien Morphems". Without this tolerance
# exactly those technical terms stay unmarked that are in the glossary as
# adjective-noun combinations — in a real unit that was a quarter of the
# entries.
_ADJ_ENDING = re.compile(r"(es|er|en|em|e)$", re.I)

def slug(term: str) -> str:
    """Must match the `slug` function in shell.html CHARACTER BY CHARACTER.

    The hover looks the definition up through `TERM_INDEX[data-term]`; a
    different key silently gives no popover. That is why this deliberately
    does NOT unicode-normalise: JavaScript does not either, and "Naïve
    Bayes" must become "na-ve-bayes" on both sides, not once "naive-bayes"
    and once "na-ve-bayes".

    tests/test_slug_parity.py checks the parity against the real JS
    implementation.
    """
    t = str(term or "").lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        t = t.replace(a, b)
    t = re.sub(r"[^a-z0-9]+", "-", t)
    return t.strip("-") or "abschnitt"


def _pattern(term: str) -> re.Pattern | None:
    """Search pattern for a term, tolerant of inflection.

    Parenthetical additions are disambiguation in the glossary, not part of
    the wording: "Anbieter (KI-Verordnung)" is searched as "Anbieter".
    """
    core = re.sub(r"\s*\([^)]*\)\s*", " ", term or "").strip()
    if len(core) < 3:
        return None
    words = core.split()

    def _part(w: str, last: bool) -> str:
        if last:
            return re.escape(w) + _ENDINGS
        # Determining word (mostly an adjective): cut off its own ending, allow
        # any admissible one back. Upper/lower case open, because adjectives
        # are written in lower case inside a sentence.
        stem = _ADJ_ENDING.sub("", w)
        if len(stem) < 3:
            stem = w
        header = re.escape(stem[0])
        return f"[{header.upper()}{header.lower()}]{re.escape(stem[1:])}(?:es|er|en|em|e)?"

    if len(words) == 1:
        core_re = _part(words[0], True)
    else:
        core_re = r"[\s\-]".join(
            [_part(w, False) for w in words[:-1]] + [_part(words[-1], True)])
    return re.compile(rf"(?<![\w-]){core_re}(?![\w-])")


def mark_terms(html: str, terms: list[dict]) -> tuple[str, int]:
    """Marks all occurrences of the terms in an HTML field.

    Longest match first, so that "Risikomanagementsystem" does not fall
    apart into "Risikomanagement" + rest. Overlaps are discarded.
    """
    if not html or not terms:
        return html or "", 0

    candidates_ = sorted(
        ((b, m) for b in terms if (m := _pattern(b.get("term", "")))),
        key=lambda p: -len(p[0].get("term", "")))

    def _section(text: str) -> tuple[str, int]:
        evidenced: list[tuple[int, int]] = []
        hits: list[tuple[int, int, str]] = []
        for b, pattern in candidates_:
            for m in pattern.finditer(text):
                a, e = m.span()
                if any(a < be and en < e or (a >= be and a < en) or (e > be and e <= en)
                       for be, en in evidenced):
                    continue
                evidenced.append((a, e))
                hits.append((a, e, b["term"]))
        if not hits:
            return text, 0
        hits.sort(key=lambda t: -t[0])
        for a, e, term in hits:
            text = (text[:a]
                    + f'<span class="term" data-term="{slug(term)}" tabindex="0" '
                      f'role="button" aria-haspopup="true">{text[a:e]}</span>'
                    + text[e:])
        return text, len(hits)

    # Leave out the taboo zones, then replace only outside of tags
    parts = _TABU.split(html)
    total = 0
    for i, part in enumerate(parts):
        if i % 2 == 1:                     # Tabu-Zone
            continue
        pieces = re.split(r"(<[^>]+>)", part)
        for j, st in enumerate(pieces):
            if st.startswith("<"):
                continue
            pieces[j], n = _section(st)
            total += n
        parts[i] = "".join(pieces)
    return "".join(parts), total


def mark_unit(unit: dict) -> int:
    """Marks all lesson texts of (a copy of) the unit. Returns the hits.

    Also takes concepts of class R into account that are only in the
    glossary — that is where the hover explanation helps most, because
    there is no lesson one could read up in.
    """
    terms = [g for g in (unit.get("glossary") or []) if g.get("term")]
    if not terms:
        return 0
    total = 0
    for l in unit.get("lessons") or []:
        for b in l.get("blocks") or []:
            if b.get("type") in ("text", "note") and isinstance(b.get("html"), str):
                b["html"], n = mark_terms(b["html"], terms)
                total += n
    return total
