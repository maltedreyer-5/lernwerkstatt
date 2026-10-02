# -*- coding: utf-8 -*-
"""LearningPipeline — the one orchestration of the LernWerkstatt.

Phases: learner profile → gap analysis (checkpoint) → detail plans (all
chapters IN PARALLEL) → two DAG runs per chapter (script, transformation) →
consolidation (final test; critic pass IN PARALLEL over all lessons) →
final gate (validator) → assembly.

Dual-LLM routing (fast + strong; many calls are no problem):
  strong (llm)       gap analysis, detail plans, scripts of the V concepts,
                     chapter assembly, application part, final test,
                     critic + revision
  fast (llm_fast)    learner profile, cross context, scripts K/D,
                     transformation, chapter meta, quality checks of the DAG
                     executor

Traceability as a design principle: DAG tasks are created FROM the concept
inventory; the validator remains the second net and final gate. The state is
in the job folder at all times (state.json, content/unit.json,
state=draft) — resumption with the pickup code.
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import logging
import re
import shutil
from pathlib import Path

from src.core.stop_signal import StopSignal
from src.i18n import Msg, N_, default_language, tr
from src import __version__
from src.unit import i18n
from src.llm.json_parser import parse_llm_json
from src.pipeline.dag import DAGExecutor, DAGPlan, DAGTask
from src.pipeline import gap_analysis as ga
from src.prompts import learning
from src.unit.assembler import assemble
from src.unit import degradation as degr
from src.unit.normalization import (normalise_block, normalise_script,
                                     normalise_unit, sup_sub_to_unicode as
                                     _sup_sub_to_unicode)
from src import config
from src.pipeline import teaching_script as lsk
from src.pipeline import material_coverage as mab
from src.pipeline import technical_report as tb
from src.unit.terminology import Terminology
from src.unit.validator import INTERACTIVE, ILLUSTRATION, validate

log = logging.getLogger("lernwerkstatt.pipeline")

# Upper limit for script text in prompts — an EMERGENCY BRAKE, not a
# control variable.
#
# The script text is written didactically: lead-in, development, example,
# transition. Shortening it means removing precisely the conclusions and
# transitions — that is where a section states what it has achieved. So it is
# NOT shortened as long as at all possible.
#
# Measured: the largest chapter script of a real job has 34,022 characters and
# gives a prompt of 12,322 tokens — nine per cent of a 128k window. There is no
# technical reason to shorten.
#
# If the limit does apply (very large chapters), the prose is NOT cut; instead
# a STRUCTURAL SUBSTITUTE, marked explicitly as such, is built: outline,
# learning objectives and content points from the detail plan. That is more
# honest than truncated sentences — the recipient sees that it gets an
# overview and not a text.
# Version of the unit.json format written by this code (see unit.schema.json).
UNIT_FORMAT_VERSION = 1

MAX_SCRIPT_CONTEXT = int(os.getenv("MAX_SCRIPT_CONTEXT", "60000"))


def _slug(t: str) -> str:
    t = (t or "learning-unit").lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        t = t.replace(a, b)
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", t)).strip("-") or "learning-unit"


def _md_to_docx(md: str, target: Path) -> None:
    """Minimal Markdown→Word converter (route 2 of the handout export):
    headings, paragraphs, bold/italics — deliberately plain, but robust."""
    import docx  # python-docx; Import bewusst lazy

    doc = docx.Document()
    for block in md.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        m = re.match(r"^(#{1,4})\s+(.*)", block)
        if m:
            doc.add_heading(re.sub(r"\*+", "", m.group(2)).strip(), level=len(m.group(1)))
            continue
        paragraph = doc.add_paragraph()
        for part in re.split(r"(\*\*.*?\*\*|\*.*?\*)", block.replace("\n", " ")):
            if part.startswith("**") and part.endswith("**"):
                paragraph.add_run(part[2:-2]).bold = True
            elif part.startswith("*") and part.endswith("*") and len(part) > 2:
                paragraph.add_run(part[1:-1]).italic = True
            elif part:
                paragraph.add_run(part)
    doc.save(str(target))


# Deviations observed with real models: substitute field names in task
# blocks. Deterministic normalisation BEFORE validation/repair (a zero-cost
# net). The English source names cover units in other languages: the
# language rule asks for JSON string values in that language there, and
# models occasionally carry that over to field names despite the protocol
# exception — the same mechanism as with the gap analysis values.
_FIELD_ALIAS = {
    "prediction": {"question": ("text", "task", "prompt", "description",
                                "frage", "aufgabe", "aufgabenstellung", "beschreibung"),
                   "resolution": ("solution", "sample_solution", "explanation", "answer",
                                  "aufloesung", "loesung", "musterloesung", "erklaerung")},
    "error_analysis": {"material": ("code", "snippet", "content", "sample", "example",
                                    "beispiel", "inhalt"),
                       "question": ("task", "prompt", "text",
                                    "frage", "aufgabe", "aufgabenstellung"),
                       "sample_solution": ("solution", "resolution", "explanation", "answer",
                                           "musterloesung", "loesung", "aufloesung", "erklaerung")},
    "task": {"task": ("prompt", "text", "question", "description", "content", "exercise",
                      "aufgabe", "aufgabenstellung", "frage", "beschreibung", "inhalt"),
             "sample_solution": ("solution", "resolution", "answer",
                                 "musterloesung", "loesung", "aufloesung")},
}

# Depending on the model, the alternative text is called `beschriftung`,
# `alt` or `caption`. With `table`, however, `caption` is a field of its own
# and legitimate — so the alias only applies to the displaying types that
# need an alternative text.
for _type in ("diagram", "chart", "formula", "simulator", "widget"):
    _FIELD_ALIAS.setdefault(_type, {})["description"] = (
        "caption", "alt", "alt_text", "beschreibung", "beschriftung", "bildunterschrift")


# Map invented block types onto the real ones. Otherwise they end up in the
# degradation and become text — the content is rescued, but the form of
# display is lost. The English names correspond to the media plan
# nomenclature (learning.TYPE_TRANSLATION) — both levels must understand the
# same words, otherwise the detail plan plans 'prediction' and the
# transformation delivers a block type the validator rejects.
_TYPE_ALIAS = {
    "grafik": None,        # decided by the content: chart or diagram
    "abbildung": None,
    "bild": None,
    "schaubild": None,
    "interaktiv": None,
    "image": None,
    "figure": None,
    "graphic": None,
    # German names: the canonical names before the format became English,
    # and the variants models produce when the unit's language is German.
    "hinweis": "note",
    "tabelle": "table",
    "akkordeon": "accordion",
    "lueckentext": "cloze",
    "luecke": "cloze",
    "lueckentexte": "cloze",
    "zuordnung": "matching",
    "karteikarten": "flashcards",
    "diagramm": "diagram",
    "vorhersage": "prediction",
    "aufgabe": "task",
    "uebung": "task",
    "fehleranalyse": "error_analysis",
    "formel": "formula",
    # The canonical names themselves, so that "Note" or "TABLE" end up in
    # the canonical spelling as well.
    **{t: t for t in ("text", "note", "table", "accordion", "code", "quiz", "cloze", "matching",
                      "flashcards", "chart", "diagram", "simulator", "prediction", "task",
                      "error_analysis", "widget", "formula")},
    # English variants
    "fill_in_the_blank": "cloze",
    "flashcard": "flashcards",
    "exercise": "task",
    "error-analysis": "error_analysis",
    "simulation": "simulator",
    "callout": "note",
    "hint": "note",
}


def _resolve_type_alias(blk: dict) -> dict:
    """Maps invented type names onto the real ones."""
    type_ = blk.get("type")
    key = type_.strip().lower() if isinstance(type_, str) else type_
    if key not in _TYPE_ALIAS:
        # Models occasionally set the MERMAID type as the BLOCK type
        # ("mindmap",
        # "timeline", …). If the block carries code, it is a diagram block — an
        # intact mind map would otherwise end up as 'unknown block type' in the
        # degradation, although catalogue AND grammar know the type.
        from src.unit import diagram_types as _dt
        if (isinstance(key, str) and isinstance(blk.get("code"), str)
                and key in {k.lower() for k in _dt.TYPES}):
            log.info("Block type '%s' read as diagram/mermaid", type_)
            blk["type"] = "diagram"
            blk.setdefault("engine", "mermaid")
        return blk
    target = _TYPE_ALIAS[key]
    if target is None:
        # Decide by the content instead of guessing: Mermaid source -> diagram,
        # specification -> chart. Otherwise leave it to the degradation.
        if isinstance(blk.get("code"), str):
            target = "diagram"
        elif isinstance(blk.get("spec"), dict):
            target = "chart"
        else:
            return blk
    log.info("Block type '%s' read as '%s'", type_, target)
    blk["type"] = target
    return blk



def _prepare_blocks(lesson: dict) -> None:
    """Alias resolution and normalisation for all blocks of a lesson.

    A function of its own because it is needed in TWO places: after the
    first generation and after a repair.
    """
    for blk in (lesson or {}).get("blocks") or []:
        if isinstance(blk, dict):
            _resolve_field_aliases(blk)
            # Close format drift BEFORE checking: otherwise every Markdown
            # remnant burns
            # a repair run.
            normalise_block(blk)


_HEADING = re.compile(
    r"^(?:#{1,4}\s+\S.*"                    # Markdown
    r"|\d+(?:\.\d+)*[.)]?\s+\S.{0,90}"     # 3.2 section title
    r"|[A-ZÄÖÜ][^.!?\n]{3,90})$")            # short line without punctuation


def representative_excerpt(text: str, limit: int = 4000) -> str:
    """An excerpt that shows the CUT of a document — not its beginning.

    The gap analysis does not need to know the content, but WHAT the
    document covers, at which level and with which terminology. 4,000
    characters are enough for that — but not the FIRST 4,000: in a textbook
    those would be preface and table of contents, in a standard the scope.
    Both say little about the subject matter.

    So the excerpt takes: the beginning (usually purpose and scope), ALL
    headings (they show the structure of the whole document) and the end
    (summary, conclusion).
    """
    text = (text or "").strip()
    if len(text) <= limit:
        return text

    header_budget = int(limit * 0.35)
    foot_budget = int(limit * 0.15)
    header = text[:header_budget]
    foot = text[-foot_budget:]

    # Headings from the MIDDLE part — the beginning is already included.
    middle = text[header_budget:-foot_budget]
    title = []
    for line in middle.split("\n"):
        z = line.strip()
        if 4 <= len(z) <= 95 and _HEADING.match(z):
            title.append(z)
    rest = limit - len(header) - len(foot) - 80
    outline = ""
    for t in title:
        if len(outline) + len(t) + 1 > rest:
            outline += "\n…"
            break
        outline += t + "\n"

    parts = [header.rstrip()]
    if outline.strip():
        parts.append("\n[Outline of the document:]\n" + outline.rstrip())
    parts.append("\n[End of the document:]\n" + foot.lstrip())
    return "\n".join(parts)[:limit]


def script_structural_substitute(html: str, detail_plan: dict | None = None,
                          summary: str = "") -> str:
    """An overview instead of truncated prose — only for emergencies.

    If a script becomes so large that it does not fit into the prompt, the
    worst solution is to cut the text at a character position: that hits the
    conclusions and transitions of the sections systematically, that is,
    exactly what carries didactically.

    Instead an overview is built from data that is ALREADY STRUCTURED —
    outline of the script, learning objectives and content points from the
    detail plan. The recipient sees explicitly that it gets an overview and
    not running text, and can adjust to it.
    """
    title = [re.sub(r"<[^>]+>", "", t).strip()
             for t in re.findall(r"<h3[^>]*>(.*?)</h3>", html or "", re.S | re.I)]
    rows = ["[NOTE: the chapter script is too long for this prompt.",
              "Instead of truncated prose an OVERVIEW follows. Wordings",
              "and examples from the script are NOT available here —",
              "refer to the topics named, not to the wording.]", ""]
    # The chapter summary has already been WRITTEN as a summary — not a cut
    # text, but the best substitute available.
    if (summary or "").strip():
        rows += ["SUMMARY OF THE CHAPTER:", summary.strip(), ""]
    if title:
        rows.append("OUTLINE OF THE CHAPTER:")
        rows += [f"  - {t}" for t in title]
        rows.append("")
    for lp in ((detail_plan or {}).get("lessons") or []):
        if not isinstance(lp, dict):
            continue
        rows.append(f"LESSON {lp.get('id')}: {lp.get('title', '')}")
        for z in (lp.get("learning_objectives") or [])[:4]:
            rows.append(f"    Ziel: {z}")
        for i in (lp.get("content_points") or [])[:6]:
            rows.append(f"    Inhalt: {i}")
        rows.append("")
    return "\n".join(rows)


def evidence_locations(full_text: str, terms, budget: int = 6000,
                 window: int = 320) -> str:
    """Places in the material where the checked terms OCCUR.

    For a verdict "is this an established technical term or a coinage?" the
    first 6,000 characters of a document are the wrong ones: they contain
    the scope, not the terminology. What is needed is the context of the
    terms themselves.

    If a term does not occur, that is exactly the information — then it is
    not in the material, and the verdict follows accordingly.
    """
    full_text = full_text or ""
    if not full_text.strip():
        return ""
    searched = [str(b).strip() for b in (terms or []) if str(b).strip()]
    if not searched:
        return full_text[:budget]

    locations: list[str] = []
    consumed = 0
    for term in searched:
        pos = full_text.lower().find(term.lower())
        if pos < 0:
            continue
        a = max(0, pos - window // 2)
        e = min(len(full_text), pos + len(term) + window // 2)
        excerpt = full_text[a:e].replace("\n", " ").strip()
        entry = f"[{term}] …{excerpt}…"
        if consumed + len(entry) > budget:
            break
        locations.append(entry)
        consumed += len(entry) + 1
    if not locations:
        # Not a single term in the material — then the beginning is as good as
        # any other place, and the answer is "not evidenced" anyway.
        return full_text[:budget]
    return "\n".join(locations)


def _into_pieces(text: str, limit: int) -> list[str]:
    """Splits text at sentence boundaries into sections below `limit` characters.

    Cutting off would be the simpler solution and the worse one: the end of
    a lesson typically contains application and numbers — exactly what a
    fact check must see.
    """
    text = text or ""
    if len(text) <= limit:
        return [text] if text.strip() else []
    pieces, current = [], ""
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if len(current) + len(sentence) + 1 > limit and current:
            pieces.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current.strip():
        pieces.append(current)
    return pieces


# The glossary section marker is protocol vocabulary of the chapter script.
# Units in other languages occasionally write "=== GLOSSARY ===" despite the
# instruction or vary the case — then _harvest_glossary would SILENTLY harvest
# nothing (no error, simply no glossary) and the handout would keep the
# glossary block in the running text.
_GLOSSARY_MARKER = re.compile(r"^[ \t]*=+[ \t]*GLOSSAR\w*[ \t]*=+[ \t]*$",
                             re.IGNORECASE | re.MULTILINE)


def _normalise_glossary_marker(script: str) -> str:
    """Unifies the glossary marker (also '=== GLOSSARY ===', '===glossar===')."""
    return _GLOSSARY_MARKER.sub("=== GLOSSAR ===", script or "", count=1)


def _resolve_field_aliases(b: dict) -> dict:
    # Normalise the TYPE first — the field aliases depend on it.
    _resolve_type_alias(b)
    for target, sources in _FIELD_ALIAS.get(b.get("type"), {}).items():
        if not b.get(target):
            for q in sources:
                if b.get(q):
                    b[target] = b.pop(q)
                    break
    if isinstance(b.get("concepts"), str):
        b["concepts"] = [b["concepts"]]
    return b


def _html_to_md(html: str) -> str:
    """HTML→Markdown for the script handout.

    HTML is the lead format; this direction is the conversion back for the
    Word route. Formulas are the delicate part: MathML cannot easily be set
    in docx, so the sub/sup notation is lifted to Unicode and MathML is
    resolved through its plain-text annotation or its characters — a
    readable `Q · Kᵀ` is better than an empty paragraph.
    """
    t = html or ""
    # MathML first: prefer the LaTeX annotation, otherwise the plain
    # characters.
    def _mathml(m):
        raw = m.group(0)
        anno = re.search(r"<annotation[^>]*>(.*?)</annotation>", raw, re.S | re.I)
        if anno:
            return "$" + re.sub(r"<[^>]+>", "", anno.group(1)).strip() + "$"
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", raw)).strip()
    t = re.sub(r"<math\b.*?</math>", _mathml, t, flags=re.S | re.I)
    t = _sup_sub_to_unicode(t, strip_tags=False)
    t = re.sub(r"<h3[^>]*>(.*?)</h3>", r"\n### \1\n", t, flags=re.S | re.I)
    t = re.sub(r"<h4[^>]*>(.*?)</h4>", r"\n#### \1\n", t, flags=re.S | re.I)
    t = re.sub(r"</p>\s*", "\n\n", t, flags=re.I)
    t = re.sub(r"<li[^>]*>", "- ", t, flags=re.I)
    t = re.sub(r"<(strong|b)>(.*?)</\1>", r"**\2**", t, flags=re.S | re.I)
    t = re.sub(r"<(em|i)>(.*?)</\1>", r"*\2*", t, flags=re.S | re.I)
    t = re.sub(r"<code>(.*?)</code>", r"`\1`", t, flags=re.S | re.I)
    t = re.sub(r"<[^>]+>", "", t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def _first_sentence(text: str, limit: int = 300) -> str:
    """First sentence of a definition — a usable short form for the hover."""
    t = re.sub(r"<[^>]+>", " ", text or "").strip()
    m = re.search(r"^(.{20,%d}?[.!?])(\s|$)" % limit, t)
    return (m.group(1) if m else t[:limit]).strip()


def _chart_numbers(blk: dict) -> dict:
    """Extracts the plain data values from a chart spec for the fact check.

    Without axis configuration and formatting — the numbers are to be
    checked, not the display.
    """
    spec = blk.get("spec") or {}
    if blk.get("engine") == "vegalite":
        data_ = spec.get("data") or {}
        return {"values": (data_.get("values") or [])[:40]}
    d = spec.get("data") or {}
    return {"labels": d.get("labels"),
            "datasets": [{"label": ds.get("label"), "data": ds.get("data")}
                         for ds in (d.get("datasets") or []) if isinstance(ds, dict)]}



# Titles of the DAG tasks the pipeline builds. They stay English in the plan
# (the quality check quotes them to the model); for the production log they
# are turned into messages, so that the log follows the interface language.
_TASK_TITLES = {N_("Terminology & cross-references"), N_("Assemble the chapter script"),
                N_("Chapter summary"), N_("Application part of the chapter")}
_TASK_PATTERNS = ((re.compile(r"^Script (?P<id>\S+) \((?P<name>.*)\)$"), N_("Script {id} ({name})")),
                  (re.compile(r"^Blocks: (?P<title>.*)$"), N_("Blocks: {title}")))


def _task_title(title: str):
    if title in _TASK_TITLES:
        return Msg(title)
    for pattern, template in _TASK_PATTERNS:
        m = pattern.match(title)
        if m:
            return Msg(template, m.groupdict())
    return title

class LearningPipeline:
    """Stateful pipeline for exactly one job."""

    def __init__(self, llm_primary=None, llm_fast=None,
                 work_dir: str | Path = "work",
                 max_parallel: int = 6, quality_checks: bool = True,
                 job_number: int | None = None, notify_status=None,
                 inventory_index=None):
        self.llm = llm_primary
        self.llm_fast = llm_fast or llm_primary
        # Absolute, so that folder paths stored in the register stay valid
        # regardless of the current directory of a later process.
        self.root = Path(work_dir).resolve()
        self.max_parallel = max_parallel
        self.quality_checks = quality_checks
        self.job_number = job_number
        self.notify_status = notify_status
        self.stop_signal = StopSignal()

        self.profile: dict = {}
        # Language of the files written into the job folder (plans, reports).
        # The interface language at the time the job was created; saved in
        # state.json so that a resumed job keeps writing in the same language.
        self.ui_language: str = default_language()
        self.material_context: str = "no material uploaded — subject scaffold from model knowledge"
        # Full text of the material. `material_context` is ONLY a status
        # sentence ("material present (a.pdf) — inventory built"); using it as
        # the source corpus would check against one sentence of prose. The full
        # text lies in the file, not in the state — it can be many MB large.
        self.material_full_text: str = ""
        self.time_budget: int | None = None
        self.gap: ga.GapAnalyse | None = None
        self.detail_plans: dict[int, dict] = {}
        self.chapter_meta: list[dict] = []
        self.scripts: dict[int, str] = {}
        self.script_parts: dict[int, dict] = {}   # single sections of run A (half-chapter resumption)
        self.inventory_index = inventory_index      # InventoryIndex or None
        # Terminology register: separates FIXED terms (inventory, sources,
        # checked) from CANDIDATES. Only what is fixed goes into the prompts as
        # binding — otherwise a coinage from chapter 2 becomes the standard for
        # all following chapters.
        self.terminology = Terminology()
        # Teaching script: common thread and concept graph. Steers all
        # following phases — every section learns from it what it may introduce
        # and what not.
        self.teaching_script: lsk.TeachingScript | None = None
        # Lessons that could not be created despite retries. They must block
        # the final gate instead of being missing silently.
        self.losses: list[Msg] = []
        # Coverage matrix: which concept is evidenced in the material, which
        # material does not occur in the plan.
        self.coverage: dict = {}
        # Blocks that were downgraded to a text substitute.
        self.degradations: list[str] = []
        # Enrichment counter — the only way to measure whether the later pass
        # actually contributes illustration.
        self.enriched: int = 0
        # Enrichment blocks proposed but discarded (breach of contract or
        # duplicate). In the report it shows if a model fails systematically on
        # one block type.
        self.enrichment_discarded: int = 0
        # Lesson blocks already created per chapter. Without this intermediate
        # store an interruption would repeat the whole block phase of a chapter
        # — the most expensive phase.
        self.lesson_cache: dict[int, dict[int, dict]] = {}
        self.unit: dict = {}
        self.folder: Path | None = None

    # ────────────────────── Persistence & resumption ──────────────────────

    def _persist_state(self) -> None:
        if not self.folder:
            return
        z = {"job": self.job_number, "ui_language": self.ui_language, "profile": self.profile,
             "time_budget": self.time_budget, "material_context": self.material_context,
             "gap": ga.gap_as_dict(self.gap) if self.gap else None,
             "detail_plans": {str(k): v for k, v in self.detail_plans.items()},
             "chapter_meta": self.chapter_meta,
             "scripts": {str(k): v for k, v in self.scripts.items()},
             "script_parts": {str(k): v for k, v in self.script_parts.items()},
             "lesson_cache": {str(k): {str(i): d for i, d in v.items()}
                            for k, v in self.lesson_cache.items()}}
        (self.folder / "state.json").write_text(
            json.dumps(z, ensure_ascii=False, indent=1), encoding="utf-8")

    @classmethod
    def load(cls, folder: str | Path, llm_primary=None, llm_fast=None, **kw) -> "LearningPipeline":
        folder = Path(folder)
        z = json.loads((folder / "state.json").read_text(encoding="utf-8"))
        p = cls(llm_primary, llm_fast, work_dir=folder.parent,
                job_number=z.get("job"), **kw)
        p.folder = folder
        p.ui_language = z.get("ui_language") or p.ui_language
        p.profile = z.get("profile") or {}
        p.time_budget = z.get("time_budget")
        p.material_context = z.get("material_context") or p.material_context
        p.gap = ga.gap_from_dict(z["gap"]) if z.get("gap") else None
        p.detail_plans = {int(k): v for k, v in (z.get("detail_plans") or {}).items()}
        p.chapter_meta = z.get("chapter_meta") or []
        p.scripts = {int(k): v for k, v in (z.get("scripts") or {}).items()}
        p.lesson_cache = {int(k): {int(i): d for i, d in v.items()}
                        for k, v in (z.get("lesson_cache") or {}).items()}
        p.script_parts = {int(k): v for k, v in (z.get("script_parts") or {}).items()}
        unit_path = folder / "content" / "unit.json"
        p.unit = json.loads(unit_path.read_text(encoding="utf-8")) if unit_path.exists() else {}
        return p

    @property
    def next_chapter(self) -> int:
        return len(self.unit.get("modules") or [])

    @property
    def fully_produced(self) -> bool:
        return bool(self.gap) and self.next_chapter >= len(self.gap.chapters)

    @property
    def language(self) -> str:
        return (self.profile.get("language") or self.unit.get("language") or "de").lower()

    def _notify(self, status: str) -> None:
        if self.notify_status:
            try:
                self.notify_status(status)
            except Exception:  # noqa: BLE001 — a status message must never break the run
                log.warning("Status message failed", exc_info=True)

    # ────────────────────── Phase 0: Lernprofil ──────────────────────

    async def collect_profile(self, prior_knowledge: str, learning_objective: str,
                            time_budget_min: int | None = None,
                            material_texts: dict[str, str] | None = None,
                            language: str = "de") -> dict:
        self.time_budget = time_budget_min
        # Set early: `self.language` reads it, and the language rule is
        # attached to EVERY following generation prompt.
        self.profile["language"] = (language or "de").lower()
        if material_texts:
            names = ", ".join(material_texts)
            self.material_context = ((f"material present ({names}) — "
                                      "excerpts flow into planning and content."))
            self.material_full_text = "\n\n".join(
                f"### {n}\n{t}" for n, t in material_texts.items())
            if self.folder:
                self._write_material()
            await self._build_inventory(material_texts)
        response = await self.llm_fast.complete(
            learning.learner_profile_prompt(prior_knowledge, learning_objective, time_budget_min, self.material_context),
            json_mode=True)
        chosen = self.profile["language"]
        parsed = parse_llm_json(response)
        self.profile = parsed if isinstance(parsed, dict) else {}
        # The language the user chose for the unit wins. The model reports the
        # language of the user's INPUT, which is a different thing: a German
        # description of an English course would otherwise produce a German
        # unit, whatever was selected.
        self.profile["language"] = chosen
        if material_texts:
            # Not the first 4,000 characters, but 4,000 REPRESENTATIVE ones:
            # beginning, outline of the whole document, end.
            self.profile["material_excerpts"] = {
                n: representative_excerpt(t)
                for n, t in list(material_texts.items())[:8]}
            shortened = [n for n, t in list(material_texts.items())[:8]
                        if len(t) > 4000]
            if shortened:
                log.info("material excerpts: %d of %d documents shortened (beginning + outline + end)",
                         len(shortened), len(material_texts))
            if len(material_texts) > 8:
                log.warning("%d documents uploaded, only the first 8 go "
                            "into planning", len(material_texts))
        self._notify("learner-profile")
        return self.profile

    async def _build_inventory(self, material_texts: dict[str, str]) -> None:
        """Builds the material inventory (segmentation + embedding index).
        Without an embedder configuration the context excerpt remains — the
        fact check is then skipped, and that is shown."""
        if self.inventory_index is None:
            self.material_context += ((" NOTE: no embedder configured (EMBEDDER_*)"
                                       " — the fact check against the material is skipped."))
            return
        try:
            from src.pipeline.inventory_builder import build_inventory
            for name, text in material_texts.items():
                await build_inventory(
                    material=text, document_name=name, llm=self.llm_fast,
                    index=self.inventory_index, task_type_name="learning unit",
                    kind_types=["chapter", "section", "definition", "example", "procedure"])
            self.material_context += ((f" inventory built"
                                       f" ({self.inventory_index.count} entries) —"
                                       " fact check active."))
        except Exception as e:  # noqa: BLE001 — grounding is an additional net, not a blocker
            log.warning("Inventory building failed: %s", e)
            self.inventory_index = None
            self.material_context += f" NOTE: building the inventory failed ({e})."

    def answer_briefing(self, answers: str) -> None:
        if answers.strip():
            self.profile["briefing_answers"] = answers.strip()
            self.profile.pop("open_questions", None)

    # ────────────────── Phase 1: Gap-Analyse + Grobplan ──────────────────

    async def analyse_gap(self) -> tuple[ga.GapAnalyse, str]:
        response = await self.llm.complete(
            learning.gap_prompt(self.profile, self.material_context)
            + "\n\n" + learning.language_rule(self.language), json_mode=True)
        self.gap = ga.parse_gap(parse_llm_json(response))

        proposal_text = ""
        if self.time_budget:
            _, proposal_text = ga.prioritisation_proposal(self.gap, self.time_budget)

        prefix = (f"job-{self.job_number:04d}-" if self.job_number
                   else "learning-unit-")
        self.folder = self.root / f"{prefix}{_slug(self.gap.title)}"
        (self.folder / "content").mkdir(parents=True, exist_ok=True)
        (self.folder / "dist").mkdir(exist_ok=True)
        (self.folder / "00-learner-profile.md").write_text(
            tr("# Learner profile", self.ui_language) + "\n\n```json\n"
            + json.dumps(self.profile, ensure_ascii=False, indent=1) + "\n```\n",
            encoding="utf-8")
        (self.folder / "01-outline-plan.md").write_text(
            ga.outline_plan_markdown(self.gap, self.time_budget, proposal_text, self.ui_language),
            encoding="utf-8")
        # Only now does the job folder exist — set up the terminology register.
        self._prepare_terminology()
        self._persist_state()
        self._notify("plan")
        return self.gap, proposal_text

    async def create_teaching_script(self):
        """Phase 1b: guiding document between gap analysis and detail plan."""
        if self.gap is None:
            return []
        names = {k.id: k.name for k in self.gap.concepts}
        try:
            data_ = parse_llm_json(await self.llm.complete(
                learning.teaching_script_prompt(
                    {"concepts": [k.as_dict() for k in self.gap.concepts],
                     "chapters": [{"title": kp.title, "concepts": kp.concepts,
                                  "learning_objectives": kp.learning_objectives} for kp in self.gap.chapters],
                     "kind": self.gap.kind, "title": self.gap.title}, self.profile)
                + "\n\n" + learning.language_rule(self.language), json_mode=True))
        except Exception as e:  # noqa: BLE001 — must never stop production
            log.warning("Teaching script failed: %s", e)
            self.teaching_script = lsk.TeachingScript()
            return [Msg("Teaching script not created ({error}) — production runs without a common thread",
                        {"error": e})]
        self.teaching_script, findings = lsk.parse_teaching_script(data_, set(names))
        if self.folder:
            (self.folder / "01b-teaching-script.md").write_text(
                lsk.teaching_script_markdown(self.teaching_script, names, findings, self.ui_language)
                + "\n\n" + tr("## Concept graph", self.ui_language) + "\n\n```mermaid\n"
                + lsk.mermaid_graph(self.teaching_script, names) + "\n```\n",
                encoding="utf-8")
        for b in findings:
            log.info("Teaching script: %s", b)
        await self._build_coverage()
        return findings

    async def _build_coverage(self) -> None:
        """Assigns every planned concept to evidence in the material.

        Only meaningful here: the concept inventory is fixed, and the evidence
        then goes into the script phase.
        """
        if self.inventory_index is None or self.gap is None:
            return
        try:
            self.coverage = await mab.matrix(
                [k.as_dict() for k in self.gap.concepts],
                self.inventory_index,
                getattr(self.terminology, "corpus", ""))
        except Exception as e:  # noqa: BLE001 — additional net, not a blocker
            log.warning("Material coverage failed: %s", e)
            return
        without = [a for a in self.coverage.get("coverage", []) if not a.evidenced]
        log.info("material coverage: %d of %d concepts evidenced, %d segments without a concept",
                 len(self.coverage.get("coverage", [])) - len(without),
                 len(self.coverage.get("coverage", [])),
                 len(self.coverage.get("orphaned", [])))
        if self.folder:
            try:
                (self.folder / "01c-material-coverage.md").write_text(
                    mab.as_markdown(self.coverage, self.ui_language), encoding="utf-8")
            except OSError:
                pass

    def _evidence_block(self, concept_id: str) -> str:
        """Evidence of a concept as context for the concept author."""
        for a in (self.coverage.get("coverage") or []):
            if a.concept_id == concept_id:
                return mab.evidence_block(a)
        return ""

    def _teaching_script_job_lesson(self, lp: dict) -> str:
        """Lesson brief for the block phase.

        The script phase gets a brief per concept, but the block phase builds
        the lessons — that is where it is decided whether a synthesis connects
        or repeats.
        """
        if self.teaching_script is None or self.gap is None:
            return ""
        names = {k.id: k.name for k in self.gap.concepts}
        return self.teaching_script.job_lesson(
            lp.get("id", ""), lp.get("concepts") or [], names)

    def _teaching_script_job(self, concept_id: str) -> str:
        if self.teaching_script is None or self.gap is None:
            return ""
        names = {k.id: k.name for k in self.gap.concepts}
        return self.teaching_script.job(concept_id, names)

        proposal_text = ""
        if self.time_budget:
            _, proposal_text = ga.prioritisation_proposal(self.gap, self.time_budget)

        prefix = (f"job-{self.job_number:04d}-" if self.job_number
                   else "learning-unit-")
        self.folder = self.root / f"{prefix}{_slug(self.gap.title)}"
        (self.folder / "content").mkdir(parents=True, exist_ok=True)
        (self.folder / "dist").mkdir(exist_ok=True)
        (self.folder / "00-learner-profile.md").write_text(
            tr("# Learner profile", self.ui_language) + "\n\n```json\n"
            + json.dumps(self.profile, ensure_ascii=False, indent=1) + "\n```\n",
            encoding="utf-8")
        (self.folder / "01-outline-plan.md").write_text(
            ga.outline_plan_markdown(self.gap, self.time_budget, proposal_text, self.ui_language),
            encoding="utf-8")
        self._persist_state()
        self._notify("plan")
        return self.gap, proposal_text


    def approve(self, inventory_edits: list[dict] | None = None) -> list[str]:
        assert self.gap is not None, "gap analysis missing"
        hints = ga.apply_edits(self.gap, inventory_edits or [])
        g = self.gap
        self.unit = {
            "format_version": UNIT_FORMAT_VERSION,
            "id": _slug(g.title),
            "title": g.title,
            "description": g.description,
            "language": self.profile.get("language", "de"),
            "duration_minutes": max(10, g.learning_time_min),
            "depth_profile": g.depth_profile,
            "state": "draft",
            "learning_objectives": [z for chap in g.chapters for z in chap.learning_objectives][:8],
            "prerequisites": self.profile.get("known_concepts", [])[:5],
            "provenance": {
                "models": ", ".join(sorted({getattr(x, "model", "?")
                                             for x in (self.llm, self.llm_fast) if x})),
                # Data of the unit, so in the unit's language.
                "sources": ([i18n.table_(self.language)["source_material"]]
                            if self.profile.get("material_excerpts")
                            else [i18n.table_(self.language)["source_model"]]),
                "note": f"{i18n.table_(self.language)['created_with']} LernWerkstatt {__version__}.",
            },
            "concepts": [k.as_dict() for k in g.concepts],
            "modules": [], "lessons": [], "glossary": [],
        }
        self._write_unit()
        self._persist_state()
        self._notify("approved")
        return hints

    # ────────────────── Phase 2: detail plans (all chapters IN PARALLEL)
    # ──────────────────

    async def plan_all_chapters(self) -> list[int]:
        """Creates missing detail plans in parallel (strong model). Returns the
        planned chapter indices."""
        assert self.gap is not None
        missing = [ci for ci in range(len(self.gap.chapters)) if ci not in self.detail_plans]
        if not missing:
            return []
        sem = asyncio.Semaphore(self.max_parallel)

        async def plan_one(ci: int):
            async with sem:
                fp = await self._detail_plan(ci, note=None)
                return ci, fp

        for ci, fp in await asyncio.gather(*(plan_one(ci) for ci in missing)):
            self.detail_plans[ci] = fp
        self._persist_state()
        return missing

    # Head word of a media plan entry ("diagram:flowchart (…)" -> "diagram",
    # "chart with params" -> "chart"). Nomenclature in other languages is
    # translated through the same table as in contract_for — otherwise a plan
    # in another language would count as without interactions by mistake.
    @staticmethod
    def _media_plan_type(entry) -> str:
        header = re.split(r"[:(]", str(entry or ""))[0].strip().lower()
        word = header.split()[0] if header.split() else ""
        if word in INTERACTIVE or word in ILLUSTRATION or word in (
                "text", "note", "accordion", "task", "error_analysis"):
            return word
        return learning.TYPE_TRANSLATION.get(word) or learning.TYPE_TRANSLATION.get(header) or ""

    @classmethod
    def _detail_plan_findings(cls, fp: dict, depth_profile: str | None = None,
                          v_ids: frozenset | set = frozenset()) -> list[str]:
        """Deterministic density check of a detail plan (didactics C1/C1b/C1c).

        Detail plans can plan only 2–3 interactions per lesson; the
        transformation follows the media plan, and the deficit would
        propagate into the finished unit. The gap analysis is validated
        strictly (`GapParseError`); this check does the same for the detail
        plan.

        Deliberately general: the minimum depends on the profile (C1 = one
        self-check per lesson; only 'detailed' asks for two), the duty to
        display applies, as in the planner prompt, only to lessons with a V
        concept and leaves the justification allowed there as a way out, the
        form rule applies only when there are enough interactions to vary, and
        with mostly unknown nomenclature there is no verdict at all.
        Conservative as a trigger for revision, never as a blocker: a failed
        second attempt does not stop production.
        """
        findings: list[str] = []
        lessons = [lp for lp in (fp.get("lessons") or []) if isinstance(lp, dict)]
        entries = [e for lp in lessons for e in (lp.get("media_plan") or [])]
        unknown = sum(1 for e in entries if not cls._media_plan_type(e))
        if entries and unknown / len(entries) > 0.3:
            log.info("detail plan density check skipped: %d/%d media plan entries cannot be mapped (unknown nomenclature?)",
                     unknown, len(entries))
            return []
        min_inter = 2 if (depth_profile or "") == "detailed" else 1
        all_int: list[str] = []
        for lp in lessons:
            types_ = [cls._media_plan_type(e) for e in (lp.get("media_plan") or [])]
            inter = [t for t in types_ if t in INTERACTIVE]
            visual = [t for t in types_ if t in ILLUSTRATION]
            all_int += inter
            if len(inter) < min_inter:
                findings.append(
                    f"lesson '{lp.get('id')}': only {len(inter)} interaction(s) in the "
                    f"media plan — the minimum for depth profile "
                    f"'{depth_profile or 'compact'}' is {min_inter}, spread over the "
                    f"lesson (C1b: about one per 400 words of reading text)")
            if not visual and v_ids and set(lp.get("concepts") or []) & set(v_ids):
                findings.append(
                    f"lesson '{lp.get('id')}' (V concept): no non-textual display "
                    f"in the media plan — at least one, or the plan states explicitly "
                    f"why none is suitable here")
        if len(lessons) >= 2 and len(all_int) >= 3 and len(set(all_int)) < 3:
            findings.append(
                f"only {len(set(all_int))} form(s) of interaction across the chapter "
                f"({', '.join(sorted(set(all_int))) or 'none'}) for "
                f"{len(all_int)} interactions — C1c asks for varying forms "
                f"(flashcards, matching, cloze, quiz, prediction) depending on the "
                f"learning purpose")
        return findings

    async def _detail_plan(self, ci: int, note: str | None) -> dict:
        chap = self.gap.chapters[ci]
        concepts = [k for k in self.gap.concepts
                    if k.id in chap.concepts and k.concept_class != "R"]  # R: glossary only
        # R concepts belong only in the glossary — the chapter is presented to
        # the planner already filtered, so that they produce no lessons.
        chap_dict = {**chap.__dict__, "concepts": [k.id for k in concepts]}
        prompt = learning.detail_plan_prompt(chap_dict, [k.__dict__ for k in concepts],
                                      self.profile, self.unit.get("depth_profile")
                                      or self.gap.depth_profile)
        if note:
            prompt += f"\n\nREWORK NOTE (must be taken into account): {note}"
        prompt += "\n\n" + learning.language_rule(self.language)
        # A single failed detail plan must not end the whole job. Otherwise a
        # run could break off right here, directly after approval, with "empty
        # answer" — an hour of work lost before it had begun.
        fp = None
        for attempt in range(3):
            try:
                fp = parse_llm_json(
                    await self.llm.complete(prompt, json_mode=True,
                                            thinking=False if attempt else None),
                    context=f"feinplan/k{ci+1}")
                break
            except Exception as e:  # noqa: BLE001
                log.warning("detail plan chapter %d, attempt %d failed: %s",
                            ci + 1, attempt + 1, e)
        # Density check with EXACTLY ONE revision: the planner gets the
        # concrete findings and delivers again; the version with fewer findings
        # is accepted. A remaining rest is logged but blocks nothing — the
        # enrichment and the validator catch it later.
        if fp is not None:
            _tp = self.unit.get("depth_profile") or getattr(
                self.gap, "depth_profile", None)
            _v = {k.id for k in concepts if getattr(k, "concept_class", "") == "V"}
            findings = self._detail_plan_findings(fp, depth_profile=_tp, v_ids=_v)
            if findings:
                log.info("Detail plan chapter %d: %d density finding(s) — one "
                         "revision: %s", ci + 1, len(findings),
                         "; ".join(findings[:3]))
                try:
                    fp2 = parse_llm_json(
                        await self.llm.complete(
                            prompt + ("\n\nREVISION (the previous plan had "
                             "these flaws — fix exactly them, keep "
                             "everything else):\n- ") + "\n- ".join(findings),
                            json_mode=True, thinking=False),
                        context=f"feinplan/k{ci+1}/dichte")
                    # THE SAME criteria as above — otherwise fp2 would win
                    # under a laxer assessment (without profile and V
                    # concepts), although it can be worse under the real
                    # criteria.
                    if len(self._detail_plan_findings(fp2, depth_profile=_tp,
                                                  v_ids=_v)) < len(findings):
                        fp = fp2
                    else:
                        log.warning("detail plan chapter %d: revision brought no improvement — original kept", ci + 1)
                except Exception as e:  # noqa: BLE001
                    log.warning("detail plan chapter %d: revision failed (%s) — original kept",
                                ci + 1, e)
        if fp is None:
            # Emergency plan from the concept inventory: one lesson per
            # concept. Rough, but production continues, and rework can plan the
            # chapter again in a targeted way.
            fp = {"lessons": [
                {"id": f"k{ci+1}l{n+1}", "title": k.name,
                 "concepts": [k.id], "learning_objectives": [],
                 "media_plan": ["text with h3 structure", "quiz"],
                 "check_criteria": []}
                for n, k in enumerate(concepts)]}
            log.error("detail plan chapter %d cannot be created — emergency plan with %d lessons", ci + 1, len(fp["lessons"]))
            self.losses.append(
                Msg("chapter {n}: detail plan could not be created, emergency plan used — "
                    "rework recommended", {"n": ci + 1}))
        (self.folder / f"02-detail-plan-c{ci+1}.json").write_text(
            json.dumps(fp, ensure_ascii=False, indent=1), encoding="utf-8")
        return fp

    # ────────────────── Phase 3/4: production chapter by chapter
    # ──────────────────

    def _chapter_context(self, ci: int):
        chap = self.gap.chapters[ci]
        concepts = [k for k in self.gap.concepts
                    if k.id in chap.concepts and k.concept_class != "R"]  # R: glossary only
        return chap, concepts

    async def _run_a(self, ci: int, note: str | None):
        """Run A: detail plan (if missing) + scripts + chapter assembly + early
        meta. Persists afterwards — an abort before run B resumes here
        (half-chapter resumption)."""
        chap, concepts = self._chapter_context(ci)
        yield {"kind": "phase", "text": Msg("Chapter {n}/{total}: {title}{rework}",
                                      {"n": ci + 1, "total": len(self.gap.chapters), "title": chap.title,
                                       "rework": Msg(" (rework)") if note else ""})}
        self._notify(f"chapter-{ci+1}a")

        if note or ci not in self.detail_plans:
            self.detail_plans[ci] = await self._detail_plan(ci, note)
        lessons_plan = self.detail_plans[ci].get("lessons") or []
        yield {"kind": "info", "text": Msg("Detail plan: {n} lessons", {"n": len(lessons_plan)})}

        if not note and ci in self.scripts and ci in self.script_parts:
            yield {"kind": "info", "text": Msg("Chapter {n}: run A taken over from the saved state "
                                             "(half-chapter resumption)", {"n": ci + 1})}
            return

        plan_a = self._plan_script(chap, concepts, lessons_plan, note)
        async for ev in self._executor().execute(plan_a):
            yield self._translate(ev)
        self.script_parts[ci] = {t.id: t.output for t in plan_a.tasks if t.phase == "process"}
        chapter_script = next((t.output for t in plan_a.tasks if t.phase == "finalize"), "")
        # Close format drift deterministically BEFORE the script moves on:
        # Markdown remnants become HTML, LaTeX the appropriate display. That
        # saves the repair loop the usual case.
        chapter_script, log_ = normalise_script(chapter_script)
        if log_:
            log.info("chapter %d normalised: %s", ci + 1, "; ".join(log_[:12]))
        # Terminology check on the script — this is where the terms arise.
        chapter_script = await self._check_terminology(chapter_script, f"chapter {ci+1}")
        self.scripts[ci] = chapter_script
        # File extension .html: the script IS HTML (the Word export converts it
        # back through _html_to_md, not the other way round).
        (self.folder / f"03-script-c{ci+1}.html").write_text(chapter_script, encoding="utf-8")
        self._harvest_glossary(chapter_script, lessons_plan)

        # Early meta from the script (fast model): makes the summary available
        # for the cross task of the following chapter BEFORE run B runs — the
        # basis of the chapter pipelining in produce_all().
        try:
            meta = parse_llm_json(await self.llm_fast.complete(
                learning.chapter_meta_prompt(chap.title)
                .replace("{dep:*process}", self._script_for_prompt(chapter_script, ci))
                + "\n\n" + learning.language_rule(self.language), json_mode=True))
        except Exception:  # noqa: BLE001
            meta = {"summary": "", "new_terms": []}
        if ci < len(self.chapter_meta):
            self.chapter_meta[ci] = meta
        else:
            self.chapter_meta.append(meta)
        self._persist_state()

    async def _run_b(self, ci: int, note: str | None):
        """Run B: transformation + application part + assembly + validation."""
        chap, concepts = self._chapter_context(ci)
        lessons_plan = self.detail_plans[ci].get("lessons") or []
        plan_b = self._plan_transform(ci, chap, concepts, lessons_plan, self.detail_plans[ci],
                                      self.script_parts.get(ci, {}), self.scripts[ci],
                                      note)
        async for ev in self._executor().execute(plan_b):
            yield self._translate(ev)
        lesson_data, exercises, repaired = await self._parse_and_repair(
            ci, plan_b, lessons_plan)
        if repaired:
            yield {"kind": "info",
                   "text": Msg("Repair loop: {n} item(s) format-corrected", {"n": repaired})}
        new_ids = self._assemble_chapter(ci, chap, plan_b, lessons_plan,
                                          lesson_data, exercises)
        # Enrichment as a SEPARATE pass after the blocks are built. In one call
        # prose and interaction compete for the same token budget, and the
        # block list starts with text — illustration falls off at the end
        # first. Here the output is small (only new blocks) and therefore
        # protected against cut-off.
        plan_by_id = {lp.get("id"): lp for lp in lessons_plan}
        supplemented = 0
        for les in self.unit["lessons"]:
            if les.get("id") not in (new_ids or []):
                continue
            try:
                supplemented += await self._enrich(
                    les, plan_by_id.get(les.get("id"), {}))
            except Exception as e:  # noqa: BLE001
                # An additional benefit must never cost a finished chapter: an
                # exception here would take run B down with it, and the chapter
                # would then be missing from the unit entirely.
                log.warning("enrichment %s skipped: %s", les.get("id"), e)
        if supplemented:
            self._notify(f"enrichment: {supplemented} blocks added")

        log_ = normalise_unit(self.unit)
        if log_:
            log.info("unit normalised (chapter %d): %s", ci + 1, "; ".join(log_[:12]))
        finding = validate(self.unit)
        self._write_unit()
        self._persist_state()
        self._notify(f"chapter-{ci+1}")
        yield {"kind": "restliste",
               "text": Msg("Validation after chapter {n}: {errors} errors, {warnings} warnings "
                           "(remaining list)", {"n": ci + 1, "errors": len(finding.errors),
                                                "warnings": len(finding.warnings_)}),
               "finding": finding}

    async def produce_chapter(self, ci: int, note: str | None = None):
        """Sequential production of ONE chapter (rework, tests, fallback)."""
        # Rework means: create the chapter ANEW. The lesson store would
        # otherwise return the old blocks and make the note ineffective. It
        # only applies to resuming an interrupted run.
        if note:
            self.lesson_cache.pop(ci, None)
        assert self.gap is not None and self.unit, "approval missing"
        async for ev in self._run_a(ci, note):
            yield ev
        async for ev in self._run_b(ci, note):
            yield ev

    async def produce_all(self, start: int | None = None):
        """Pipelined production of all chapters: run A of chapter k+1 runs in
        parallel with run B of chapter k (possible thanks to the early meta
        from run A). Run B stays strictly sequential — the order of assembly
        and with it the reading order are guaranteed."""
        assert self.gap is not None and self.unit, "approval missing"
        start = self.next_chapter if start is None else start
        n = len(self.gap.chapters)
        background: tuple | None = None   # (queue, task) of the running run B

        async def _in_queue(gen):
            q: asyncio.Queue = asyncio.Queue()

            async def run():
                try:
                    async for ev in gen:
                        await q.put(ev)
                except Exception as e:  # noqa: BLE001 — error as an event, then end
                    await q.put({"kind": "warning", "text": Msg("Run B aborted: {error}", {"error": e})})
                finally:
                    await q.put(None)
            return q, asyncio.create_task(run())

        try:
            for ci in range(start, n):
                async for ev in self._run_a(ci, None):
                    yield ev
                if background:                       # wait for run B of the previous chapter
                    q, task = background
                    while (ev := await q.get()) is not None:
                        yield ev
                    await task
                    background = None
                if self.stop_signal.is_stopped:
                    yield {"kind": "info", "text": Msg("⏹ Stopped — state saved.")}
                    return
                background = await _in_queue(self._run_b(ci, None))
        finally:
            if background:
                q, task = background
                while (ev := await q.get()) is not None:
                    yield ev
                await task

    async def regenerate_chapter(self, ci: int, note: str):
        """Rework: create chapter ci again with a note; replaces it in the unit."""
        if ci < len(self.unit.get("modules") or []):
            old_ids = set(self.unit["modules"][ci].get("lessons") or [])
            self.unit["lessons"] = [l for l in self.unit["lessons"]
                                      if l.get("id") not in old_ids]
            self.unit["glossary"] = [g for g in self.unit["glossary"]
                                    if g.get("lesson") not in old_ids]
        self.unit["state"] = "draft"
        async for ev in self.produce_chapter(ci, note=note):
            yield ev

    def _plan_script(self, chap: ga.Chapter, concepts: list[ga.Concept],
                     lessons_plan: list[dict], note: str | None) -> DAGPlan:
        summ = "\n\n".join(f"[{i+1}] {m.get('summary', '')}"
                          for i, m in enumerate(self.chapter_meta))
        # Only FIXED terminology is binding (see src.unit.terminology).
        glossary_state = self.terminology.binding_list(limit=30)
        addition = "\n\n" + learning.language_rule(self.language) + (
            f"\n\nREWORK NOTE (must be taken into account): {note}"
            if note else "")
        tasks = [DAGTask(id="cross", phase="cross", title="Terminology & cross-references",
                         prompt=learning.cross_prompt(summ, glossary_state) + addition)]
        by_concept = {cid: lp for lp in lessons_plan for cid in (lp.get("concepts") or [])}
        for n, k in enumerate(concepts, 1):
            lp = by_concept.get(k.id) or (lessons_plan[min(n-1, len(lessons_plan)-1)]
                                            if lessons_plan else {})
            tasks.append(DAGTask(
                id=f"script:{n}", phase="process",
                title=f"Script {k.id} ({k.name})",
                prompt=learning.script_prompt(k.__dict__, lp, self.profile,
                                          self.unit["depth_profile"], "")
                       + ("\n\n" + self._teaching_script_job(k.id)
                          if self._teaching_script_job(k.id) else "")
                       + ("\n\n" + self._evidence_block(k.id)
                          if self._evidence_block(k.id) else "") + addition,
                depends_on=["cross"],
                use_primary=(k.concept_class == "V"),
                # Criteria for PROSE, not for the finished lesson. The detail
                # plan's `check_criteria` describe the assembled lesson (quiz,
                # visualisation, self-check) — a process task cannot meet them
                # structurally, because it only delivers running text. Checking
                # them against it would force a score of 1/5 and thus a second
                # run of the expensive model per V concept, produced under
                # demotivating feedback. The lesson criteria belong to the
                # critic (critic_prompt), where the blocks exist. Only criteria
                # that can be decided from brief and output. Terminology has a
                # separate, better pass; the facts are checked by the fact
                # check against the material. Criteria the checker cannot
                # decide it would otherwise count as open and push the score
                # down for no reason.
                check_criteria=([
                    (f"Covers the concept '{k.name}' named in the brief "
                     f"and stays with it"),
                    "Running text throughout in HTML markup; no Markdown, no LaTeX",
                ] + ([("Keeps to the brief from the teaching script: introduces only "
                       "its own concept, does not derive prerequisites again, "
                       "does not anticipate what is named later")]
                     if self.teaching_script is not None else [])
                  + [learning.language_criterion(self.language)]),
            ))
        deps_block = "\n\n".join("{dep:" + t.id + "}" for t in tasks if t.phase == "process")
        tasks.append(DAGTask(
            id="finalize", phase="finalize", title="Assemble the chapter script",
            prompt=learning.chapter_finalize_prompt(chap.title).replace("{dep:*process}", deps_block)
                   + addition,
            depends_on=[t.id for t in tasks if t.phase == "process"], use_primary=True,
            check_criteria=[learning.language_criterion(self.language)]))
        return DAGPlan(title=f"Script: {chap.title}",
                       summary="Comprehension part of the chapter", tasks=tasks)

    def _plan_transform(self, ci_cache: int, chap: ga.Chapter, concepts: list[ga.Concept],
                        lessons_plan: list[dict], detail_plan: dict,
                        scripts: dict[str, str], chapter_script: str,
                        note: str | None) -> DAGPlan:
        addition = "\n\n" + learning.language_rule(self.language) + (
            f"\n\nREWORK NOTE (must be taken into account): {note}"
            if note else "")
        tasks: list[DAGTask] = []
        script_list = list(scripts.values())
        cache = self.lesson_cache.get(ci_cache) or {}
        for n, lp in enumerate(lessons_plan, 1):
            if (n - 1) in cache:
                # Already created (earlier, interrupted run) — do not pay
                # again. The data
                # come from the intermediate store in `_parse_and_repair`.
                continue
            source = script_list[n-1] if n-1 < len(script_list) else chapter_script
            tasks.append(DAGTask(
                id=f"bloecke:{n}", phase="process",
                title=f"Blocks: {lp.get('title', '')}",
                prompt=learning.transform_prompt(lp, self._script_for_prompt(source, ci_cache),
                                             self.unit["depth_profile"])
                       + ("\n\n" + self._teaching_script_job_lesson(lp)
                          if self._teaching_script_job_lesson(lp) else "")
                       + addition,
                # No LLM quality check: JSON validity, field names, self-check
                # and alt texts are checked by `check_lesson` deterministically
                # and completely, the didactics by the critic. A generic check
                # that sees only the first 4000 characters of a lesson of
                # 10,000-18,000 characters — that is, truncated JSON — would
                # have to rate "valid JSON" as missed. That would cost one
                # retry of the model per lesson and give no usable verdict.
                check_criteria=[],
                # These tasks produce the largest outputs of the pipeline
                # (10,000-18,000
                # characters). thinking=False is decisive: with thinking the
                # whole budget can
                # go there and the answer comes back with 0 characters.
                max_tokens=config.BLOCKS_MAX_TOKENS,
                thinking=config.BLOCKS_THINKING,
            ))
        tasks.append(DAGTask(
            id=f"bloecke:{len(lessons_plan)+1}", phase="process",
            title="Application part of the chapter",
            prompt=learning.tasks_prompt(chap.title, detail_plan, [k.__dict__ for k in concepts])
                       .replace("{dep:cross}", self._script_for_prompt(chapter_script, ci_cache)) + addition,
            use_primary=True,
            check_criteria=[
                "Each of these V concepts occurs in at least one task: "
                + (", ".join(k.name for k in concepts if k.concept_class == "V") or "(none)"),
                            "Sample solutions explain the why and end with a self-check",
                            "Reihenfolge: vorhersage → fehleranalyse → aufgabe → Fallaufgabe",
                            learning.language_criterion(self.language)]))
        deps_block = "\n\n".join("{dep:" + t.id + "}" for t in tasks)
        tasks.append(DAGTask(
            id="finalize", phase="finalize", title="Chapter summary",
            prompt=learning.chapter_meta_prompt(chap.title).replace("{dep:*process}", deps_block)
                   + addition,
            depends_on=[t.id for t in tasks]))
        return DAGPlan(title=f"Transformation: {chap.title}",
                       summary="Lernseiten + Anwendungsteil", tasks=tasks)

    async def _parse_and_repair(self, ci_cache: int, plan_b: DAGPlan,
                                   lessons_plan: list[dict]):
        """Parses the outputs of run B; lessons with format errors go through a
        validator-supported one-shot repair (fast LLM, concrete list of errors
        as the brief). Returns (lesson_data, exercises, number_repaired)."""
        from src.unit.validator import check_lesson
        process = [t for t in plan_b.tasks if t.phase == "process"]
        lesson_data: list[dict | None] = [None] * len(lessons_plan)
        exercises: list[dict] = []
        repaired = 0
        # Lessons taken over from an earlier, interrupted run.
        cache = self.lesson_cache.get(ci_cache) or {}
        for i, data_ in cache.items():
            if 0 <= i < len(lesson_data):
                lesson_data[i] = json.loads(json.dumps(data_))
        if cache:
            log.info("chapter %d: %d lessons taken over from the intermediate store",
                     ci_cache + 1, len(cache))
        # The tasks correspond only to the lessons NOT in the intermediate
        # store.
        open_ones = [i for i in range(len(lessons_plan)) if i not in cache]
        for pos, t in enumerate(process):
            i = open_ones[pos] if pos < len(open_ones) else pos
            if not t.output:
                continue
            try:
                data_ = parse_llm_json(t.output, context=f"{t.id}/{t.title}")
            except Exception as e:  # noqa: BLE001
                # A `continue` here would make the lesson disappear silently,
                # and the gate would notice nothing — in a real run 5 of 8
                # lessons could be lost that way. The cause is almost always
                # cut-off at the token budget: the block phase produces the
                # largest outputs of the whole pipeline (10,000-18,000
                # characters per lesson).
                log.warning("Task %s: JSON unreadable (%s) — %d characters received, "
                            "retrying with a larger budget",
                            t.id, e, len(t.output or ""))
                data_ = await self._catch_up_transform(t, lessons_plan, i)
                if data_ is None:
                    lp = lessons_plan[i] if i < len(lessons_plan) else {}
                    self.losses.append(
                        Msg("lesson '{title}' could not be created (JSON unreadable, even "
                            "after a retry)", {"title": lp.get("title") or t.title}))
                    log.error("lesson %s IS LOST: %s", t.id, e)
                    continue
            if i < len(lessons_plan):
                _prepare_blocks(data_)
                finding = check_lesson(data_, language=self.language)
                to_fix = finding.errors + self._fixable_warnings(finding)
                if to_fix and self.llm_fast:
                    new_ = await self._repair_lesson(data_, to_fix,
                                                        required=len(finding.errors))
                    if new_ is not None:
                        # Prepare the REPAIRED version as well. Without this
                        # its blocks would bypass
                        # alias resolution and normalisation completely — field
                        # names such as
                        # `beschriftung` would remain and block the final gate
                        # afterwards.
                        _prepare_blocks(new_)
                        data_, repaired = new_, repaired + 1
                lesson_data[i] = data_
                # Save at once: if the run breaks off now, it costs at most the
                # one lesson being created — not the whole block phase of the
                # chapter.
                self.lesson_cache.setdefault(ci_cache, {})[i] = data_
                self._persist_state()
            else:
                exercises = [_resolve_field_aliases(b) for b in (data_.get("exercises") or [])
                            if isinstance(b, dict)]
                for b in exercises:
                    normalise_block(b)
                if exercises:
                    pseudo = {"id": "ex", "title": "Anwendungsteil", "blocks": exercises}
                    finding = check_lesson(pseudo, language=self.language)
                    to_fix = (finding.errors
                                  + self._fixable_warnings(finding))
                    if to_fix and self.llm_fast:
                        new_ = await self._repair_lesson(
                            pseudo, to_fix, required=len(finding.errors))
                        if new_ is not None and new_.get("blocks"):
                            exercises, repaired = new_["blocks"], repaired + 1
        return lesson_data, exercises, repaired

    @staticmethod
    def _partial_lesson(raw: str | None) -> dict | None:
        """Rescues from a truncated answer what is already valid."""
        if not raw or "{" not in raw:
            return None
        try:
            data_ = parse_llm_json(raw, context="partial rescue")
        except Exception:  # noqa: BLE001
            return None
        if not isinstance(data_, dict):
            return None
        data_["blocks"] = [b for b in (data_.get("blocks") or [])
                            if isinstance(b, dict) and b.get("type")]
        return data_ if data_.get("blocks") else None

    async def _complete_lesson(self, task, begun: dict) -> dict | None:
        """Requests ONLY the missing blocks instead of building the lesson anew.

        The same technique as with the block patch: the output covers only the
        rest, stays small and therefore cannot break off again. What was
        already created validly does not go through the model and can
        consequently not be made worse.
        """
        present = begun.get("blocks") or []
        short = self._short_form(present)
        try:
            response = parse_llm_json(await self.llm.complete(
                task.prompt
                + "\n\nTHE LESSON HAS ALREADY BEEN PARTLY CREATED. Existing blocks:\n"
                + short
                + ("\n\nCreate ONLY the blocks still MISSING that complete the media plan "
                   "— do NOT repeat the existing ones. "
                   "Produce JSON: {\"further_blocks\": [ … ]}"),
                json_mode=True, max_tokens=8000, thinking=False),
                context=f"{task.id}/ergaenzen")
        except Exception as e:  # noqa: BLE001
            log.info("partial completion %s failed: %s", task.id, e)
            return None
        further = [b for b in (response.get("further_blocks") or [])
                   if isinstance(b, dict) and b.get("type")]
        if not further:
            return None
        begun["blocks"] = present + further
        log.info("lesson %s rescued: %d existing + %d added blocks",
                 task.id, len(present), len(further))
        return begun

    async def _catch_up_transform(self, task, lessons_plan, i):
        """Second attempt for a lesson with a larger token budget.

        The block phase runs on the fast model (8000 tokens), but produces the
        most extensive outputs of the pipeline. With tables, diagrams and more
        interactions required, the budget is often not enough.
        """
        if self.llm is None:
            return None
        try:
            # thinking=False is decisive here: a retry with max_tokens=16000
            # can come back with "0 characters received, finish_reason=length"
            # — the whole budget went into thinking tokens, nothing was left
            # for the output. More budget alone makes it worse, not better.
            # First RESCUE what is already there. The truncated answer of the
            # first attempt usually contains half the lesson; having it created
            # completely anew is expensive and can break off again.
            begun = self._partial_lesson(task.output)
            if begun and len(begun.get("blocks") or []) >= 3:
                full = await self._complete_lesson(task, begun)
                if full is not None:
                    return full

            response = await self.llm.complete(task.prompt, json_mode=True,
                                              max_tokens=16000, thinking=False)
            return parse_llm_json(response, context=f"{task.id}/nachholen")
        except Exception as e:  # noqa: BLE001
            log.warning("Second attempt for %s failed as well: %s",
                        task.id, e)
            return None

    # Warnings that can be fixed by replacing ONE block. Everything else —
    # distribution across the unit, density, length — cannot be repaired in one
    # block and does not belong here.
    # Codes of validator warnings that a block patch can fix. Recognised by
    # code, not by wording: the wording is translated.
    _FIXABLE_WARNINGS = (
        "cloze_readable",            # the solution is visible in the cloze text itself
        "no_feedback",               # quiz option without feedback
        "checks_nothing",            # all options correct
        "duplicate_front",           # duplicate flashcard
        "no_exploration_task",       # interactive graphic without a task
        "binding_without_name",      # control without a label
        "field_not_in_data",
        "trivial_pair",              # too easy a matching pair
    )

    @classmethod
    def _fixable_warnings(cls, finding) -> list[str]:
        """Warnings with a block reference that a block patch can fix.

        Without this the validator would find things nobody fixes: cloze
        texts that can be read off, quiz options without feedback, controls
        without labels — the repair would only get `finding.errors`. With the
        block patch the route is short: the messages already carry the block
        number.
        """
        return [w for w in finding.warnings_with_codes(cls._FIXABLE_WARNINGS) if "block[" in w]

    async def _repair_lesson(self, lesson: dict, errors: list[str],
                                 required: int | None = None) -> dict | None:
        """Fixes the validation errors of a lesson.

        First per block in a targeted way: the error messages already carry
        the block number (`block[3]: questions missing`), so the whole lesson
        need not go through the model. Only if no error can be assigned to a
        block does the full repair follow — and only if it demonstrably does
        not make the lesson worse.
        """
        from src.unit.validator import check_lesson
        if self.llm_fast is None:
            return None

        # ── Route 1: patch blocks one by one ─────────────────────────────
        findings = []
        for f in errors[:10]:
            m = re.search(r"block\[(\d+)\]", f)
            if m:
                findings.append({"block": int(m.group(1)),
                                "correction": re.sub(r"^.*?block\[\d+\]:\s*", "", f)})
        if findings:
            work = json.loads(json.dumps(lesson))
            n, _ = await self._patch_blocks(work, findings)
            if n:
                afterwards = check_lesson(work, language=self.language)
                # Success means: NO new error and fewer objections overall.
                # "Fewer errors
                # than before" alone would also hold if the repair damaged
                # other blocks.
                open_ = (len(afterwards.errors)
                         + len(self._fixable_warnings(afterwards)))
                if (len(afterwards.errors) <= (required if required is not None
                                            else len(errors))
                        and open_ < len(errors)):
                    work["id"] = lesson.get("id", work.get("id"))
                    return work

        # ── Route 2: full repair, with protection against getting worse
        # ──────────
        try:
            new_ = parse_llm_json(await self.llm_fast.complete(
                ("Repair the following lesson (unit.json format). Fix ONLY "
                "the errors listed; leave the content unchanged. Translate "
                "foreign-language fragments (Chinese characters, for instance) into the target language."
                "\n\nERRORS:\n")
                + "\n".join(f"- {f}" for f in errors[:10])
                + "\n\n" + learning.language_rule(self.language)
                # Not shortened — see _revision_acceptable.
                + "\n\nLESSON:\n" + json.dumps(lesson, ensure_ascii=False)
                + "\n\n" + learning.JSON_ONLY, json_mode=True))
        except Exception:  # noqa: BLE001 — repair is optional; otherwise the original stays
            return None

        # The error count alone is NOT enough: an empty lesson has exactly one
        # error ("no blocks") and would be accepted against three original
        # errors — the repair would have destroyed the lesson.
        ok, reason = self._revision_acceptable(lesson, new_)
        if not ok:
            log.warning("repair %s discarded: %s", lesson.get("id"), reason)
            return None
        if len(check_lesson(new_, language=self.language).errors) < len(errors):
            new_["id"] = lesson.get("id", new_.get("id"))
            return new_
        return None

    def _assemble_chapter(self, ci: int, chap: ga.Chapter, plan_b: DAGPlan,
                          lessons_plan: list[dict], lesson_data: list,
                          exercises: list[dict]) -> None:
        lesson_ids: list[str] = []
        for i, data_ in enumerate(lesson_data):
            if data_ is None:
                continue
            data_["id"] = self._unique_lesson_id(
                data_.get("id") or lessons_plan[i].get("id") or f"k{ci+1}l{i+1}")
            # Traceability: concept tags come authoritatively from the plan —
            # models must not be able to change the coverage chain.
            data_["concepts"] = (lessons_plan[i].get("concepts")
                                 or data_.get("concepts") or [])
            self.unit["lessons"].append(data_)
            lesson_ids.append(data_["id"])
        # Coverage safeguard: if the DETAIL PLAN already assigns a non-R
        # concept of the chapter to no lesson, it is attributed to the first
        # lesson — the final gate must never fail because of that.
        classes = {k.id: k.concept_class for k in self.gap.concepts}
        tagged = {cid for l in self.unit["lessons"]
                   if l["id"] in lesson_ids for cid in l.get("concepts", [])}
        first = next((l for l in self.unit["lessons"] if l["id"] in lesson_ids), None)
        for cid in chap.concepts:
            if classes.get(cid, "R") != "R" and cid not in tagged and first is not None:
                first.setdefault("concepts", []).append(cid)
                log.warning(("chapter %s: concept %s was not assigned to any lesson in the "
                            "detail plan — attributed to the first lesson"), ci + 1, cid)
        # Shown in the unit's navigation, so in the unit's language.
        module = {"title": f"{i18n.table_(self.language)['chapters']} {ci+1} · {chap.title}",
                  "lessons": lesson_ids,
                 "exercises": exercises}
        if ci < len(self.unit["modules"]):
            self.unit["modules"][ci] = module       # rework: replace instead of appending
        else:
            self.unit["modules"].append(module)
        self._sort_lessons()

        meta_raw = next((t.output for t in plan_b.tasks if t.phase == "finalize"), "")
        try:
            meta = parse_llm_json(meta_raw)
        except Exception:  # noqa: BLE001
            meta = {"summary": "", "new_terms": []}
        if ci < len(self.chapter_meta):
            self.chapter_meta[ci] = meta
        else:
            self.chapter_meta.append(meta)
        for g in meta.get("new_terms") or []:
            # Models occasionally deliver a list of strings instead of objects
            # here. Unchecked that would break the whole chapter with "'str'
            # object has no attribute 'get'".
            if isinstance(g, str):
                # A bare term without a definition is useless as a glossary
                # entry and blocks
                # the gate later. Discarding is more honest than entering an
                # empty shell.
                log.info("term '%s' without definition discarded", g.strip()[:40])
                continue
            if not isinstance(g, dict) or not g.get("term"):
                continue
            # The same rule as in _harvest_glossary: only provable notation
            # variants count as duplicates — qualifying brackets ("(Storey)",
            # "(DSGVO)") stay entries of their own.
            from src.unit.terminology import glossary_duplicate as _gd
            if any(_gd(g["term"], x.get("term", ""))
                   for x in self.unit["glossary"]):
                continue
            # Only what is covered is fixed; everything else stays a candidate
            # and does not become a binding standard for following chapters.
            covered, _ = self.terminology.covered(g["term"])
            if covered:
                self.terminology.set_(g["term"], g.get("definition", ""),
                                        source="kapitel-meta")
            # `short` carries the hover. Without a fallback exactly the entries
            # from this second glossary source would report "no short field".
            short = (g.get("short") or "").strip() or _first_sentence(g.get("definition", ""))
            self.unit["glossary"].append(
                {"term": g["term"], "definition": g.get("definition", ""),
                 "short": short,
                 **({"lesson": g["lesson"]} if g.get("lesson") in lesson_ids else {})})
        return lesson_ids

    # ────────────────── Terminology control ──────────────────

    def _prepare_terminology(self) -> None:
        """Sets the authorities: concept inventory and uploaded material."""
        if self.gap:
            self.terminology.set_inventory(getattr(self.gap, "concepts", []) or [])
        # The source corpus is the FULL TEXT of the material, not the status
        # sentence. For normative texts and textbooks it is the authority on
        # terminology; without it the check reports two thirds of all terms as
        # uncovered and the model judge has to do all the work.
        if self.material_full_text and self.folder:
            self._write_material()     # the folder only exists after the profile
        elif not self.material_full_text and self.folder:
            self._read_material()
        if self.material_full_text:
            self.terminology.set_corpus(self.material_full_text)
        if self.folder is None:      # the job folder only exists after the briefing
            return
        path_ = self.folder / "terminology-blocklist.json"
        if path_.exists():
            self.terminology.load_blocklist(path_)

    async def _check_terminology(self, text: str, occurrence: str) -> str:
        """Checks candidates and applies approved replacements.

        Order by cost: whitelist and source corpus are free, compound
        splitting as well; only the rest goes to the model. Whoever has
        uploaded no material has no source corpus — then the inventory alone
        carries, and the check reports correspondingly more.
        """
        open_ = self.terminology.check(text, occurrence)
        uncovered = [k for k in open_ if k["reason"] == "ungedeckt"]
        # Cases already decided: replace deterministically, without a model.
        text, replaced = self.terminology.replace(text)
        if replaced:
            log.info("Terminology: %d replacements from the blocklist (%s)",
                     replaced, occurrence)
        if not uncovered or self.llm is None:
            return text
        try:
            response = await self.llm.complete(
                learning.terminology_verdict_prompt(
                    uncovered, self.terminology.binding_list(),
                    # Specifically the places where the checked terms occur —
                    # not the first
                    # characters of the document. A second cut inside the
                    # prompt would be
                    # pointless as well: the inner one would win.
                    evidence_locations(self.material_full_text or self.material_context,
                                 [u.get("term") for u in uncovered
                                  if isinstance(u, dict)]))
                + "\n\n" + learning.language_rule(self.language), json_mode=True)
            verdicts = (parse_llm_json(response) or {}).get("verdicts") or []
        except Exception as e:  # noqa: BLE001 — the check must never stop production
            log.warning("Terminology check failed (%s): %s", occurrence, e)
            return text
        replacements = self.terminology.adopt_verdict(verdicts)
        if replacements:
            text, n = self.terminology.replace(text, replacements)
            log.info("terminology (%s): %d coinages replaced — %s",
                     occurrence, n, ", ".join(f"{a} -> {b}" for a, b in replacements.items()))
            self._notify(f"terminology: {len(replacements)} terms corrected")
        self.terminology.save(self.folder / "terminology.json")
        return text

    def _sort_lessons(self) -> None:
        """Lesson order = module order (important after rework)."""
        sequence_order = [lid for m in self.unit["modules"] for lid in (m.get("lessons") or [])]
        pos = {lid: i for i, lid in enumerate(sequence_order)}
        self.unit["lessons"].sort(key=lambda l: pos.get(l.get("id"), 10**6))

    def _harvest_glossary(self, chapter_script: str, lessons_plan: list[dict]) -> None:
        """Takes glossary entries in — but only covered terms as fixed.

        A newly appearing term must not go straight into the glossary and from
        there through cross_prompt into the next chapter as a binding standard.
        Uncovered terms are kept as candidates and fixed only after checking.
        """
        chapter_script = _normalise_glossary_marker(chapter_script)
        if "=== GLOSSAR ===" not in chapter_script:
            return
        # ONLY provable notation variants are merged ("X (BH)" vs "X (BH-
        # Verfahren)"). A plain comparison of cores would eat genuine
        # distinctions such as "q-Wert" vs "q-Wert (Storey)" — everything that
        # can be confused is reported by the validator as a suspect instead.
        from src.unit.terminology import glossary_duplicate

        ids = {lp.get("id") for lp in lessons_plan}
        for line in chapter_script.split("=== GLOSSAR ===", 1)[1].strip().splitlines():
            parts = [t.strip() for t in line.split("::")]
            if len(parts) < 2 or not parts[0]:
                continue
            if any(glossary_duplicate(parts[0], x.get("term", ""))
                   for x in self.unit["glossary"]):
                continue
            # Format: term :: short :: definition :: lesson-id
            # The three-column format (without short) stays readable.
            if len(parts) >= 4 or (len(parts) == 3 and parts[2] not in ids):
                short, definition = parts[1], parts[2]
                lesson = parts[3] if len(parts) > 3 else ""
            else:
                short, definition = parts[1], parts[1]
                lesson = parts[2] if len(parts) > 2 else ""
            covered, _ = self.terminology.covered(parts[0])
            if covered:
                self.terminology.set_(parts[0], definition, source="script")
            e = {"term": parts[0], "definition": definition, "short": short}
            if lesson in ids:
                e["lesson"] = lesson
            self.unit["glossary"].append(e)

    # ────────────────── Completion: consolidation (critic IN PARALLEL), gate
    # ──────────────────

    @staticmethod
    def _revision_acceptable(alt: dict, new_) -> tuple[bool, str]:
        """May `new` replace the lesson `old`?

        A revision should improve, not destroy. A lesson given in cut off at
        MAX_SCRIPT_CONTEXT cannot be returned completely by the model — and an
        answer replacing the original unconditionally would delete lessons;
        everything would look fine until the final gate reports "no blocks".
        """
        if not isinstance(new_, dict):
            return False, Msg("no object structure")
        if not (new_.get("title") or "").strip():
            return False, Msg("title missing")
        new_bl = [b for b in (new_.get("blocks") or []) if isinstance(b, dict)]
        old_bl = [b for b in (alt.get("blocks") or []) if isinstance(b, dict)]
        if not new_bl:
            return False, Msg("no blocks")
        # Losing more than a third is no longer polishing.
        if old_bl and len(new_bl) < len(old_bl) * 2 / 3:
            return False, Msg("only {new} instead of {old} blocks", {"new": len(new_bl), "old": len(old_bl)})
        old_w = sum(len(re.sub(r"<[^>]+>", " ", b.get("html", "")).split())
                    for b in old_bl if b.get("type") in ("text", "note"))
        new_w = sum(len(re.sub(r"<[^>]+>", " ", b.get("html", "")).split())
                    for b in new_bl if b.get("type") in ("text", "note"))
        if old_w > 200 and new_w < old_w * 0.6:
            return False, Msg("only {new} instead of {old} words", {"new": new_w, "old": old_w})
        return True, ""

    @staticmethod
    def _critic_verdict_usable(verdict) -> bool:
        """Only an object is a critic verdict.

        A model can answer with valid JSON `null` — parse_llm_json then does
        NOT raise (no parse error) but returns None, and a `verdict.get(...)`
        outside the try would raise AttributeError through asyncio.gather and
        break the WHOLE consolidation.
        """
        return isinstance(verdict, dict)

    @staticmethod
    def _final_test_usable(test) -> bool:
        """An object with a non-empty list of questions — otherwise better no final
        test at all than `null`/a torso in the unit (the same class of problem
        as with the critic verdict)."""
        return (isinstance(test, dict)
                and isinstance(test.get("questions"), list)
                and any(isinstance(f, dict) for f in test["questions"]))

    async def consolidate(self):
        yield {"kind": "phase",
               "text": Msg("Consolidation: final test + critic pass (parallel)")}
        self._notify("consolidation")
        summ = "\n".join(f"K{i+1}: {m.get('summary', '')}"
                        for i, m in enumerate(self.chapter_meta))
        try:
            test = parse_llm_json(await self.llm.complete(
                learning.final_test_prompt(self.unit["title"], summ)
                + "\n\n" + learning.language_rule(self.language), json_mode=True))
            if self._final_test_usable(test):
                self.unit["final_test"] = test
            else:
                yield {"kind": "warning",
                       "text": Msg("Final test: answer without a list of questions — skipped "
                                   "(can be done later through rework)")}
        except Exception as e:  # noqa: BLE001
            yield {"kind": "warning", "text": Msg("Final test failed: {error}", {"error": e})}

        # Pass deterministic block findings on to the critic. A slider without
        # effect stands as a warning in the remaining list — but no layer IN
        # the run would react to it. The critic is exactly the layer that can
        # patch blocks in a targeted way; it should know what the probe has
        # already proven instead of guessing it.
        warn_per_lesson: dict[str, list[str]] = {}
        quiz_bias = False
        try:
            preliminary = validate(self.unit)
            # A unit-wide finding that can only be fixed per lesson: the block
            # contract already forbids length bias — units still show it (13 of
            # 17 questions, for instance). Once proven it becomes a criterion
            # for every quiz lesson instead of remaining a hope in the prompt.
            quiz_bias = preliminary.has_code("quiz_longest_option")
            for w in preliminary.warnings_:
                if ".block[" not in w:
                    continue          # only block-exact, patchable findings
                m = re.match(r"lesson\[\d+\]\(([^)]*)\)(\.block\[\d+\]): (.*)", w)
                if m:
                    warn_per_lesson.setdefault(m.group(1), []).append(
                        f"{m.group(2)[1:]}: {m.group(3)}")
        except Exception as e:  # noqa: BLE001
            log.warning("preliminary validation for the critic skipped: %s", e)

        sem = asyncio.Semaphore(self.max_parallel)

        async def check_and_repair(li: int, lesson: dict):
            async with sem:
              try:
                try:
                    verdict = parse_llm_json(await self.llm.complete(
                        learning.critic_prompt(
                            self._short_form(lesson.get("blocks") or []),
                            self._criteria_for(lesson)
                            + [f"DETERMINISTIC FINDING (proven, "
                               f"fix with priority): {d}"
                               for d in warn_per_lesson.get(
                                   lesson.get("id"), [])[:3]]
                            + ([(f"QUIZ length balance (proven finding "
                                f"of this unit): the correct answer is "
                                f"mostly the longest option — bring the options "
                                f"of this lesson to a similar length, "
                                f"justify distractors just as concretely")]
                               if quiz_bias and any(
                                   b.get("type") == "quiz"
                                   for b in (lesson.get("blocks") or [])
                                   if isinstance(b, dict)) else [])
                            + [learning.language_criterion(self.language)],
                            self.unit["depth_profile"]), json_mode=True))
                except Exception:  # noqa: BLE001
                    return li, None, None
                if not self._critic_verdict_usable(verdict):
                    log.warning("critic %s: unusable verdict (%s) — skipped", lesson.get("id"),
                                type(verdict).__name__)
                    return li, None, None
                score = int(verdict.get("score", 5) or 5)
                if score >= 4 or not verdict.get("findings"):
                    return li, None, None
                # Patch FIRST in a targeted way: only the blocks objected to go
                # through the model, everything else stays literally untouched.
                # A full revision only comes into play if no finding refers to
                # a block.
                n_patch, message = await self._patch_blocks(
                    lesson, verdict["findings"][:6])
                if n_patch:
                    return li, ("PATCH", message), score
                corrections = "; ".join(b.get("correction", "") for b in verdict["findings"][:4])
                try:
                    new_ = parse_llm_json(await self.llm.complete(
                        learning.transform_prompt(lesson, "", self.unit["depth_profile"])
                        + "\n\n" + learning.language_rule(self.language)
                        + (f"\n\nREVISE the following lesson according to the CORRECTIONS "
                          f"(leave it unchanged otherwise):\nCORRECTIONS: {corrections}\n"
                          # Do NOT cut: whoever puts in a truncated lesson
                          # gets a truncated one back — which then replaced
                          # the complete original. A large prompt is better
                          # than a lost lesson.
                          f"LESSON: {json.dumps(lesson, ensure_ascii=False)}"),
                        json_mode=True))
                    new_["id"] = lesson["id"]
                    new_["concepts"] = lesson.get("concepts", [])
                    return li, new_, score
                except Exception:  # noqa: BLE001
                    return li, None, score
              except Exception as e:  # noqa: BLE001
                # The critic is an improvement layer: a single broken answer
                # (score not an int, unexpected structure, …) must NEVER break
                # the consolidation of all lessons — an AttributeError here
                # would do exactly that through asyncio.gather.
                log.warning("critic %s skipped: %s", lesson.get("id"), e)
                return li, None, None

        results_ = await asyncio.gather(
            *(check_and_repair(li, l) for li, l in enumerate(self.unit["lessons"])))
        # Record the scores for the technical report: critics can rate ALL
        # lessons 1-3 — whether that is quality of generation or strictness of
        # the rubric can only be judged with a visible distribution.
        self.critic_scores = {
            self.unit["lessons"][li].get("id"): score
            for li, _n, score in results_ if score is not None}
        for li, new_, score in results_:
            identifier = self.unit["lessons"][li].get("id")
            if isinstance(new_, tuple) and new_[:1] == ("PATCH",):
                yield {"kind": "info",
                       "text": Msg("Critic {id}: score {score} — {patch}",
                                   {"id": identifier, "score": score, "patch": new_[1]})}
                continue
            if score is not None:
                yield {"kind": "info",
                       "text": Msg("Critic {id}: score {score} — {outcome}",
                                   {"id": identifier, "score": score,
                                    "outcome": Msg("revised") if new_ else Msg("revision failed")})}
            if new_:
                ok, reason = self._revision_acceptable(self.unit["lessons"][li], new_)
                if ok:
                    self.unit["lessons"][li] = new_
                else:
                    log.warning("critic revision %s discarded: %s",
                                self.unit["lessons"][li].get("id"), reason)
                    yield {"kind": "info",
                           "text": Msg("Critic {id}: revision discarded ({reason}) — original kept",
                                       {"id": self.unit['lessons'][li].get('id'), "reason": reason})}
        async for ev in self._fact_check():
            yield ev
        async for ev in self._redundancy_pass():
            yield ev
        self._write_unit()
        self._persist_state()
        # Record the report here, not only when the result page is opened. With
        # production running on the server the window is often closed — then it
        # would never be written and the usage figures would be lost with the
        # process.
        self.technical_report()
        yield {"kind": "info", "text": Msg("Consolidation finished")}

    def _script_for_prompt(self, text: str, ci: int | None = None) -> str:
        """Script text for a prompt — UNSHORTENED as a rule.

        Didactically written text is not cut. Only if it exceeds the emergency
        brake does an explicitly marked structural substitute take its place.
        """
        text = text or ""
        # The glossary section is harvest payload for _harvest_glossary, not
        # prose. Unstripped it would go into the chapter's last lesson as a
        # text block "Glossar" — in addition to the real hover glossary, where
        # the same terms are correct.
        text = _normalise_glossary_marker(text).split("=== GLOSSAR ===", 1)[0].rstrip()
        if len(text) <= MAX_SCRIPT_CONTEXT:
            return text
        # Defensive: on a resumption or in partial tests one of the fields may
        # still be missing. A missing substitute component must not stop
        # generation.
        fp = (getattr(self, "detail_plans", {}) or {}).get(ci) if ci is not None else None
        meta = getattr(self, "chapter_meta", []) or []
        summ = ""
        if ci is not None and 0 <= ci < len(meta):
            summ = (meta[ci] or {}).get("summary") or ""
        substitute = script_structural_substitute(text, fp, summ)
        log.warning(("chapter script with %d characters exceeds %d — instead of truncated "
                    "prose a summary (%d characters) goes into the prompt. Content is lost "
                    "in the process; raise MAX_SCRIPT_CONTEXT if needed."),
                    len(text), MAX_SCRIPT_CONTEXT, len(substitute))
        return substitute

    @staticmethod
    def _short_form(blocks: list) -> str:
        """Numbered short form of a lesson — one entry per block.

        The basis both for the enrichment and for the critic; with it the
        critic need not rewrite the whole lesson.
        """
        rows = []
        for i, b in enumerate(blocks or []):
            if not isinstance(b, dict):
                continue
            raw = re.sub(r"<[^>]+>", " ", b.get("html") or b.get("description")
                         or b.get("task") or b.get("question") or "")
            rows.append(f"[{i}] {b.get('type')}: "
                          f"{re.sub(r'\s+', ' ', raw).strip()[:160]}")
        return "\n".join(rows)

    async def _patch_blocks(self, lesson: dict, findings: list) -> tuple[int, str]:
        """Replaces single blocks instead of rewriting the whole lesson.

        Returns (number of blocks replaced, message).

        Every substitute is checked ON ITS OWN against the block contract.
        Whatever does not pass is discarded — the original block stays. A
        revision therefore cannot make things worse, let alone delete a whole
        lesson.
        """
        blocks = lesson.get("blocks") or []
        # Only findings with a valid block reference; -1 (the whole lesson)
        # cannot be fixed by a block patch.
        affected: dict[int, list[str]] = {}
        for bf in findings:
            if not isinstance(bf, dict):
                continue
            try:
                n = int(bf.get("block", -1))
            except (TypeError, ValueError):
                continue
            if 0 <= n < len(blocks) and isinstance(blocks[n], dict):
                affected.setdefault(n, []).append(
                    (f"Block [{n}] ({blocks[n].get('type')}): "
                     f"{bf.get('correction') or bf.get('criterion') or ''}"))
        if not affected:
            return 0, Msg("no finding refers to a block")

        selection = {str(n): blocks[n] for n in sorted(affected)}
        corrections = "\n".join(x for list_ in affected.values() for x in list_)
        try:
            response = parse_llm_json(await self.llm.complete(
                learning.block_patch_prompt(
                    json.dumps(selection, ensure_ascii=False), corrections,
                    self.language, learning.BLOCK_CONTRACT_COMPACT),
                json_mode=True), context=f"blockpatch/{lesson.get('id')}")
        except Exception as e:  # noqa: BLE001 — improvement must never block
            return 0, Msg("patch failed ({error})", {"error": type(e).__name__})

        replaced = 0
        discarded = 0
        for entry in (response.get("replacements") or []):
            if not isinstance(entry, dict):
                continue
            try:
                n = int(entry.get("number", -1))
            except (TypeError, ValueError):
                continue
            new_ = entry.get("block")
            if not (0 <= n < len(blocks)) or not isinstance(new_, dict):
                continue
            if new_.get("type") != blocks[n].get("type"):
                discarded += 1
                continue
            _resolve_field_aliases(new_)
            normalise_block(new_, f"patch[{n}]")
            probe = {"id": "p", "title": "P", "state": "draft",
                     "depth_profile": self.unit.get("depth_profile", "compact"),
                     "lessons": [{"id": "p", "title": "P", "concepts": [],
                                    "blocks": [new_]}]}
            if validate(probe, node_probe=False).errors:
                discarded += 1
                continue
            blocks[n] = new_
            replaced += 1
        parts = [Msg("{n} block(s) replaced", {"n": replaced})]
        if discarded:
            parts.append(Msg("{n} discarded", {"n": discarded}))
        return replaced, Msg("{parts}", {"parts": parts})

    @staticmethod
    def _interaction_target(wtext: int, depth_profile: str | None) -> int:
        """Minimum number of interactions per lesson (didactics criterion C1b).

        C1b names 'about one per 400 words' as the FLOOR. `round(wtext/400)`
        would round this floor away (605 words -> target 2, 550 words ->
        target 1), so that the lesson with the most PLANNED interactions might
        be the only one not topped up. `ceil` sets the floor correctly; in the
        depth profile 'detailed' there are at least two from 500 words on, so
        that a stretch of reading never ends with a single final question.
        """
        target = max(1, math.ceil(max(wtext, 0) / 400))
        if (depth_profile or "") == "detailed" and wtext >= 500:
            target = max(target, 2)
        return target

    @staticmethod
    def _block_insertable(blocks: list, pos: int, blk: dict) -> tuple[bool, str]:
        """May `blk` be inserted at position `pos`?

        Prevents clusters: two (or four) `prediction` blocks directly in a
        row, because the enrichment inserted next to an existing block of the
        same type. Interactions and displays of the same type must not be
        adjacent; identical task texts are duplicates.
        """
        type_ = blk.get("type")
        core = re.sub(r"\s+", " ", str(blk.get("question") or blk.get("task")
                                       or blk.get("html") or ""))[:60].lower()
        neighbours = [blocks[i] for i in (pos - 1, pos)
                    if 0 <= i < len(blocks) and isinstance(blocks[i], dict)]
        for n in neighbours:
            if n.get("type") == type_ and type_ in (INTERACTIVE | ILLUSTRATION):
                return False, Msg("same type '{type}' directly adjacent", {"type": type_})
        if core:
            for b in blocks:
                if not isinstance(b, dict) or b.get("type") != type_:
                    continue
                alt = re.sub(r"\s+", " ", str(b.get("question") or b.get("task")
                                              or b.get("html") or ""))[:60].lower()
                if alt and alt == core:
                    return False, Msg("a block with the same content exists")
        return True, ""

    def _enrichment_status(self, lesson: dict) -> tuple[str, int, int]:
        """Describes the current state and the target value for the prompt."""
        blocks = lesson.get("blocks") or []
        wtext = len(re.sub(r"<[^>]+>", " ",
                           " ".join(b.get("html", "") or "" for b in blocks
                                    if isinstance(b, dict)
                                    and b.get("type") in ("text", "note"))).split())
        types_ = [b.get("type") for b in blocks if isinstance(b, dict)]
        interactive = [x for x in types_ if x in INTERACTIVE]
        visual = [x for x in types_ if x in ILLUSTRATION]
        target = self._interaction_target(wtext, self.unit.get("depth_profile"))
        situation = ((f"~{wtext} words of reading text. Present: {len(interactive)} interactions "
                f"({', '.join(sorted(set(interactive))) or 'none'}), "
                f"{len(visual)} displays ({', '.join(sorted(set(visual))) or 'none'}). "
                f"Minimum (C1b): at least {target} interactions and at least "
                f"2 displays, SPREAD over the lesson and in varying forms — "
                f"no block of the same type directly next to an existing one."))
        return situation, target, len(interactive)

    async def _enrich(self, lesson: dict, lp: dict) -> int:
        """Second pass per lesson: adds illustration and activity.

        Separate from building the blocks, because there prose and interaction
        compete for the same token budget — and prose comes first. Here the
        output is small (only new blocks), the risk of cut-off therefore low.

        If the first pass misses the C1b minimum, EXACTLY ONE targeted second
        attempt with the shortfall named follows. Then it stops — the
        enrichment stays non-blocking, and the validator reports a remaining
        rest as a warning.
        """
        if self.llm is None or not (lesson.get("blocks") or []):
            return 0
        inserted = 0
        for attempt in range(2):
            situation, target, ist = self._enrichment_status(lesson)
            if attempt and ist >= target:
                break
            if attempt:
                situation += ((f"\nREVISION: the first addition still lacks "
                         f"{target - ist} interaction(s) to reach the minimum. Add "
                         f"interactions in forms not used yet, specifically "
                         f"at places in the text without activity."))
            inserted += await self._enrich_once(lesson, lp, situation)
            _, target, ist = self._enrichment_status(lesson)
            if ist >= target:
                break
        return inserted

    async def _enrich_once(self, lesson: dict, lp: dict, situation: str) -> int:
        blocks = lesson.get("blocks") or []
        compact = []
        for i, b in enumerate(blocks):
            if not isinstance(b, dict):
                continue
            raw = re.sub(r"<[^>]+>", " ", b.get("html") or b.get("description")
                         or b.get("task") or "")
            compact.append(f"[{i}] {b.get('type')}: {re.sub(r'\s+', ' ', raw).strip()[:110]}")
        try:
            response = await self.llm.complete(
                learning.enrichment_prompt("\n".join(compact),
                                         ", ".join(lp.get("media_plan") or []),
                                         situation, learning.BLOCK_CONTRACT_COMPACT)
                + "\n\n" + learning.language_rule(self.language),
                json_mode=True, thinking=False)
            new_ones = (parse_llm_json(response, context=f"enrichment/{lesson.get('id')}",
                                   fallback={"new_blocks": []}) or {}).get("new_blocks") or []
        except Exception as e:  # noqa: BLE001 — enrichment must never block
            log.warning("Enrichment %s failed: %s", lesson.get("id"), e)
            return 0

        # Filter first, then sort: the sort key accesses `.get`, so the type
        # check must come before it.
        entries = [e for e in (new_ones if isinstance(new_ones, list) else [])
                     if isinstance(e, dict) and isinstance(e.get("block"), dict)]
        if len(entries) < len(new_ones or []):
            log.info("enrichment %s: %d unusable entries discarded",
                     lesson.get("id"), len(new_ones or []) - len(entries))
            self.enrichment_discarded += len(new_ones or []) - len(entries)

        def _pos(e):
            try:
                return -int(e.get("after_block", 0) or 0)
            except (TypeError, ValueError):
                return 0

        inserted = 0
        for entry in sorted(entries, key=_pos):
            blk = entry.get("block")
            if not blk.get("type"):
                continue
            _resolve_field_aliases(blk)
            normalise_block(blk)
            # Check each new block on its own against the block contract: an
            # enrichment must never damage a valid lesson.
            from src.unit.validator import check_lesson as _pl
            finding = _pl({"id": lesson.get("id"), "title": lesson.get("title", "x"),
                          "concepts": [], "blocks": [blk]}, language=self.language)
            if finding.errors:
                log.info("enrichment %s: block '%s' discarded (%s)",
                         lesson.get("id"), blk.get("type"), finding.errors[0][:80])
                self.enrichment_discarded += 1
                continue
            # after_block = index of the block AFTER which the new one is
            # inserted; -1 means "at the very beginning" (the prompt says the
            # same).
            pos = max(0, min(-_pos(entry) + 1, len(lesson["blocks"])))
            ok, reason = self._block_insertable(lesson["blocks"], pos, blk)
            if not ok:
                log.info("enrichment %s: block '%s' discarded (%s)",
                         lesson.get("id"), blk.get("type"), reason)
                self.enrichment_discarded += 1
                continue
            lesson["blocks"].insert(pos, blk)
            inserted += 1
        if inserted:
            log.info("enrichment %s: %d blocks added", lesson.get("id"), inserted)
        self.enriched += inserted
        return inserted

    async def _redundancy_pass(self):
        """Looks for repeated explanations across the whole unit.

        The counterpart to the critic, which deliberately checks each lesson
        on its own and therefore cannot see repetitions between lessons.
        """
        lessons = self.unit.get("lessons") or []
        if len(lessons) < 2 or self.llm is None:
            return
        yield {"kind": "phase", "text": Msg("Redundancy check across the whole unit")}
        rows = []
        for l in lessons:
            html = " ".join(b.get("html", "") for b in (l.get("blocks") or [])
                            if b.get("type") in ("text", "note"))
            over = re.findall(r"<h[34][^>]*>(.*?)</h[34]>", html, re.S | re.I)
            rows.append(f"{l.get('id')} ({l.get('title')}): "
                          + " | ".join(re.sub(r"<[^>]+>", "", u).strip() for u in over[:8])
                          + f"  [Konzepte: {', '.join(l.get('concepts') or []) or '—'}]")
        try:
            response = await self.llm.complete(
                learning.redundancy_prompt("\n".join(rows))
                + "\n\n" + learning.language_rule(self.language), json_mode=True)
            if not (response or "").strip():
                log.info("redundancy pass: empty answer — skipped")
                return
            verdict = parse_llm_json(response, context="redundanzpass",
                                    fallback={"findings": []})
        except Exception as e:  # noqa: BLE001
            log.warning("Redundancy pass failed: %s", e)
            return
        findings = (verdict or {}).get("findings") or []
        if not findings:
            yield {"kind": "info", "text": Msg("Redundancy check: no repeated explanations")}
            return
        for bf in findings[:8]:
            dupl = ", ".join(f"{d.get('lesson')}" for d in (bf.get("duplicates") or []))
            yield {"kind": "info",
                   "text": Msg("Redundancy: '{concept}' explained in {first} and again in {again}",
                               {"concept": bf.get('concept'), "first": bf.get('introduction'), "again": dupl})}
        self.unit.setdefault("check_report", {})["redundancy"] = findings

    async def _fact_piece(self, text: str, sem) -> list:
        """Checks ONE text section against the source material."""
        async with sem:
            try:
                evidence_texts = []
                if self.inventory_index is not None:
                    evidence = await self.inventory_index.retrieve(text[:1200], top_k=4)
                    evidence_texts = [
                        f"{getattr(b, 'display_label', getattr(b, 'title', '?'))}: "
                        f"{(getattr(b, 'full_text', '') or getattr(b, 'summary', ''))[:1200]}"
                        for b in evidence]
                verdict = parse_llm_json(await self.llm.complete(
                    learning.fact_check_prompt(text, evidence_texts)
                    + "\n\n" + learning.language_rule(self.language), json_mode=True))
                return verdict.get("findings") or []
            except Exception as e:  # noqa: BLE001
                return [{"claim": "(check failed)",
                         "status": "errors", "comment": str(e)}]

    async def _fact_check(self):
        """Checks lesson texts against the material inventory (in parallel);
        contradictions trigger a revision, everything goes into the check
        report."""
        if self.inventory_index is None or getattr(self.inventory_index, "is_empty", True):
            return
        yield {"kind": "phase", "text": Msg("Fact check against the source material (parallel)")}
        sem = asyncio.Semaphore(self.max_parallel)

        async def check(li: int, lesson: dict):
            # Numbers in diagrams and tables are checkable statements like any
            # other — precisely they can be invented, so they are checked
            # against the source material as well.
            parts = []
            for b_ in lesson.get("blocks", []):
                if not isinstance(b_, dict):
                    continue
                type_ = b_.get("type")
                if type_ in ("text", "note"):
                    parts.append(b_.get("html", ""))
                elif type_ == "table":
                    header = " | ".join(str(x) for x in (b_.get("header") or []))
                    rows = ["; ".join(str(c) for c in (z or []))
                              for z in (b_.get("rows") or [])]
                    parts.append(f"Tabelle ({b_.get('caption','')}): {header} — "
                                 + " / ".join(rows))
                elif type_ == "chart":
                    parts.append(f"Diagrammdaten ({b_.get('description','')}): "
                                 + json.dumps(_chart_numbers(b_), ensure_ascii=False))
            text = re.sub(r"<[^>]+>", " ", " ".join(parts))
            if not text.strip():
                return li, []
            # Do NOT cut, but split into pieces: with a cut at 6,000 characters
            # the end of a detailed lesson (up to 12,000 characters) would stay
            # unchecked — and precisely the part that contains the application
            # and the numbers. So the text is checked in sections at sentence
            # boundaries.
            pieces = _into_pieces(text, 6000)
            if len(pieces) > 1:
                log.info("fact check %s: text checked in %d sections (%d characters)", lesson.get("id"), len(pieces), len(text))
            findings_total = []
            for piece in pieces:
                findings_total += await self._fact_piece(piece, sem)
            return li, findings_total



        results_ = await asyncio.gather(
            *(check(li, l) for li, l in enumerate(self.unit["lessons"])))
        rows = [tr("# Fact check against the source material", self.ui_language), ""]
        for li, findings in results_:
            lid = self.unit["lessons"][li].get("id")
            if not findings:
                rows.append(tr("- {id}: no objections", self.ui_language, id=lid))
                continue
            for b in findings:
                rows.append(f"- {lid} · {b.get('status')}: {b.get('claim')} "
                              f"— {b.get('comment', '')}")
            yield {"kind": "warning",
                       "text": Msg("Fact check {id}: {n} finding(s) ({kinds})",
                                   {"id": lid, "n": len(findings),
                                    "kinds": ', '.join(sorted({b.get('status', '?') for b in findings}))})}
            contradictions = [b for b in findings if b.get("status") == "contradicts"]
            if contradictions:
                corrections = "; ".join(
                    (f"Correct the statement according to the source material: {b.get('claim')}"
                     f" ({b.get('comment', '')})") for b in contradictions[:3])
                new_ = await self._revision(self.unit["lessons"][li], corrections)
                if new_:
                    ok, reason = self._revision_acceptable(
                        self.unit["lessons"][li], new_)
                    if ok:
                        self.unit["lessons"][li] = new_
                        yield {"kind": "info",
                               "text": Msg("Fact check {id}: contradiction — lesson revised", {"id": lid})}
                    else:
                        log.warning("fact revision %s discarded: %s",
                                    self.unit["lessons"][li].get("id"), reason)
                        yield {"kind": "info",
                               "text": Msg("Fact check {id}: revision discarded ({reason}) — original kept",
                                           {"id": lid, "reason": reason})}
        (self.folder / "04-fact-check.md").write_text("\n".join(rows),
                                                          encoding="utf-8")

    async def _revision(self, lesson: dict, corrections: str) -> dict | None:
        try:
            new_ = parse_llm_json(await self.llm.complete(
                learning.transform_prompt(lesson, "", self.unit["depth_profile"])
                + "\n\n" + learning.language_rule(self.language)
                + (f"\n\nREVISE the following lesson according to the CORRECTIONS "
                  f"(leave it unchanged otherwise):\nCORRECTIONS: {corrections}\n"
                  # Not shortened — see _revision_acceptable: a truncated
                  # input produces a truncated output, which then replaced the
                  # complete lesson.
                  f"LESSON: {json.dumps(lesson, ensure_ascii=False)}"),
                json_mode=True))
            new_["id"] = lesson["id"]
            new_["concepts"] = lesson.get("concepts", [])
            return new_
        except Exception:  # noqa: BLE001
            return None

    def _criteria_for(self, lesson: dict) -> list[str]:
        for fp in self.detail_plans.values():
            for lp in fp.get("lessons") or []:
                if not isinstance(lp, dict):
                    continue
                if lp.get("id") == lesson.get("id"):
                    return (lp.get("check_criteria") or [])[:5]
        return ["learning objectives visibly pursued", "at least one example per core concept"]

    def finalise(self):
        """Final gate: state=final only with 0 errors. If the gate is blocked, a
        clearly marked DRAFT is assembled nevertheless — the user is never
        left without a visible result (rework closes the errors afterwards)."""
        self.unit["state"] = "final"
        # Last normalisation before the gate: critic and fact check have
        # rewritten lessons and may have brought in Markdown. After this every
        # remaining format remnant is a genuine error.
        log_ = normalise_unit(self.unit)
        if log_:
            log.info("Final normalisation: %s", "; ".join(log_[:15]))
        finding = validate(self.unit)
        # Downgrade instead of block: whatever is still broken after all repair
        # attempts is replaced by its description as text — provided it has a
        # usable one. A single broken diagram must not fail an otherwise
        # complete unit.
        replaced = degr.downgrade(self.unit, finding)
        if replaced:
            for e in replaced:
                log.info("Degradation: %s", e)
            self.degradations = replaced
            # Keep the originals: without them the broken source cannot be
            # found after the downgrade — and therefore cannot be repaired
            # either.
            if self.folder and degr.discarded:
                try:
                    (self.folder / "99-discarded-blocks.json").write_text(
                        json.dumps(degr.discarded, ensure_ascii=False, indent=1),
                        encoding="utf-8")
                    log.info("%d discarded blocks saved in 99-discarded-blocks.json", len(degr.discarded))
                except OSError as e:  # noqa: BLE001
                    log.warning("discarded blocks cannot be written: %s", e)
            finding = validate(self.unit)
            for e in replaced:
                finding.W("degradation", e.text, **e.params)
        for v in self.losses:
            finding.F("production", "{loss} — the unit is incomplete", loss=v)
        open_ = self.terminology.open_candidates()
        if open_:
            for k in open_[:10]:
                finding.W("terminology",
                          "unchecked term candidate '{term}' ({where}) — evidenced neither "
                          "in the inventory nor in the material",
                          term=k["term"], where=k.get("occurrence", "?"))
            self.terminology.save(self.folder / "terminology.json")
        if not finding.passed:
            self.unit["state"] = "draft"
            self._write_unit()
            self._notify("gate-blocked")
            draft_unit = {**self.unit, "title": "ENTWURF · " + self.unit.get("title", "")}
            result = assemble(draft_unit, self.folder / "dist",
                                   filename=f"{self.unit.get('id', 'learning-unit')}-draft.html")
            result.draft = True
            return finding, result
        self._write_unit()
        result = assemble(self.unit, self.folder / "dist")
        self._notify("done")
        return finding, result

    # ────────────────── Script handout ──────────────────

    def script_handout(self) -> tuple[Path, Path | None, str]:
        """Exports the chapter scripts as Markdown and (if possible) Word.

        Returns (md_path, docx_path|None, message). The main output of the
        LernWerkstatt remains the HTML unit.
        """
        from src.unit import i18n
        T = i18n.table_(self.language)
        parts = [f"# {self.unit.get('title', T['learning_unit'])} — {T['script']}"]
        for ci in sorted(self.scripts):
            title = (self.gap.chapters[ci].title
                     if self.gap and ci < len(self.gap.chapters)
                     else f"{T['chapters']} {ci+1}")
            parts.append(f"\n\n## {T['chapters']} {ci+1} · {title}\n\n"
                         + _html_to_md(_normalise_glossary_marker(self.scripts[ci]).split("=== GLOSSAR ===")[0]))
        md = "\n".join(parts)
        md_path = self.folder / "dist" / f"{self.unit.get('id', 'learning-unit')}-script.md"
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(md, encoding="utf-8")

        docx_path = md_path.with_suffix(".docx")
        try:                                  # route 1: formatted exporter
            from src.exporters.word_exporter import export_to_docx
            # "models" is the key the exporter reads; the pipeline passed
            # "modelle", so the model line never appeared.
            models = (self.unit.get("provenance") or {}).get("models") or ""
            generated = export_to_docx(md, title=self.unit.get("title", T["learning_unit"]),
                                     footer_info={"models": [models]} if models else None,
                                     language=self.language)
            shutil.move(generated, docx_path)
            message = Msg("Script exported as Markdown and Word.")
        except Exception as e1:  # noqa: BLE001
            try:                              # route 2: own minimal converter
                _md_to_docx(md, docx_path)
                message = Msg("Script exported as Markdown and Word (minimal layout; the "
                              "formatted export was not available).")
            except Exception as e2:  # noqa: BLE001 — Word is optional, Markdown is required
                docx_path = None
                message = Msg("Script exported as Markdown; Word export failed ({e1} / {e2})",
                              {"e1": e1, "e2": e2})
        return md_path, docx_path, message

    # ────────────────────────── Helfer ──────────────────────────

    def _executor(self) -> DAGExecutor:
        return DAGExecutor(self.llm, self.llm_fast, max_parallel=self.max_parallel,
                           enable_quality_checks=self.quality_checks,
                           stop_signal=self.stop_signal)

    def request_stop(self) -> None:
        self.stop_signal.request()

    def _unique_lesson_id(self, wish: str) -> str:
        basis = _slug(wish)
        if basis in ("start", "test", "glossary") or basis.startswith("ex-"):
            basis = "l-" + basis
        present = {l["id"] for l in self.unit["lessons"]}
        lid, n = basis, 2
        while lid in present:
            lid, n = f"{basis}-{n}", n + 1
        return lid

    # Full text of the material: lies in the job folder so that it survives a
    # resumption. It is the authority on terminology and feeds the fact check —
    # without it both would work blind after reloading.
    MATERIAL_FILE = "00-material-full-text.txt"

    @staticmethod
    def _sum_usage(current_value: list[dict], path_json) -> list[dict]:
        """Adds this process's usage to the saved state.

        The key is the role (strong/fast), not the model name — that can change
        between runs without making the summary invalid.
        """
        if path_json is None or not path_json.exists():
            return current_value
        try:
            alt = {m.get("role"): m for m in
                   (json.loads(path_json.read_text(encoding="utf-8")).get("llm") or [])}
        except (OSError, json.JSONDecodeError):
            return current_value
        sum_ = []
        for m in current_value:
            v = dict(m)
            a = alt.get(m.get("role"))
            if a:
                for field_ in ("calls", "input", "output", "truncated",
                             "empty", "rescued"):
                    v[field_] = (a.get(field_, 0) or 0) + (m.get(field_, 0) or 0)
            sum_.append(v)
        return sum_

    def _write_material(self) -> None:
        if not (self.folder and self.material_full_text):
            return
        try:
            (self.folder / self.MATERIAL_FILE).write_text(
                self.material_full_text, encoding="utf-8")
        except OSError as e:  # noqa: BLE001 — must never stop production
            log.warning("material full text cannot be written: %s", e)

    def _read_material(self) -> None:
        """Fetches the full text back after a resumption."""
        if not self.folder:
            return
        path_ = self.folder / self.MATERIAL_FILE
        if not path_.exists():
            return
        try:
            self.material_full_text = path_.read_text(encoding="utf-8")
        except OSError as e:  # noqa: BLE001
            log.warning("material full text cannot be read: %s", e)

    def technical_report(self, lang: str | None = None) -> str:
        """Usage and content summary of the run.

        The content figures are COUNTED from the finished unit, not carried
        along during production — so they cannot diverge from what is
        delivered.

        The usage figures, on the other hand, come from the LLM clients and
        are naturally zero after a restart or when an older job is loaded. In
        that case they are taken from the saved report — and the file is NOT
        overwritten, otherwise the real figures would be lost by merely
        looking.
        """
        md, data_ = tb.report(self.unit, self, lang or self.ui_language)
        path_json = (self.folder / "99-technical-report.json") if self.folder else None
        fresh = any(m.get("calls") for m in data_.get("llm") or [])

        if not fresh and path_json and path_json.exists():
            try:
                alt = json.loads(path_json.read_text(encoding="utf-8"))
                if any(m.get("calls") for m in alt.get("llm") or []):
                    data_["llm"] = alt["llm"]
                    data_["history"] = {**(alt.get("history") or {}),
                                        **{k: v for k, v in (data_.get("history") or {}).items()
                                           if v}}
                    data_["from_saved_run"] = True
                    md = tb.as_markdown(data_, lang or self.ui_language)
            except (OSError, json.JSONDecodeError, KeyError) as e:
                log.info("Saved report not readable: %s", e)

        # Write even without usage figures as long as no report exists: the
        # content summary is meaningful on its own, and a missing report would
        # be worse than an incomplete one.
        if self.folder and (fresh or not (path_json and path_json.exists())):
            # After a resumption the clients count only the calls of THIS
            # process. Without summing up, the saved report would be
            # overwritten with a fraction when continuing.
            data_["llm"] = self._sum_usage(data_.get("llm") or [], path_json)
            md = tb.as_markdown(data_, lang or self.ui_language)
            try:
                # The file is written in the job's language, the return value
                # in the viewer's language.
                (self.folder / "99-technical-report.md").write_text(
                    tb.as_markdown(data_, self.ui_language), encoding="utf-8")
                path_json.write_text(tb.as_json(data_), encoding="utf-8")
            except OSError as e:  # noqa: BLE001 — the report must never block
                log.warning("Technical report cannot be written: %s", e)
        return md

    def _write_unit(self) -> None:
        if self.folder:
            (self.folder / "content" / "unit.json").write_text(
                json.dumps(self.unit, ensure_ascii=False, indent=1), encoding="utf-8")

    @staticmethod
    def _translate(ev: dict) -> dict:
        """A DAG event as a message the production log can show.

        Task titles stay English in the plan, because the quality check
        quotes them to the model; only their display is translated.
        """
        kind = ev.get("event", "")
        title = _task_title(ev.get("title") or ev.get("task_id") or ev.get("task") or "")
        rest = {k: v for k, v in ev.items() if k not in ("event", "task", "task_id", "title")}
        if kind == "layer_start":
            text = Msg("Step {layer} of {total}: {n} task(s)", {
                "layer": ev.get("layer"), "total": ev.get("total_layers"),
                "n": len(ev.get("tasks") or [])})
        elif kind == "task_done":
            text = Msg("done: {title}", {"title": title})
        elif kind == "task_failed":
            text = Msg("failed: {title} — {error}", {"title": title, "error": ev.get("error", "")})
        elif kind == "task_skipped":
            text = Msg("skipped: {title} — {reason}", {"title": title, "reason": ev.get("reason", "")})
        elif kind == "layer_done":
            text = Msg("Step {layer} finished: {done} done, {failed} failed",
                       {"layer": ev.get("layer"), "done": ev.get("done", 0), "failed": ev.get("failed", 0)})
        elif kind == "all_done":
            text = Msg("All tasks finished: {done} of {total}",
                       {"done": ev.get("done", 0), "total": ev.get("total", 0)})
        elif kind == "stopped":
            text = Msg("Stopped after step {layer}", {"layer": ev.get("layer")})
        else:
            text = f"[{kind}] {title}".strip()
        return {"kind": "dag", "text": text, "raw": {"event": kind, **rest}}
