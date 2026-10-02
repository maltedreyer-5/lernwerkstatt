# -*- coding: utf-8 -*-
"""Replaces single blocks that cannot be repaired by a readable substitute.

Without this layer the final gate would be all-or-nothing: one broken
Mermaid diagram in one of twelve lessons would fail the whole unit —
although it would be fully usable for the learner and the rest of the
production is fine.

This layer runs AFTER all repair attempts and BEFORE the gate. Whatever is
still broken then is not thrown away but downgraded: the block is replaced
by its own description as text. The learner loses the graphic but keeps
the statement; the error becomes a warning, and the report states what was
replaced.

Deliberately limited: only DISPLAYING blocks are replaced, and only if
they have a usable `description`. Structural flaws (missing lessons,
broken IDs, tasks that cannot be answered) stay blocking — they are not a
matter of display, and a substitute text would hide them.
"""
from __future__ import annotations

from src.i18n import Msg
from src.unit import i18n

import re

# Only these types can be replaced: their contribution can be carried in
# words. Interactions are NOT listed — replacing a quiz by its description
# takes the activity from the learner and fakes completeness.
REPLACEABLE = {"diagram", "chart", "formula", "simulator", "widget"}




def _esc(t: str) -> str:
    return (str(t or "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def _substitute(blk: dict, language: str = "en") -> dict | None:
    """Builds the text substitute for a broken block.

    None if there is no usable content — then the error stays, instead of
    putting in an empty shell.
    """
    type_ = blk.get("type")
    description = (blk.get("description") or "").strip()
    if not description:
        # Invented types often carry their content in other fields.
        for field_ in ("html", "task", "question", "title", "text"):
            value = blk.get(field_)
            if isinstance(value, str) and len(value.strip()) >= 25:
                description = re.sub(r"<[^>]+>", " ", value).strip()
                break
    if len(description) < 25:
        return None
    # The replacement must be CLEAN: if the description were taken over raw and
    # contained LaTeX remnants such as "q_{m+1}", the validator would report
    # them again, and the error would survive its own downgrade.
    from src.unit.normalization import normalise_text_field
    description = normalise_text_field(description)[0]
    addition = ""
    if type_ == "formula" and isinstance(blk.get("latex"), str):
        addition = f" <code>{_esc(blk['latex'])}</code>"
    return {
        "type": "note", "variant": "info",
        # Shown in the unit, so in the unit's language.
        "html": (f"<p><strong>{i18n.table_(language).get('not_displayable_' + type_, i18n.table_(language)['not_displayable'])}"
                 f"</strong> {_esc(description[:600])}{addition}</p>"),
    }


def _known_types() -> set[str]:
    from src.unit.validator import _CHECKERS
    return set(_CHECKERS)


def _blocklist(unit: dict):
    """(container, index, block, path prefix) for all blocks of the unit."""
    for li, l in enumerate(unit.get("lessons") or []):
        for bi, b in enumerate(l.get("blocks") or []):
            if isinstance(b, dict):
                yield l["blocks"], bi, b, f"lesson[{li}]({l.get('id')}).block[{bi}]"
    for mi, m in enumerate(unit.get("modules") or []):
        for bi, b in enumerate(m.get("exercises") or []):
            if isinstance(b, dict):
                # The exact path the validator writes, title included;
                # otherwise its findings would never match these blocks.
                yield m["exercises"], bi, b, f"modules[{mi}]({m.get('title', '?')}).exercises[{bi}]"


# The most recently downgraded blocks in their original form. The pipeline
# writes them into the job folder, so that the cause stays traceable.
discarded: list[dict] = []


def downgrade(unit: dict, finding) -> list[str]:
    """Replaces broken displaying blocks and reports what was replaced.

    `finding` is the result of the validation; blocks are matched through
    the path prefix in the error message. Returns the list of replacements.
    """
    # Empty FIRST, even with a finding free of errors: otherwise a later run
    # writes the discarded blocks of the previous one into its job folder.
    discarded.clear()
    if not getattr(finding, "errors", None):
        return []
    replaced: list[str] = []
    known = _known_types()
    for container, bi, blk, path_ in list(_blocklist(unit)):
        # Invented block types ("interaktiv", for instance) cannot be displayed
        # by any renderer. They are no reason to block an otherwise finished
        # unit, though, if their content can be carried in words.
        unknown = blk.get("type") not in known
        if not unknown and blk.get("type") not in REPLACEABLE:
            continue
        affected = [f for f in finding.errors if f.startswith(path_)]
        if not affected:
            continue
        new_ = _substitute(blk, unit.get("language") or "en")
        if new_ is None:
            continue
        # Keep the original BEFORE it is replaced. Otherwise the rescue
        # destroys the cause: the broken source would be nowhere to be found
        # afterwards, and the error could not be traced.
        discarded.append({"path": path_, "type": blk.get("type"),
                          "findings": affected[:3], "block": blk})
        container[bi] = new_
        reason = re.sub(r"^.*?:\s*", "", affected[0])[:90]
        replaced.append(Msg("{location} ({type}) → replaced by text — {reason}",
                            {"location": path_, "type": blk.get("type"), "reason": reason}))
    return replaced
