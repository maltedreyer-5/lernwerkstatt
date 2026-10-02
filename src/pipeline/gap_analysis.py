# -*- coding: utf-8 -*-
"""Gap analysis: concept inventory, treatment classes, derivation of scope and
format.

Pure domain logic without an LLM dependency (the LearningPipeline
orchestrates the LLM calls). Core idea: the scope of a unit follows from
the task — sum of the treatment classes ⇒ learning time ⇒ format.
"""
from __future__ import annotations

from src.i18n import N_, Msg, render, tr
from dataclasses import MISSING, dataclass, field, fields

LEARNING_TIME_MIN = {"V": 25, "K": 8, "D": 4, "R": 0}
CLASSES = ("V", "K", "D", "R")

FORMAT_IMPULSE = "impulse"          # up to ~45 min, mostly D/K
FORMAT_LEARNING_UNIT = "learning_unit"  # 1–2 h
FORMAT_BOOK = "book"

# Display labels for protocol values; the values themselves are never shown.
KIND_LABEL = {"paradigm_shift": N_("paradigm shift"), "extension": N_("extension"),
              "version_delta": N_("version delta"), "knowledge": N_("knowledge")}
INTERFERENCE_LABEL = {"high": N_("high"), "medium": N_("medium"), "low": N_("low"),
                      "unknown": N_("unknown")}
FORMAT_LABEL = {FORMAT_IMPULSE: N_("impulse"), FORMAT_LEARNING_UNIT: N_("learning unit"),
                FORMAT_BOOK: N_("book")}              # 3 h+, several V chapters


@dataclass
class Concept:
    id: str
    name: str
    concept_class: str
    rationale: str = ""

    def as_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "concept_class": self.concept_class}


@dataclass
class Chapter:
    title: str
    concepts: list[str]
    learning_objectives: list[str] = field(default_factory=list)
    prerequisites: list[str] = field(default_factory=list)


@dataclass
class GapAnalyse:
    kind: str                      # paradigm_shift | extension | version_delta
    interference: str              # hoch | mittel | gering
    interference_rationale: str
    concepts: list[Concept]
    chapters: list[Chapter]
    title: str
    description: str

    @property
    def learning_time_min(self) -> int:
        return sum(LEARNING_TIME_MIN.get(k.concept_class, 0) for k in self.concepts)

    @property
    def format(self) -> str:
        m = self.learning_time_min
        if m <= 45:
            return FORMAT_IMPULSE
        if m <= 150:
            return FORMAT_LEARNING_UNIT
        return FORMAT_BOOK

    @property
    def depth_profile(self) -> str:
        return "compact" if self.format == FORMAT_IMPULSE else "detailed"

    def summary(self, lang: str | None = None) -> str:
        n = {k: sum(1 for x in self.concepts if x.concept_class == k) for k in CLASSES}
        return tr("Kind: {kind} · interference: {interference} · {concepts} concepts "
                  "({v}×V, {k}×K, {d}×D, {r}×R) → ~{minutes} min learning time → "
                  "format: {format} ({chapters} chapters)", lang,
                  kind=tr(KIND_LABEL.get(self.kind, self.kind), lang),
                  interference=tr(INTERFERENCE_LABEL.get(self.interference, self.interference), lang),
                  concepts=len(self.concepts), v=n["V"], k=n["K"], d=n["D"], r=n["R"],
                  minutes=self.learning_time_min,
                  format=tr(FORMAT_LABEL.get(self.format, self.format), lang),
                  chapters=len(self.chapters))


def gap_as_dict(g: GapAnalyse) -> dict:
    return {"kind": g.kind, "interference": g.interference,
            "interference_rationale": g.interference_rationale,
            "concepts": [k.__dict__ for k in g.concepts],
            "chapters": [k.__dict__ for k in g.chapters],
            "title": g.title, "description": g.description}


def _known_only(concept_class, d: dict) -> dict:
    """Filters fields the data class does not know (yet).

    Saved jobs can come from an older or newer version. An unknown or
    missing field must not prevent loading — otherwise old results become
    unreachable for good.
    """
    fields_ = {f.name for f in fields(concept_class)}
    required = {f.name for f in fields(concept_class)
               if f.default is MISSING and f.default_factory is MISSING}  # type: ignore[misc]
    filtered = {k: v for k, v in (d or {}).items() if k in fields_}
    for name in required - set(filtered):
        filtered[name] = ""            # placeholder instead of a crash
    return filtered


def gap_from_dict(d: dict) -> GapAnalyse:
    """Restores a saved gap analysis — tolerant of errors."""
    d = d or {}
    return GapAnalyse(
        kind=d.get("kind", "knowledge"),
        interference=d.get("interference", "unknown"),
        interference_rationale=d.get("interference_rationale", ""),
        concepts=[Concept(**_known_only(Concept, k)) for k in d.get("concepts", [])],
        chapters=[Chapter(**_known_only(Chapter, k)) for k in d.get("chapters", [])],
        title=d.get("title", "Learning unit"),
        description=d.get("description", ""))


class GapParseError(ValueError):
    pass


# Protocol synonyms: models translate schema values into the unit's
# language, although the schema prescribes them literally (the language rule
# appended to every prompt asks for JSON string values in that language).
# UNAMBIGUOUS translations are normalised before validation; anything that
# cannot be mapped stays a hard error — the gate becomes more tolerant of
# vocabulary, never of content.
_KIND_SYNONYMS = {
    "paradigm_shift": "paradigm_shift", "paradigmshift": "paradigm_shift",
    "paradigm_change": "paradigm_shift", "paradigmenwechsel": "paradigm_shift",
    "extension": "extension", "expansion": "extension", "erweiterung": "extension",
    "version_delta": "version_delta", "versiondelta": "version_delta",
    "versionsdelta": "version_delta",
}
_INTERFERENCE_SYNONYMS = {
    "high": "high", "hoch": "high",
    "medium": "medium", "moderate": "medium", "mittel": "medium",
    "low": "low", "gering": "low", "niedrig": "low",
}


def _protocol_value(value, synonyms: dict) -> str:
    """Maps a schema value onto the protocol vocabulary (or leaves it
    unchanged, so that the error message shows the original value)."""
    n = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return synonyms.get(n, value)


def parse_gap(data_: dict) -> GapAnalyse:
    """Validates and parses the LLM answer of the gap analysis."""
    errors: list[str] = []
    kind = _protocol_value(data_.get("kind"), _KIND_SYNONYMS)
    if kind not in ("paradigm_shift", "extension", "version_delta"):
        errors.append(f"art '{kind}' unbekannt")
    interference = _protocol_value(data_.get("interference"), _INTERFERENCE_SYNONYMS)
    if interference not in ("high", "medium", "low"):
        errors.append(f"interferenz '{interference}' unbekannt")

    concepts: list[Concept] = []
    ids: set[str] = set()
    for i, k in enumerate(data_.get("concepts") or []):
        cid, name, concept_class = k.get("id"), k.get("name"), k.get("concept_class")
        # The same normalisation as in the edit path (apply_edits): "v" is V.
        concept_class = (str(concept_class).strip().upper() if concept_class is not None else concept_class)
        if not cid or not name:
            errors.append(f"concepts[{i}]: id/name missing")
            continue
        if concept_class not in CLASSES:
            errors.append(f"concepts[{i}]({cid}): klasse '{concept_class}' unbekannt")
            continue
        if cid in ids:
            errors.append(f"concepts[{i}]: id '{cid}' doppelt")
            continue
        ids.add(cid)
        concepts.append(Concept(cid, name, concept_class, k.get("rationale", "")))
    if not concepts:
        errors.append("no concept inventory")

    chapters: list[Chapter] = []
    covered: set[str] = set()
    for i, chap in enumerate(data_.get("chapters") or []):
        refs = [r for r in (chap.get("concepts") or [])]
        for r in refs:
            if r not in ids:
                errors.append(f"chapters[{i}]: unknown concept '{r}'")
        covered.update(refs)
        chapters.append(Chapter(chap.get("title", f"Chapter {i+1}"), refs,
                               chap.get("learning_objectives") or [], chap.get("prerequisites") or []))
    missing = [k.id for k in concepts if k.concept_class != "R" and k.id not in covered]
    if missing:
        errors.append(f"concepts without a chapter: {', '.join(missing)} (only R may be without a chapter)")
    if not chapters:
        errors.append("no chapters")

    if errors:
        raise GapParseError("; ".join(errors))
    return GapAnalyse(kind=kind, interference=interference,
                      interference_rationale=data_.get("interference_rationale", ""),
                      concepts=concepts, chapters=chapters,
                      title=data_.get("unit_title", "Learning unit"),
                      description=data_.get("description", ""))


def apply_edits(gap: GapAnalyse, edits: list[dict]) -> list[Msg]:
    """Applies user edits from the checkpoint: [{"id": "k3", "concept_class": "K"|"DELETE"}].

    Returns hints (e.g. chapters that became empty as a result).
    """
    hints: list[Msg] = []
    by_id = {k.id: k for k in gap.concepts}
    struck: set[str] = set()
    for e in edits:
        cid = e.get("id")
        new_ = (e.get("concept_class") or "").strip().upper()
        k = by_id.get(cid)
        if k is None:
            hints.append(Msg("Edit ignored: concept '{cid}' unknown", {"cid": cid}))
            continue
        if new_ in ("DELETE", "STREICHEN"):
            struck.add(cid)
        elif new_ in CLASSES and new_ != k.concept_class:
            hints.append(Msg("{cid} ({name}): {old} → {new}",
                             {"cid": cid, "name": k.name, "old": k.concept_class, "new": new_}))
            k.concept_class = new_
        elif new_ and new_ not in CLASSES:
            hints.append(Msg("Edit ignored: class '{cls}' unknown (V|K|D|R|DELETE)", {"cls": new_}))
    if struck:
        gap.concepts = [k for k in gap.concepts if k.id not in struck]
        for chap in gap.chapters:
            chap.concepts = [r for r in chap.concepts if r not in struck]
        empty_ones = [chap.title for chap in gap.chapters if not chap.concepts]
        gap.chapters = [chap for chap in gap.chapters if chap.concepts]
        hints.append(Msg("Removed: {ids}", {"ids": ", ".join(sorted(struck))}))
        for t in empty_ones:
            hints.append(Msg("Chapter '{title}' became empty and is dropped", {"title": t}))
    return hints


def prioritisation_proposal(gap: GapAnalyse, budget_min: int) -> tuple[list[dict], str]:
    """Proposes downgrades to reach a time budget — NEVER cuts silently.

    Greedy from the back (later concepts count as less fundamental): V→K,
    then K→D. Returns (edits, explanatory text); the edits are only a
    proposal, the user decides at the checkpoint.
    """
    if gap.learning_time_min <= budget_min:
        return [], ""
    edits: list[dict] = []
    minutes = gap.learning_time_min
    for k in reversed(gap.concepts):
        if minutes <= budget_min:
            break
        if k.concept_class == "V":
            edits.append({"id": k.id, "concept_class": "K", "name": k.name, "from": "V"})
            minutes -= LEARNING_TIME_MIN["V"] - LEARNING_TIME_MIN["K"]
    for k in reversed(gap.concepts):
        if minutes <= budget_min:
            break
        if k.concept_class == "K" and not any(e["id"] == k.id for e in edits):
            edits.append({"id": k.id, "concept_class": "D", "name": k.name, "from": "K"})
            minutes -= LEARNING_TIME_MIN["K"] - LEARNING_TIME_MIN["D"]
    rows = [f"- {e['id']} ({e['name']}): {e['from']} → {e['concept_class']}" for e in edits]
    text = Msg("Derived scope ~{derived} min exceeds the budget of {budget} min. Proposal "
               "(gives ~{minutes} min):\n{rows}{note}",
               {"derived": gap.learning_time_min, "budget": budget_min, "minutes": minutes,
                "rows": "\n".join(rows),
                "note": Msg("\nNote: the budget cannot be reached even with all downgrades — "
                            "remove concepts as well or relax the budget.") if minutes > budget_min else ""})
    return edits, text


def outline_plan_markdown(gap: GapAnalyse, budget_min: int | None,
                          proposal_text, lang: str | None = None) -> str:
    """01-outline-plan.md — the checkpoint artefact with the documented derivation."""
    z = [tr("# Outline plan — {title} (CHECKPOINT)", lang, title=gap.title), "",
         tr("**Gap analysis:** {summary}", lang, summary=gap.summary(lang)),
         tr("**Interference:** {level} — {rationale}", lang,
            level=tr(INTERFERENCE_LABEL.get(gap.interference, gap.interference), lang),
            rationale=gap.interference_rationale), "",
         tr("## Concept inventory", lang), "",
         tr("| ID | Concept | Class | Rationale |", lang), "|---|---|---|---|"]
    for k in gap.concepts:
        z.append(f"| {k.id} | {k.name} | {k.concept_class} | {k.rationale} |")
    z += ["", tr("## Chapter plan", lang), ""]
    for i, chap in enumerate(gap.chapters, 1):
        z.append(tr("**C{i} · {title}** — concepts: {concepts}", lang, i=i, title=chap.title,
                    concepts=", ".join(chap.concepts)))
        for lo in chap.learning_objectives:
            z.append(tr("  Objective: {objective}", lang, objective=lo))
        z.append("")
    if budget_min:
        z.append(tr("**Time budget (constraint):** {minutes} min", lang, minutes=budget_min))
        if proposal_text:
            z += ["", tr("## Prioritisation proposal", lang), "", str(render(proposal_text, lang))]
    z += ["", "---", tr("**CHECKPOINT:** scope and chapter plan must be approved before "
                        "production starts.", lang)]
    return "\n".join(z)
