# -*- coding: utf-8 -*-
"""Validates a unit.json against the level contracts.

Deliberately without third-party dependencies (standard library only), so
that the check layer runs independently of the LLM stack. The simulator
trial run uses a Node subprocess (assets/sim_probe.mjs); if Node is
missing, it warns instead of checking.

CLI:  python -m src.unit.validator path/to/unit.json
Exit 0 = no errors, exit 1 = errors.
"""
from __future__ import annotations

import json
import re
import shutil

from src.unit import diagram_types as dtype
import subprocess
import sys
from src.i18n import N_, Msg, tr
from dataclasses import dataclass, field
from pathlib import Path

_ASSETS = Path(__file__).resolve().parents[2] / "assets"

# ── Principle of classification ────────────────────────────────────── ERRORS
# block delivery and are only justified if the learner is held up or misled by
# them: missing lessons, tasks that cannot be answered, unreadable structures.
#
# Everything that would only improve the unit is a WARNING. In practice
# blocking findings that are not real flaws of the unit come from program
# errors or from rules that forbid didactically legitimate forms.
#
# New checks therefore start as a warning. Only when they have proven accurate
# over several real runs may they block. A rule that has never run on real data
# does not belong in the gate.

RESERVED_IDS = {"start", "test", "glossary"}
# flashcards count as a self-check: they are level 1 (deterministic,
# schema-checked) and, through retrieval practice, the strongest form for
# terms. Without them in this set, using them would not satisfy C1 — and so
# nobody would use them.
SELF_CHECK = {"quiz", "cloze", "matching", "flashcards"}
# Everything that makes the learner act instead of read.
INTERACTIVE = SELF_CHECK | {"prediction", "simulator", "widget"}
# Block types that provide a non-textual display. Basis of the check
# "lesson without any illustration" — sanctioning only decoration and never
# the absence would push every lesson towards running text.
ILLUSTRATION = {"chart", "diagram", "table", "simulator", "widget",
                     "formula", "code"}
FORBIDDEN_IN_SIM = ["document", "window", "fetch", "XMLHttpRequest", "localStorage",
                   "setTimeout", "setInterval", "import(", "require("]
# Detection of language mixing (model drift, e.g. Qwen → Chinese): CJK
# ideographs, Hiragana/Katakana, Hangul, half-width Katakana.
_CJK = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af\uff66-\uff9f]")


def _foreign_chars(text: str) -> tuple[int, str]:
    hits = _CJK.findall(text or "")
    return len(hits), "".join(hits[:8])


# Format drift: models fall back to Markdown and LaTeX despite the HTML
# instruction. Both appear literally in the unit ("**Fachbegriff**", "$a
# \\cdot b^T$"). The normalisation layer repairs the usual case; whatever
# still arrives here is a genuine remnant and triggers the repair loop.
_MD_REST = [
    # CommonMark rule: emphasis only opens/closes WITHOUT whitespace directly
    # inside. The APA convention "(* p < .05, ** p < .01, *** p < .001)" would
    # match a looser pattern and block the final gate as a pseudo error —
    # subject matter of a statistics unit, not Markdown.
    (re.compile(r"\*\*(?!\s)[^*\n]+(?<!\s)\*\*"),
     Msg("Markdown bold (**…**) instead of <strong>")),
    (re.compile(r"(?<![\w*])\*(?!\s)[^*\n]+(?<!\s)\*(?![\w*])"),
     Msg("Markdown italics (*…*) instead of <em>")),
    (re.compile(r"^#{1,6}\s+\S", re.M), Msg("Markdown heading (#) instead of <h3>/<h4>")),
    (re.compile(r"^[ \t]*[-*+][ \t]+\S", re.M), Msg("Markdown list (-) instead of <ul><li>")),
    (re.compile(r"`[^`\n]+`"), Msg("Markdown code (`…`) instead of <code>")),
    (re.compile(r"\[[^\]\n]+\]\(https?://[^)\s]+\)"), Msg("Markdown link instead of <a>")),
    (re.compile(r"^\s*\|.+\|\s*$", re.M), Msg("Markdown table instead of a table block")),
]
# The primary signal is the backslash command, not the dollar sign — "$50"
# must not trigger a false alarm.
_LATEX_REST = [
    (re.compile(r"\\[a-zA-Z]{2,}"), Msg("LaTeX command (\\…) — belongs in a formula block")),
    (re.compile(r"\\\(|\\\)|\\\[|\\\]"), Msg("LaTeX delimiters (\\( \\)) not resolved")),
    (re.compile(r"\$[^$\n]*[\\^_][^$\n]*\$"), Msg("LaTeX between dollar signs")),
    (re.compile(r"\^\{|_\{"), Msg("LaTeX super/subscript (^{…}) instead of <sup>/<sub>")),
]




def _format_remnants(text: str) -> list[Msg]:
    """Reports Markdown and LaTeX remnants outside of code regions."""
    t = re.sub(r"<code\b.*?</code>|<pre\b.*?</pre>|<math\b.*?</math>", " ",
               text or "", flags=re.S | re.I)
    return [msg for pattern, msg in (_MD_REST + _LATEX_REST) if pattern.search(t)]


# Fields that become visible as text in the unit. Source texts (code.content,
# diagram.code, simulator.code, chart.spec) are deliberately excluded:
# backslash and asterisk are legitimate there.
_VISIBLE_FIELDS = ("html", "question", "resolution", "sample_solution", "task",
                     "explanation", "title", "caption", "description",
                     "text", "feedback", "front", "back", "definition",
                     "left", "right", "header", "rows", "hints", "material")

# Fields that are output ESCAPED. HTML is not the lead format there — on the
# contrary: `<ul><li>` would appear literally. A dash list in preformatted
# task material is the right display, not a flaw. The HTML rules must
# therefore not apply here.
_ESCAPED_FIELDS = ("material", "front", "back", "left", "right", "header",
                   "rows", "title", "description", "caption",
                   "feedback", "text", "hints")


def _visible_text(obj, depth: int = 0, html_only: bool = False) -> str:
    """Collects the visible text fields of a block recursively.

    `html_only=True` leaves out escaped fields — for checks that presuppose
    HTML as the lead format.
    """
    if depth > 6:
        return ""
    if isinstance(obj, str):
        return obj
    if isinstance(obj, list):
        return " ".join(_visible_text(x, depth + 1, html_only) for x in obj)
    if isinstance(obj, dict):
        allowed = [k for k in obj if k in _VISIBLE_FIELDS
                   and not (html_only and k in _ESCAPED_FIELDS)]
        return " ".join(_visible_text(obj[k], depth + 1, html_only)
                        for k in allowed)
    return ""


@dataclass
class Finding:
    """Result of a validation."""
    errors: list[str] = field(default_factory=list)
    warnings_: list[str] = field(default_factory=list)
    # Diagrams that stayed unchecked for lack of a working probe. Belongs TO
    # THE FINDING, not to the module: Gradio runs synchronous handlers in
    # worker threads, and two simultaneous validations would overwrite each
    # other through a module-wide list.
    unchecked: list[str] = field(default_factory=list)
    probe_reason: str = ""

    # Every message as (level, location, Msg), for the report in the
    # interface language. errors/warnings_ hold the same messages in English
    # as "location: text"; that form goes into repair prompts and logs, and
    # the pipeline reads the location from it.
    entries: list = field(default_factory=list)

    def F(self, path_: str, text: str, /, code: str = "", **params) -> None:
        m = Msg(text, params, code)
        self.entries.append(("F", path_, m))
        self.errors.append(f"{path_}: {m}")

    def W(self, path_: str, text: str, /, code: str = "", **params) -> None:
        m = Msg(text, params, code)
        self.entries.append(("W", path_, m))
        self.warnings_.append(f"{path_}: {m}")

    def has_code(self, code: str) -> bool:
        return any(m.code == code for _, _, m in self.entries)

    def warnings_with_codes(self, codes) -> list[str]:
        """English warnings whose message carries one of the given codes."""
        return [f"{p}: {m}" for level, p, m in self.entries if level == "W" and m.code in codes]

    @property
    def passed(self) -> bool:
        return not self.errors

    def report(self, lang: str | None = None) -> str:
        rows = [tr("WARNING  {text}", lang, text=f"{p}: {m.render(lang)}")
                for level, p, m in self.entries if level == "W"]
        rows += [tr("ERROR    {text}", lang, text=f"{p}: {m.render(lang)}")
                 for level, p, m in self.entries if level == "F"]
        rows.append("\n" + tr("{errors} errors, {warnings} warnings — {verdict}", lang,
                               errors=len(self.errors), warnings=len(self.warnings_),
                               verdict=tr("NOT passed.", lang) if self.errors else tr("passed.", lang)))
        return "\n".join(rows)


def _objects(b, list_, P: str, field_: str):
    """Iterates a list of objects tolerantly: non-objects are REPORTED as errors
    instead of breaking the check. A critic block patch can return
    `questions: [null, …]`; a `.get(...)` in _p_quiz would then raise
    AttributeError and, through the patch probe and asyncio.gather, break
    the whole consolidation. The validator is the protective layer of the
    pipeline — it must not raise on ANY input itself.
    """
    for i, e in enumerate(list_ or []):
        if isinstance(e, dict):
            yield i, e
        else:
            b.F(f"{P}.{field_}[{i}]", "not an object")


def _is_str(v) -> bool:
    return isinstance(v, str) and v.strip() != ""


def _words(html: str) -> int:
    return len([w for w in re.sub(r"<[^>]+>", " ", html or "").split() if w])


def validate(unit: dict, node_probe: bool = True) -> Finding:
    """Complete validation of a unit. Returns the finding (errors/warnings)."""
    b = Finding()

    # ── Grundstruktur ──
    if not _is_str(unit.get("id")):
        b.F("unit.id", "missing or empty")
    if not _is_str(unit.get("title")):
        b.F("unit.title", "missing or empty")
    lessons = unit.get("lessons")
    if not isinstance(lessons, list) or not lessons:
        b.F("unit.lessons", "at least one lesson required")
        lessons = []
    provenance = unit.get("provenance")
    if not isinstance(provenance, dict) or not isinstance(provenance.get("sources"), list):
        b.W("unit.provenance", "provenance.sources missing — provenance incomplete")

    def _block_safe(blk, path_):
        # Net under everything: even a structural gap overlooked in the future
        # makes the block an ERROR instead of breaking production or the patch
        # probe.
        try:
            _check_block(b, blk, path_, node_probe)
        except Exception as e:  # noqa: BLE001
            b.F(path_, "block check aborted ({v1}: {e}) — the block counts as faulty", v1=type(e).__name__, e=e)

    ids: set[str] = set()
    for li, l in enumerate(lessons):
        if not isinstance(l, dict):
            b.F(f"lesson[{li}]", "not an object")
            continue
        P = f"lesson[{li}]({l.get('id', '?')})"
        lid = l.get("id")
        if not _is_str(lid):
            b.F(P, "id missing")
        elif lid in ids:
            b.F(P, "id duplicated")
        else:
            ids.add(lid)
        if (lid in RESERVED_IDS) or re.match(r"^ex-", lid or ""):
            b.F(P, "id is reserved (start|test|glossary|ex-*)")
        if not _is_str(l.get("title")):
            b.F(P, "title missing")
        blocks = l.get("blocks")
        if not isinstance(blocks, list) or not blocks:
            b.F(P, "no blocks")
            blocks = []
        if not isinstance(l.get("learning_objectives"), list) or not l.get("learning_objectives"):
            b.W(P, "no learning objectives given")
        interactive = [x.get("type") for x in blocks
                      if isinstance(x, dict) and x.get("type") in INTERACTIVE]
        if not any(t in SELF_CHECK for t in interactive):
            b.W(P, "no self-check (quiz/cloze/matching/flashcards) — didactics criterion C1")
        # Density: C1 asks for exactly ONE self-check. A lesson with 1200 words
        # and one quiz at the end would comply — the learner reads for twenty
        # minutes and acts once. The minimum therefore scales with the length.
        wtext = _words(" ".join(x.get("html", "") or "" for x in blocks
                                  if isinstance(x, dict) and x.get("type") in ("text", "note")))
        target = max(1, round(wtext / 400))
        if len(interactive) < target:
            b.W(P, "~{wtext} words of reading text, but only {v1} interaction(s) — about {target} would be appropriate. The learner should not have to wait until the end of the lesson to act", wtext=wtext, v1=len(interactive), target=target)
        if len(interactive) >= 3 and len(set(interactive)) == 1:
            b.W(P, "all {v1} interactions are of type '{v2}' — derive the form from the learning purpose (recall terms, separate what is easily confused, reconstruct an order, confront a misconception)", v1=len(interactive), v2=interactive[0])
        for bi, blk in enumerate(blocks):
            _block_safe(blk, f"{P}.block[{bi}]")

    if unit.get("final_test"):
        at = unit["final_test"]
        if not isinstance(at, dict):
            b.F("final_test", "not an object")
        else:
            _block_safe({"type": "quiz", "questions": at.get("questions")},
                          "final_test")

    # ── Course structures: modules and glossary ──
    assigned: set[str] = set()
    if unit.get("modules") is not None:
        if not isinstance(unit["modules"], list):
            b.F("unit.modules", "must be an array")
        else:
            for mi, m in enumerate(unit["modules"]):
                if not isinstance(m, dict):
                    b.F(f"modules[{mi}]", "not an object")
                    continue
                P = f"modules[{mi}]({m.get('title', '?')})"
                if not _is_str(m.get("title")):
                    b.F(P, "title missing")
                if not isinstance(m.get("lessons"), list) or not m.get("lessons"):
                    b.F(P, "lessons (list of lesson ids) missing")
                for lid in m.get("lessons") or []:
                    if lid not in ids:
                        b.F(P, "references unknown lesson '{lid}'", lid=lid)
                    if lid in assigned:
                        b.F(P, "lesson '{lid}' is assigned to several modules", lid=lid)
                    assigned.add(lid)
                for bi, blk in enumerate(m.get("exercises") or []):
                    _block_safe(blk, f"{P}.exercises[{bi}]")
            for lid in ids:
                if lid not in assigned:
                    b.W("unit.modules", "lesson '{lid}' is not assigned to any module — it appears under 'More lessons'", lid=lid)

    if unit.get("glossary") is not None:
        if not isinstance(unit["glossary"], list):
            b.F("unit.glossary", "must be an array")
        else:
            terms: set[str] = set()
            for gi, g in enumerate(unit["glossary"]):
                if not isinstance(g, dict):
                    b.F(f"glossary[{gi}]", "not an object")
                    continue
                P = f"glossary[{gi}]({g.get('term', '?')})"
                if not _is_str(g.get("term")):
                    b.F(P, "term missing")
                if not _is_str(g.get("definition")):
                    b.F(P, "definition missing")
                if _is_str(g.get("term")):
                    k = g["term"].lower()
                    if k in terms:
                        b.W(P, "term duplicated in the glossary")
                    terms.add(k)
                if g.get("lesson") is not None and g["lesson"] not in ids:
                    b.W(P, "lesson '{v1}' does not exist — the reference is not shown", v1=g['lesson'])

    # ── Concept coverage (traceability) ──
    if unit.get("state") is not None and unit["state"] not in ("draft", "final"):
        b.W("unit.state", "'{v1}' unknown (draft|final)", v1=unit['state'])
    if unit.get("concepts") is not None:
        final = unit.get("state") != "draft"
        rep = b.F if final else b.W
        if not isinstance(unit["concepts"], list):
            b.F("unit.concepts", "must be an array")
        else:
            kmap: dict[str, dict] = {}
            for ci, k in enumerate(unit["concepts"]):
                if not isinstance(k, dict):
                    b.F(f"concepts[{ci}]", "not an object")
                    continue
                P = f"concepts[{ci}]({k.get('id', '?')})"
                if not _is_str(k.get("id")):
                    b.F(P, "id missing")
                if not _is_str(k.get("name")):
                    b.F(P, "name missing")
                if k.get("concept_class") not in ("V", "K", "D", "R"):
                    b.F(P, "concept_class '{v1}' unknown (V|K|D|R)", v1=k.get('concept_class'))
                if _is_str(k.get("id")):
                    if k["id"] in kmap:
                        b.F(P, "id duplicated")
                    else:
                        kmap[k["id"]] = k
            in_lesson: set[str] = set()
            in_exercise: set[str] = set()
            for li, l in enumerate(lessons):
                if not isinstance(l, dict):
                    continue
                if l.get("concepts") is None:
                    b.W(f"lesson[{li}]({l.get('id')})",
                        "no concepts assigned — coverage of this lesson cannot be checked")
                    continue
                for cid in l.get("concepts") or []:
                    if cid in kmap:
                        in_lesson.add(cid)
                    else:
                        b.F(f"lesson[{li}]({l.get('id')}).concepts", "unknown concept '{cid}'", cid=cid)
            for mi, m in enumerate(unit.get("modules") or []):
                if not isinstance(m, dict):
                    continue          # already reported as an error above
                for bi, blk in enumerate(m.get("exercises") or []):
                    if not isinstance(blk, dict):
                        continue
                    for cid in blk.get("concepts") or []:
                        if cid in kmap:
                            in_exercise.add(cid)
                        else:
                            b.F(f"modules[{mi}].exercises[{bi}].concepts", "unknown concept '{cid}'", cid=cid)
            for cid, k in kmap.items():
                if k.get("concept_class") == "R":
                    continue
                if cid not in in_lesson:
                    rep("unit.concepts",
                        N_("concept '{cid}' ({name}, class {cls}) appears in NO lesson{consequence}"),
                        cid=cid, name=k.get("name"), cls=k.get("concept_class"),
                        consequence=Msg(" — blocks delivery") if final else Msg(" (state: draft)"))
                if k.get("concept_class") == "V" and cid not in in_exercise:
                    b.W("unit.concepts", "V concept '{cid}' ({v1}) is not practised in any application part", cid=cid, v1=k.get('name'))

    # ── Language discipline (unit level: warning; per lesson via check_lesson)
    # ──
    lang = (unit.get("language") or "de").lower()
    if lang in ("de", "en"):
        n, probe = _foreign_chars(json.dumps(unit, ensure_ascii=False))
        if n:
            b.W("unit", "{n} CJK characters found (e.g. '{probe}') — mixed languages? unit.language is '{lang}'", n=n, probe=probe, lang=lang)

    # ── Kurs-Modus-Heuristiken ──
    cnt = len(lessons)
    if unit.get("depth_profile") is not None and unit["depth_profile"] not in ("compact", "detailed"):
        b.W("unit.depth_profile", "'{v1}' unknown (compact|detailed)", v1=unit['depth_profile'])
    if unit.get("depth_profile") == "detailed":
        for li, l in enumerate(lessons):
            if not isinstance(l, dict):
                continue
            text = " ".join(x.get("html", "") or "" for x in (l.get("blocks") or [])
                            if isinstance(x, dict) and x.get("type") in ("text", "note"))
            w = _words(text)
            if w >= 500:
                continue
            # The word count alone says little. A short lesson with four
            # interactions and three displays is dense, not thin — so it is
            # only reported if the lesson is ALSO poor in activity and
            # illustration. BUT: B8 says explicitly "interactions are no
            # replacement for text". A very short lesson (<400 words) in the
            # profile 'detailed' therefore gets a warning even if it is rich in
            # interaction — a 334-word lesson with four interactions would
            # otherwise pass without any hint.
            bl = [x for x in (l.get("blocks") or []) if isinstance(x, dict)]
            act = sum(1 for x in bl if x.get("type") in INTERACTIVE)
            show = sum(1 for x in bl if x.get("type") in ILLUSTRATION)
            if act >= 3 or act + show >= 5:
                if w < 400:
                    b.W(f"lesson[{li}]({l.get('id')})",
                        "~{w} words of text — interactions do not replace developing running text (B8: 800–1500 words in depth profile 'detailed')", w=w)
                continue
            b.W(f"lesson[{li}]({l.get('id')})",
                "~{w} words of text with {act} interaction(s) and {show} display(s) — too thin for depth profile 'detailed'. Either developed running text (800–1500 words) or more activity and illustration", w=w, act=act, show=show)
    if isinstance(unit.get("modules"), list) and unit["modules"] and (
            unit.get("depth_profile") == "detailed" or cnt > 6):
        for mi, m in enumerate(unit["modules"]):
            if not isinstance(m.get("exercises"), list) or not m.get("exercises"):
                b.W(f"modules[{mi}]({m.get('title', '?')})",
                    "no application part (exercises) — consolidated tasks per chapter are part of the book model")
    if cnt > 6 and not (isinstance(unit.get("modules"), list) and unit["modules"]):
        b.W("unit", "{cnt} lessons without modules grouping — the learning path becomes hard to follow", cnt=cnt)
    if cnt > 6 and not (isinstance(unit.get("glossary"), list) and unit["glossary"]):
        b.W("unit", "{cnt} lessons without glossary — looking things up later is hardly possible", cnt=cnt)
    if cnt > 4:
        for li, l in enumerate(lessons):
            if not isinstance(l, dict):
                continue
            text = " ".join(x.get("html", "") or "" for x in (l.get("blocks") or [])
                            if isinstance(x, dict) and x.get("type") == "text")
            w = _words(text)
            if w > 350 and not re.search(r"<h[34][\s>]", text, re.I):
                b.W(f"lesson[{li}]({l.get('id')})",
                    "~{w} words of text without h3/h4 subheadings — headings become search anchors and deep links", w=w)
    # Missing illustration: sanctioning only decoration leaves no counterweight
    # — every incentive then points towards running text (the step rule chooses
    # the simplest block, the word target applies only to prose).
    for li, l in enumerate(lessons):
        if not isinstance(l, dict):
            continue
        blocks = [x for x in (l.get("blocks") or []) if isinstance(x, dict)]
        text = " ".join(x.get("html", "") or "" for x in blocks
                        if x.get("type") in ("text", "note"))
        w = _words(text)
        types_ = {x.get("type") for x in blocks}
        if w > 400 and not (types_ & ILLUSTRATION):
            b.W(f"lesson[{li}]({l.get('id')})",
                "~{w} words without any illustration (diagram, table, chart, formula, simulator) — derive the form of display from the type of content, not running text only", w=w)
    # A unit entirely WITHOUT a diagram. Tables show values, diagrams show
    # RELATIONS — processes, states, dependencies. If the second form of
    # display is missing completely, everything structural stays in running
    # text.
    #
    # Deliberately only the zero case: in the units generated so far the
    # density lay between 0.4 and 1.4 diagrams per ten blocks — a threshold in
    # between would be guessed. Zero diagrams with substantial length, on the
    # other hand, is undisputed.
    all_blocks = [x for l in lessons if isinstance(l, dict) for x in (l.get("blocks") or [])
                    if isinstance(x, dict)]
    diagrams = [x for x in all_blocks if x.get("type") == "diagram"]
    if len(all_blocks) >= 40 and not diagrams:
        b.W("unit", "not a single diagram in {v1} blocks — tables show values, diagrams show relations (processes, states, dependencies). Everything structural stays in running text", v1=len(all_blocks))

    # Length bias: if the correct answer is regularly the longest, the quiz can
    # be solved without understanding — one chooses the most detailed option. A
    # well-known test artefact, and a model falls for it reliably, because it
    # justifies the correct answer and merely asserts the wrong ones. Measured
    # on a real unit: nine out of nine questions.
    questions = [fr for l in lessons if isinstance(l, dict) for x in (l.get("blocks") or [])
              if isinstance(x, dict) and x.get("type") == "quiz"
              for fr in (x.get("questions") or []) if isinstance(fr, dict)]
    _at = unit.get("final_test")
    questions += [fr for fr in ((_at.get("questions") if isinstance(_at, dict) else None) or [])
               if isinstance(fr, dict)]
    longest = 0
    countable = 0
    for fr in questions:
        opts = [o for o in (fr.get("options") or []) if isinstance(o, dict)]
        right_answer = [o for o in opts if o.get("correct")]
        if len(opts) < 3 or len(right_answer) != 1:
            continue
        countable += 1
        length = {len(str(o.get("text") or "")) for o in opts}
        if len(length) > 1 and len(str(right_answer[0].get("text") or "")) == max(length):
            longest += 1
    if countable >= 3 and longest / countable >= 0.7:
        b.W("unit", "in {longest} of {countable} quiz questions the correct answer is the longest option — it can be solved without understanding. Justify wrong options as fully as the correct one", code="quiz_longest_option", longest=longest, countable=countable)

    # Diagram variety: Mermaid knows a dozen types; in practice almost only
    # flowchart is produced. From four diagrams on that is a monoculture and
    # usually a sign of unused means of expression.
    diagrams = [x for l in lessons if isinstance(l, dict) for x in (l.get("blocks") or [])
                 if isinstance(x, dict) and x.get("type") == "diagram"]
    kinds = {a for x in diagrams if (a := dtype.detect(x.get("code") or ""))}
    if len(diagrams) >= 4 and len(kinds) <= 1:
        b.W("unit", "all {n} diagrams are of type '{kind}' — Mermaid also knows {others}",
            n=len(diagrams), kind=next(iter(kinds), "?"),
            others=", ".join(k for k in dtype.TYPES if k not in kinds))

    all_types = {x.get("type") for l in lessons if isinstance(l, dict) for x in (l.get("blocks") or [])
                  if isinstance(x, dict)}
    if len(lessons) >= 3 and len(all_types - {"text", "note"}) < 5:
        b.W("unit", "only {v1} different forms of display and interaction in the whole unit ({v2}) — also available: chart (interactive via params too), simulator, flashcards, prediction, cloze, formula", v1=len(all_types - {'text', 'note'}), v2=', '.join(sorted(all_types - {'text', 'note'})))
    # Interaction density per lesson (didactics C1b): about one self-check or
    # activity per 400 words of reading text is the FLOOR, not the target. A
    # warning, not an error (see the principle above: new rules start as a
    # warning).
    for li, l in enumerate(lessons):
        if not isinstance(l, dict):
            continue
        blocks = [x for x in (l.get("blocks") or []) if isinstance(x, dict)]
        text = " ".join(x.get("html", "") or "" for x in blocks
                        if x.get("type") in ("text", "note"))
        w = _words(text)
        if w <= 400:
            continue
        # Tasks and error analyses IN the lesson are activity as well — not
        # counting them produces false alarms on perfectly legitimate lessons
        # that carry their activation exactly like that.
        act = sum(1 for x in blocks
                      if x.get("type") in INTERACTIVE | {"task", "error_analysis"})
        needed = -(-w // 400)          # ceil(w/400)
        if act < needed:
            b.W(f"lesson[{li}]({l.get('id')})",
                "~{w} words of reading text with only {act} interaction(s) — guideline C1b: about one per 400 words ({needed} would be the floor), spread over the lesson", w=w, act=act, needed=needed)
    # Adjacency: two INTERACTIONS of the same type directly in a row are almost
    # always an enrichment duplicate, not a distribution (e.g. 2x prediction in
    # a row). Displays are excluded — two charts or diagrams side by side are a
    # legitimate means of design (before/after, comparison) and are often
    # planned like that in the detail plan.
    for li, l in enumerate(lessons):
        if not isinstance(l, dict):
            continue
        blocks = [x for x in (l.get("blocks") or []) if isinstance(x, dict)]
        for bi in range(1, len(blocks)):
            t1, t2 = blocks[bi - 1].get("type"), blocks[bi].get("type")
            if t1 == t2 and t1 in INTERACTIVE:
                b.W(f"lesson[{li}]({l.get('id')}).block[{bi}]",
                    "two '{t1}' blocks directly in a row — distribute or merge them (C1b/C1c)", t1=t1)
    # Distribution: if illustration clusters in one lesson and the others get
    # none, the unit total is inconspicuous, but the reading impression is
    # still uneven.
    per_lesson = [sum(1 for x in (l.get("blocks") or [])
                       if isinstance(x, dict) and x.get("type") in ILLUSTRATION)
                   for l in lessons if isinstance(l, dict)]
    if len(per_lesson) >= 3 and max(per_lesson) >= 3 and min(per_lesson) <= 1:
        b.W("unit", "illustration unevenly distributed ({v1} per lesson) — the weakest lesson is almost text only", v1=', '.join(str(x) for x in per_lesson))

    # Size policy for Vega-Lite: vega + vega-lite + vega-embed are about 1.5 MB
    # that go into every unit using the engine. That pays off for real
    # exploration; not for a bar chart — Chart.js does that at about a seventh
    # of the size.
    vega = [blk for l in lessons if isinstance(l, dict) for blk in (l.get("blocks") or [])
            if isinstance(blk, dict) and blk.get("type") == "chart"
            and blk.get("engine") == "vegalite"]
    if vega and not any(isinstance(x.get("spec"), dict) and x["spec"].get("params")
                        for x in vega):
        b.W("unit", "{v1}x vegalite without a single interactive parameter — that embeds about 1.5 MB of library for static graphics; chartjs does the same at about a seventh of the size", v1=len(vega))

    # Interaction variety across the whole unit: if eight lessons contain only
    # quizzes, that is not a didactic finding per lesson but a monoculture —
    # visible only from above.
    all_int = [x.get("type") for l in lessons if isinstance(l, dict) for x in (l.get("blocks") or [])
                if isinstance(x, dict) and x.get("type") in INTERACTIVE]
    if len(lessons) >= 3 and len(all_int) >= 4 and len(set(all_int)) <= 1:
        b.W("unit", "all {v1} interactions of the unit are of type '{v2}' — also available: flashcards, matching, cloze, prediction, simulator", v1=len(all_int), v2=all_int[0])

    if b.unchecked:
        b.W("environment", "{v1} diagram(s) not syntax-checked: {v2}. This is a setup problem, not a flaw of the unit — syntax errors then only show up for the learner.", v1=len(b.unchecked), v2=b.probe_reason or 'checker not available')

    # Suspect glossary pairs: entries close enough to be confused (same core,
    # core↔bracket crossing, same abbreviation on different cores).
    # Deliberately ONLY a warning and deliberately not merged automatically:
    # "q-Wert" next to "q-Wert (Storey)" can be a genuine distinction — the
    # decision belongs to the critic/rework, not to a deduplication.
    from src.unit.terminology import glossary_suspect as _gv
    _gl = [g.get("term") or "" for g in (unit.get("glossary") or [])
           if isinstance(g, dict)]
    for gi in range(len(_gl)):
        for gj in range(gi + 1, len(_gl)):
            reason = _gv(_gl[gi], _gl[gj])
            if reason:
                b.W(f"glossary({_gl[gi]})",
                    "possible glossary duplicate of '{v1}' ({reason}) — merge them or make the distinction explicit in the term", v1=_gl[gj], reason=reason)
    # Glossary completeness: every concept needs an entry. That is also the
    # condition for the hover explanation — a term without a definition cannot
    # have a tooltip.
    glossary = unit.get("glossary") or []
    # A glossary entry "Benjamini-Hochberg-Verfahren (BH-Verfahren)" must cover
    # the concept "… – mathematische Funktionsweise", although the concept name
    # does not contain the bracket form. So every entry counts with BOTH forms:
    # full and core (without the parenthetical addition) — the same rule as
    # everywhere in the terminology.
    from src.unit.terminology import core_term as _core_glossary
    present = set()
    for g in glossary:
        if not isinstance(g, dict):
            continue          # already reported as an error above
        beg = (g.get("term") or "").strip()
        for form in (beg, _core_glossary(beg)):
            if form:
                present.add(form.lower())
    def _covered(name: str) -> bool:
        n = name.lower()
        if n in present:
            return True
        # Concept names are descriptive phrases, glossary entries are terms.
        # "Xylem-Gefäße als Transportweg" counts as covered if "Xylem-Gefäße"
        # is in the glossary.
        return any(len(g) >= 5 and re.search(rf"(?<![\w-]){re.escape(g)}", n)
                   for g in present)

    def _is_term(name: str) -> bool:
        """Only term-like concept names need a glossary entry.

        Concept names are often descriptive phrases ("Erkennen fragwürdiger
        Ergebnisdarstellungen"). There can be no glossary entry for those —
        demanding one would only produce noise.
        """
        w = name.split()
        if len(w) > 4:
            return False
        # Verb forms and prepositions mark a description
        return not re.search(r"\b(und|oder|als|von|für|bei|zur|zum|mit|über|"
                             r"jenseits|zwischen|erkennen|verstehen|anwenden|"
                             r"interpretieren|unterscheiden|einordnen)\b",
                             name, re.I)

    for k in unit.get("concepts") or []:
        if not isinstance(k, dict):
            continue
        name = (k.get("name") or "").strip()
        if name and _is_term(name) and not _covered(name):
            b.W("glossary", "concept '{name}' ({v1}) has no glossary entry — without it there is no hover explanation", name=name, v1=k.get('id'))
    # A collective message instead of one warning per entry: with 69 glossary
    # terms, single messages would make 69 of 74 warnings and let every other
    # finding drown in them.
    without_short = [g.get("term") for g in glossary if isinstance(g, dict) if not (g.get("short") or "").strip()]
    if without_short:
        b.W("glossary", "{v1} of {v2} entries without a short field (e.g. {v3}) — the hover shows the full definition there", v1=len(without_short), v2=len(glossary), v3=', '.join(str(x) for x in without_short[:3]))
    too_long = [g.get("term") for g in glossary if isinstance(g, dict)
               if len((g.get("short") or "").strip()) > 300]
    if too_long:
        b.W("glossary", "{v1} short field(s) over 300 characters (e.g. {v2}) — too much for a hover", v1=len(too_long), v2=', '.join(str(x) for x in too_long[:3]))
    return b



# ─────────────────────────── Block checks ───────────────────────────

def _check_block(b: Finding, blk, P: str, node_probe: bool) -> None:
    if not isinstance(blk, dict) or not _is_str(blk.get("type")):
        b.F(P, "type missing")
        return
    type_ = blk["type"]
    fn = _CHECKERS.get(type_)
    if fn is None:
        b.F(P, "unknown block type '{type_}'", type_=type_)
        return
    # The HTML lead format applies only to HTML fields. In escaped fields — the
    # preformatted `material` of an error analysis, for instance — a dash list
    # is the RIGHT display; `<ul><li>` would appear literally there.
    for msg in _format_remnants(_visible_text(blk, html_only=True)):
        b.F(P, "{msg} — HTML is the lead format", msg=msg)
    # In escaped fields only LaTeX remains a genuine remnant: formulas belong
    # in a formula block there as well.
    escaped = _visible_text({k: v for k, v in blk.items()
                               if k in _ESCAPED_FIELDS})
    for pattern, msg in _LATEX_REST:
        if pattern.search(escaped):
            b.W(P, "{msg} (in an escaped field — hard to read there)", msg=msg)
    fn(b, blk, P, node_probe)


def _needs_description(b: Finding, blk: dict, P: str) -> None:
    if not _is_str(blk.get("description")):
        b.F(P, "description (alternative text) is required")
    elif len(blk["description"].strip()) < 20:
        b.W(P, "description very short — it should state the key message, not just the type")


def _p_text(b, blk, P, _):
    if not _is_str(blk.get("html")):
        b.F(P, "html missing")


def _p_note(b, blk, P, _):
    if not _is_str(blk.get("html")):
        b.F(P, "html missing")
    if blk.get("variant") not in ("key_point", "info", "warning"):
        b.W(P, "unknown variant '{v1}' (expected key_point|info|warning)", v1=blk.get('variant'))


def _p_table(b, blk, P, _):
    header = blk.get("header")
    if not isinstance(header, list) or not header:
        b.F(P, "header missing")
    rows = blk.get("rows")
    if not isinstance(rows, list) or not rows:
        b.F(P, "rows missing")
    for i, z in enumerate(rows or []):
        if not isinstance(z, list) or len(z) != len(header or []):
            b.F(f"{P}.rows[{i}]", "number of columns does not match the header")


def _p_accordion(b, blk, P, _):
    items = blk.get("items")
    if not isinstance(items, list) or not items:
        b.F(P, "items missing")
    for i, e in _objects(b, items, P, "items"):
        if not _is_str(e.get("title")):
            b.F(f"{P}.items[{i}]", "title missing")
        if not _is_str(e.get("html")):
            b.F(f"{P}.items[{i}]", "html missing")


def _p_code(b, blk, P, _):
    if not _is_str(blk.get("content")):
        b.F(P, "content missing")


def _p_quiz(b, blk, P, _):
    questions = blk.get("questions")
    if not isinstance(questions, list) or not questions:
        b.F(P, "questions missing")
    for i, f in _objects(b, questions, P, "questions"):
        Q = f"{P}.questions[{i}]"
        if not _is_str(f.get("question")):
            b.F(Q, "question missing")
        opt = f.get("options")
        if not isinstance(opt, list) or len(opt) < 2:
            b.F(Q, "at least 2 options required")
        correct_ones = sum(1 for o in (opt or [])
                       if isinstance(o, dict) and o.get("correct") is True)
        if correct_ones < 1:
            b.F(Q, "no correct option marked")
        if not f.get("multiple") and correct_ones > 1:
            b.F(Q, "{correct_ones} correct options, but multiple=false", correct_ones=correct_ones)
        if opt and correct_ones == len(opt):
            # Didactically pointless, but usable — does not block.
            b.W(Q, "all options are correct — the question checks nothing", code="checks_nothing")
        texts_ = [(o.get("text") or "").strip().lower() for o in (opt or [])
                 if isinstance(o, dict) and _is_str(o.get("text"))]
        duplicate = {t for t in texts_ if texts_.count(t) > 1}
        if duplicate:
            b.F(Q, "identical options ({v1}) — one of them cannot be answered", v1=', '.join(sorted(duplicate)[:2]))
        for oi, o in _objects(b, opt, Q, "options"):
            if not _is_str(o.get("text")):
                b.F(f"{Q}.options[{oi}]", "text missing")
            if not _is_str(o.get("feedback")):
                b.W(f"{Q}.options[{oi}]", "feedback missing — didactics criterion C3", code="no_feedback")


def _p_cloze(b, blk, P, _):
    html = blk.get("html")
    if not _is_str(html):
        b.F(P, "html missing")
    in_text = set(re.findall(r"\{\{(\w+)\}\}", html or ""))
    gaps = blk.get("gaps")
    if gaps is not None and not isinstance(gaps, dict):
        b.F(P, "gaps must be an object")
        gaps = {}
    defined = set((gaps or {}).keys())
    if not in_text:
        b.F(P, "no {{n}} placeholders in the html")
    for k in in_text - defined:
        b.F(P, "gap {{{{{k}}}}} in the text, but not defined in gaps", k=k)
    for k in defined:
        if k not in in_text:
            b.F(P, "gaps['{k}'] defined, but no placeholder in the text", k=k)
        l = (gaps or {}).get(k)
        if not isinstance(l, dict):
            b.F(P, "gaps['{k}'] is not an object", k=k)
            continue
        answers = l.get("answers")
        if not isinstance(answers, list) or not answers:
            b.F(P, "gaps['{k}'].answers missing", k=k)
            continue
        if any(not _is_str(a) or not a.strip() for a in answers):
            b.F(P, "gaps['{k}'].answers contains empty entries", k=k)
        # If the solution appears literally in the surrounding text, the gap
        # can be read off instead of recalled — the exercise then checks
        # nothing.
        sight = re.sub(r"<[^>]+>", " ", re.sub(r"\{\{\w+\}\}", " ", html or ""))
        for a in answers:
            if _is_str(a) and len(a.strip()) > 3 and re.search(
                    rf"(?<![\w-]){re.escape(a.strip())}(?![\w-])", sight, re.I):
                b.W(P, "solution '{v1}' appears literally in the surrounding text — the gap can be read off", code="cloze_readable", v1=a.strip())
                break


def _p_matching(b, blk, P, _):
    pairs = blk.get("pairs")
    if not isinstance(pairs, list) or len(pairs) < 2:
        b.F(P, "at least 2 pairs required")
    for i, p in _objects(b, pairs, P, "pairs"):
        if not (_is_str(p.get("left")) and _is_str(p.get("right"))):
            b.F(f"{P}.pairs[{i}]", "left/right missing")
    # Right values occurring several times are NOT an error but a
    # categorisation task: several statements, each to be assigned to one of a
    # few terms. Requiring uniqueness would forbid this didactically valuable
    # form and block the gate for no reason.
    right = [p.get("right") for p in (pairs or []) if isinstance(p, dict)]
    categories = len(set(right))
    if categories == 1 and len(right) > 1:
        b.F(P, "all pairs point to the same value — there is nothing to match")
    # Few target values for many statements are the normal case of this task
    # form; a message about it would appear in practically every case without
    # anything to do about it.
    left = [p.get("left") for p in (pairs or []) if isinstance(p, dict)]
    if len(set(left)) != len(left):
        b.F(P, "left values must be unique — two equal prompts with different solutions cannot be answered")
    for i, p in _objects(b, [x for x in (pairs or []) if isinstance(x, dict)], P, "pairs"):
        li, re_ = (p.get("left") or "").strip().lower(), (p.get("right") or "").strip().lower()
        if li and li == re_:
            b.W(f"{P}.pairs[{i}]", "left and right are identical — trivial pair", code="trivial_pair")


def _p_flashcards(b, blk, P, _):
    cards = blk.get("cards")
    if not isinstance(cards, list) or not cards:
        b.F(P, "cards missing")
    for i, k in _objects(b, cards, P, "cards"):
        if not (_is_str(k.get("front")) and _is_str(k.get("back"))):
            b.F(f"{P}.cards[{i}]", "front/back missing")
    front = [(k.get("front") or "").strip().lower() for k in (cards or [])
             if isinstance(k, dict) and _is_str(k.get("front"))]
    duplicate = {v for v in front if front.count(v) > 1}
    if duplicate:
        # Confusing, but usable — does not block.
        b.W(P, "duplicate front ({v1}) — the same question with two answers", code="duplicate_front", v1=', '.join(sorted(duplicate)[:2]))


def _chartjs_data(b, spec, P):
    """Checks whether the Chart.js data can be drawn at all.

    The most frequent error is not wrong syntax but the shifted series: five
    labels, four values — Chart.js draws that without complaint and assigns
    everything wrongly.
    """
    data_ = spec.get("data")
    if not isinstance(data_, dict):
        b.F(P, "chartjs spec without data")
        return
    labels = data_.get("labels")
    sets = data_.get("datasets")
    if not isinstance(sets, list) or not sets:
        b.F(P, "chartjs spec without datasets")
        return
    constant: list[int] = []
    for i, ds in enumerate(sets):
        if not isinstance(ds, dict):
            b.F(f"{P}.datasets[{i}]", "not an object")
            continue
        values = ds.get("data")
        if not isinstance(values, list) or not values:
            b.F(f"{P}.datasets[{i}]", "data missing or empty — empty chart")
            continue
        if isinstance(labels, list) and labels and len(values) != len(labels):
            b.F(f"{P}.datasets[{i}]",
                "{v1} values, but {v2} labels — the mapping shifts", v1=len(values), v2=len(labels))
        numbers = [w for w in values if isinstance(w, (int, float))]
        # A constant series NEXT TO a changing one is a reference line — the
        # threshold alpha = 0.05, for instance — and didactically exactly the
        # point. Only reported if ALL series are constant.
        if len(numbers) == len(values) and len(set(numbers)) == 1 and len(numbers) > 2:
            constant.append(i)

    if constant and len(constant) == len(sets):
        b.W(P, "all {v1} data series are constant — the chart shows no difference", v1=len(sets))


def _vega_fields(spec) -> set[str]:
    """Collects all field names available to a Vega-Lite spec."""
    names: set[str] = set()
    data_ = spec.get("data")
    if isinstance(data_, dict):
        for z in (data_.get("values") or [])[:50]:
            if isinstance(z, dict):
                names.update(z.keys())
        if isinstance(data_.get("sequence"), dict):
            names.add(data_["sequence"].get("as") or "data")
    # Von Transformationen erzeugte Felder
    def _collect(obj):
        if isinstance(obj, dict):
            # `fold` creates the fields "key" and "value" (or the pair in `as`)
            # — NOT the input fields listed. Without this there would be a
            # false alarm as soon as someone uses fold.
            if isinstance(obj.get("fold"), list):
                pair = obj.get("as")
                names.update(pair if isinstance(pair, list) and len(pair) == 2
                             else ["key", "value"])
            for key in ("as", "groupby", "fold", "flatten"):
                value = obj.get(key)
                if isinstance(value, str):
                    names.add(value)
                elif isinstance(value, list):
                    # update() instead of |= : the latter would bind `names` as
                    # local in this
                    # nested function.
                    names.update(x for x in value if isinstance(x, str))
            for w in obj.values():
                _collect(w)
        elif isinstance(obj, list):
            for w in obj:
                _collect(w)
    _collect(spec.get("transform"))
    _collect(spec.get("layer"))
    _collect(spec.get("spec"))
    return names


def _vega_views(spec, depth=0):
    """All views of a Vega-Lite spec, nested ones included.

    `vconcat`, `hconcat`, `layer`, `facet` and `repeat` move the encodings
    one level down. Checking only the top level would see no encoding at all
    in such specs — and miss exactly the errors that make them unusable.
    """
    if not isinstance(spec, dict) or depth > 5:
        return
    if isinstance(spec.get("encoding"), dict):
        yield spec
    for key in ("vconcat", "hconcat", "concat", "layer"):
        for part in spec.get(key) or []:
            yield from _vega_views(part, depth + 1)
    for key in ("spec", "facet", "repeat"):
        yield from _vega_views(spec.get(key), depth + 1)


# Channels that do without `type` because they carry only constant values.
_WITHOUT_TYPE = {"tooltip", "href", "description", "key", "order", "detail"}


def _vega_data(b, spec, P, params):
    """Checks data binding, type declarations and use of parameters."""
    data_ = spec.get("data")
    has_values = (isinstance(data_, dict)
                 and (data_.get("values") or data_.get("sequence") or data_.get("url")))
    views = list(_vega_views(spec))
    if not has_values and not views:
        b.F(P, "vegalite spec without data.values — the graphic stays empty")
    elif isinstance(data_, dict) and isinstance(data_.get("values"), list) \
            and not data_["values"]:
        b.F(P, "data.values is empty — the graphic stays empty")

    available = _vega_fields(spec)
    for view in views:
        for channel, e in (view.get("encoding") or {}).items():
            for part in (e if isinstance(e, list) else [e]):
                if not isinstance(part, dict):
                    continue
                # Missing type: Vega-Lite stops with 'Invalid field type
                # "undefined"' and
                # draws nothing.
                carries_data = part.get("field") is not None or part.get("datum") is not None
                if (carries_data and not part.get("type") and channel not in _WITHOUT_TYPE
                        and part.get("aggregate") != "count" and not part.get("timeUnit")):
                    kind = "field" if part.get("field") is not None else "datum"
                    b.F(P, "encoding.{channel} has {kind} without type — Vega-Lite needs quantitative, nominal, ordinal or temporal", channel=channel, kind=kind)
                field_ = part.get("field")
                param_names = {q.get("name") for q in (params or [])
                               if isinstance(q, dict)}
                if _is_str(field_) and field_ in param_names:
                    b.F(P, "encoding.{channel}.field '{field_}' is a PARAMETER, not a data field — addressed like this the graphic stays empty. For a parameter value use 'datum' with expr or bind it in a transform", channel=channel, field_=field_)
                elif (_is_str(field_) and available and field_ not in available
                        and part.get("aggregate") != "count"):
                    b.W(P, "encoding.{channel}.field '{field_}' does not occur in the data (present: {v1})", code="field_not_in_data", channel=channel, field_=field_, v1=', '.join(sorted(available)[:6]))

    if not params:
        return
    names = {p.get("name") for p in params if isinstance(p, dict) and p.get("name")}
    without = dict(spec)
    without.pop("params", None)
    raw = json.dumps(without, ensure_ascii=False)
    for name in names:
        if not re.search(rf"\b{re.escape(name)}\b", raw):
            b.F(P, "params['{name}'] is used nowhere — the control appears but does nothing", name=name)
        # A parameter is NOT a data field. "datum.sd" is undefined; the graphic
        # then stays empty without Vega-Lite reporting anything.
        if re.search(rf"datum{re.escape('.')}{re.escape(name)}\b", raw):
            b.F(P, "params['{name}'] is addressed as 'datum.{v1}' — a parameter is not a data field. Correct is '{v2}' alone; otherwise the graphic stays empty", name=name, v1=name, v2=name)



def _p_chart(b, blk, P, _):
    _needs_description(b, blk, P)
    if blk.get("engine") not in ("chartjs", "vegalite"):
        b.F(P, "engine '{v1}' unknown (chartjs|vegalite)", v1=blk.get('engine'))
    spec = blk.get("spec")
    if not isinstance(spec, dict):
        b.F(P, "spec missing")
        return
    if blk.get("engine") == "chartjs":
        if not _is_str(spec.get("type")):
            b.F(P, "chartjs spec without type")
        _chartjs_data(b, spec, P)
        return

    raw = json.dumps(spec, ensure_ascii=False)
    if re.search(r'"url"\s*:', raw):
        b.W(P, "vegalite spec references a URL — the unit must work offline; put the data inline under data.values")
    # Vega-Lite knows no free signals; if "signal" appears, full Vega was
    # written. That does not render and is also more attack surface.
    if '"signal"' in raw:
        b.F(P, "vegalite spec contains \"signal\" — that is Vega syntax, not Vega-Lite; express it as params/bind")

    params = spec.get("params")
    if params is not None and not isinstance(params, list):
        b.F(P, "params must be a list")
        params = None
    for i, prm in enumerate(params or []):
        if not isinstance(prm, dict):
            b.F(P, "params[{i}] is not an object", i=i)
            continue
        if not _is_str(prm.get("name")):
            b.F(P, "params[{i}] without name — no transformation can refer to a parameter without a name", i=i)
        # A bound control without a value starts empty: the slider is at its
        # stop and the graphic is empty until the first use.
        if prm.get("bind") is not None and "value" not in prm:
            b.F(P, "params[{i}]('{v1}') is bound but has no value — the graphic starts empty", i=i, v1=prm.get('name'))
        bind = prm.get("bind")
        if isinstance(bind, dict):
            if bind.get("input") == "range" and not all(
                    k in bind for k in ("min", "max")):
                b.W(P, "params[{i}]('{v1}'): range binding without min/max — Vega guesses the limits", i=i, v1=prm.get('name'))
            if bind.get("input") == "select" and not bind.get("options"):
                b.F(P, "params[{i}]('{v1}'): select binding without options", i=i, v1=prm.get('name'))
            if not bind.get("name"):
                b.W(P, "params[{i}]('{v1}'): binding without name — the control then carries the technical identifier", code="binding_without_name", i=i, v1=prm.get('name'))
    if params:
        # Analogous to didactics criterion D2 (simulator): an exploration needs
        # a task, not only the possibility to slide. The pattern accepts the
        # informal and the formal imperative ("stelle"/"beobachte" and "Stellen
        # Sie … ein und beobachten Sie …"), the infinitive and English verbs
        # (units in other languages).
        descr = (blk.get("description") or "")
        if not re.search(
                r"\b(stell|setz|vergleich|beobacht|verschieb|wähl|prüf|erhöh|"
                r"verringer|klick|variier|justier|probier|untersuch|änder)"
                r"(?:e|en|n)?\b"
                r"|\b(set|adjust|observe|compare|explore|move|drag|increase|"
                r"decrease|choose|select|watch|vary|try|change|slide|toggle)\b",
                descr, re.I):
            b.W(P, "interactive graphic: description names no exploration task (\"Set X to …, observe Y\") — criterion D2", code="no_exploration_task")
    _vega_data(b, spec, P, params or [])


def _p_diagram(b, blk, P, node_probe):
    _needs_description(b, blk, P)
    if not _is_str(blk.get("code")):
        b.F(P, "code (Mermaid) missing")
        return
    # Type and minimal structure. A flowchart without edges or a pie without
    # values passes the syntax probe and still shows the learner nothing.
    type_ = dtype.detect(blk["code"])
    if type_ is None:
        b.F(P, "diagram type not recognised — the source must begin with a Mermaid keyword ({v1} …)", v1=', '.join(list(dtype.TYPES)[:5]))
        return
    shortcoming = dtype.structure_finding(blk["code"])
    if shortcoming:
        b.F(P, "{type_}: {shortcoming}", type_=type_, shortcoming=Msg(shortcoming))
    if not node_probe:
        return
    res = _mermaid_probe([blk["code"]])
    if res is None:
        # Do not report per diagram: a checker that cannot run is a problem of
        # the ENVIRONMENT and affects the whole unit equally. With 13 diagrams,
        # single messages would make 13 of 19 warnings and let the findings on
        # content vanish next to them.
        b.unchecked.append(P)
        if not b.probe_reason:
            b.probe_reason = _probe_reason.get('mermaid', '')
        return
    if res and not res[0].get("ok"):
        b.F(P, "Mermaid syntax error: {v1}", v1=res[0].get('errors', 'unbekannt'))


def _p_formula(b, blk, P, _):
    _needs_description(b, blk, P)
    latex = blk.get("latex")
    if not _is_str(latex):
        b.F(P, "latex missing")
        return
    if blk.get("display") not in (None, "inline", "block"):
        b.W(P, "unknown display '{v1}' (inline|block)", v1=blk.get('display'))
    # The normalisation sets `html`; if it is missing, the block was not passed
    # through — then the learner sees raw LaTeX.
    html = blk.get("html")
    if not _is_str(html):
        b.F(P, "html missing — the formula was not translated into a display (src.unit.normalization)")
    elif "formula-raw" in html:
        b.F(P, "the formula could not be displayed (neither simple notation nor MathML) — simplify the LaTeX or provide KaTeX")


def _p_prediction(b, blk, P, _):
    if not _is_str(blk.get("question")):
        b.F(P, "question missing")
    if not _is_str(blk.get("resolution")):
        b.F(P, "resolution missing")
    if blk.get("options") is not None:
        opt = blk["options"]
        if not isinstance(opt, list) or len(opt) < 2:
            b.F(P, "options: at least 2, or leave them out entirely (then a free-text commitment)")
        for oi, o in _objects(b, opt, P, "options"):
            if not _is_str(o.get("text")):
                b.F(f"{P}.options[{oi}]", "text missing")


def _p_task(b, blk, P, _):
    if not _is_str(blk.get("task")):
        b.F(P, "task missing")
    if not _is_str(blk.get("sample_solution")):
        b.F(P, "sample_solution missing")
    for hi, h in enumerate(blk.get("hints") or []):
        if not _is_str(h):
            b.F(f"{P}.hints[{hi}]", "empty")


def _p_error_analysis(b, blk, P, _):
    if not _is_str(blk.get("material")):
        b.F(P, "material missing")
    if not _is_str(blk.get("question")):
        b.F(P, "question missing")
    if not _is_str(blk.get("sample_solution")):
        b.F(P, "sample_solution missing")


def _p_widget(b, blk, P, _):
    _needs_description(b, blk, P)
    if not _is_str(blk.get("html")):
        b.F(P, "html missing")
    elif not re.match(r"^\s*<!DOCTYPE", blk["html"], re.I):
        b.F(P, "widget.html must be a complete HTML document (<!DOCTYPE …)")
    if re.search(r'\s(src|href)\s*=\s*["\']https?:', blk.get("html") or "", re.I):
        b.F(P, "widget loads external resources — forbidden (offline, sandbox without network)")
    b.W(P, "level 4 in use — justification in the detail plan and a smoke test required")


def _p_simulator(b, blk, P, node_probe):
    _needs_description(b, blk, P)
    parameter = blk.get("parameters")
    if not isinstance(parameter, list) or not parameter:
        b.F(P, "parameters missing")
    for i, p in _objects(b, parameter, P, "parameters"):
        Q = f"{P}.parameters[{i}]"
        if not _is_str(p.get("name")):
            b.F(Q, "name missing")
        if not _is_str(p.get("label")):
            b.F(Q, "label missing")
        for k in ("min", "max", "value"):
            if not isinstance(p.get(k), (int, float)) or isinstance(p.get(k), bool):
                b.F(Q, "{k} missing/not a number", k=k)
        if isinstance(p.get("min"), (int, float)) and isinstance(p.get("max"), (int, float)) and p["min"] >= p["max"]:
            b.F(Q, "min >= max")
    code = blk.get("code")
    if not _is_str(code):
        b.F(P, "code missing")
        return
    for forbidden in FORBIDDEN_IN_SIM:
        if forbidden in code:
            b.F(P, "code uses '{forbidden}' — level 3 contract: a pure function without environment", forbidden=forbidden)
    if not node_probe:
        return
    standard = {p["name"]: p["value"] for p in parameter or [] if _is_str(p.get("name"))}
    runs = [
        ("Default", standard),
        ("Min", {p["name"]: p["min"] for p in parameter or [] if _is_str(p.get("name"))}),
        ("Max", {p["name"]: p["max"] for p in parameter or [] if _is_str(p.get("name"))}),
    ]
    # ONE run each with only this slider at its stop: only like that can it be
    # determined whether a single control has any effect at all. A slider
    # without effect is structurally free of errors and is otherwise only
    # noticed by the learner who moves it in vain.
    for p in parameter or []:
        if _is_str(p.get("name")) and isinstance(p.get("max"), (int, float)):
            runs.append((f"only:{p['name']}", {**standard, p["name"]: p["max"]}))
    result = _sim_probe(code, runs)
    if result is None:
        b.W(P, "trial run skipped (Node.js not found) — static check only")
        return
    if "fatal" in result:
        if result["fatal"].startswith("code not evaluable"):
            b.F(P, "code not evaluable: {detail}", detail=result["fatal"].split(": ", 1)[-1])
        elif result["fatal"] == "code is not a function":
            b.F(P, "code is not a function")
        else:
            b.F(P, "simulator probe failed: {detail}", detail=result["fatal"])
        return
    for run in result.get("runs", []):
        name = run.get("name")
        if not run.get("ok"):
            b.F(P, "trial run ({name}) fails: {v1}", name=name, v1=run.get('errors'))
            continue
        if run.get("ms", 0) > 100:
            b.W(P, "trial run ({name}) takes {v1} ms — target budget ~50 ms", name=name, v1=run['ms'])
        # A frequent mistake: model(p) returns x:[0] with ONE value per series
        # — the single value of the current slider position instead of a curve.
        # Drawn as a line that lies as a single point on the left of the axis
        # and looks broken.
        if name == "Default":
            kind = str((blk.get("output") or {}).get("kind") or "line").lower()
            if kind in ("line", "flaeche", "line", "area") and 0 < run.get("xLen", 0) < 5:
                b.W(P, "output has only {v1} data point(s) — as '{kind}' that sits as a dot at the left edge of the axis. modell(p) should return a CURVE: run x over a range of values (sweep) instead of returning the single value for the current slider position", v1=run['xLen'], kind=kind)
        if not run.get("form"):
            b.F(P, "output form ({name}) invalid — expected {{x:[], series:[{{name,values}}]}}", name=name)
            continue
        for si, s in enumerate(run.get("series", [])):
            if s.get("len") != run.get("xLen"):
                b.F(P, "series[{si}].values ({name}) not as long as x", si=si, name=name)
            if not _is_str(s.get("name")):
                b.W(P, "series[{si}].name missing", si=si)
            if name != "Default":
                continue
            # A series that is 0 throughout lies invisibly on the axis — the
            # learner sees nothing and takes it for broken.
            if s.get("finite") and s.get("min") == 0 and s.get("max") == 0:
                b.W(P, "series '{v1}' is 0 throughout — it lies invisibly on the axis", v1=s.get('name') or si)
            if s.get("len", 0) > 0 and s.get("finite", 0) < s["len"]:
                b.W(P, "series '{v1}': {v2} of {v3} values are NaN or infinite — the curve breaks off there", v1=s.get('name') or si, v2=s['len'] - s['finite'], v3=s['len'])
        if run.get("xLen", 0) > 5000:
            b.W(P, "output ({name}) has {v1} points — thin it out for display", name=name, v1=run['xLen'])

    # Effect of every single slider
    sig = {l.get("name"): l.get("signature") for l in result.get("runs", [])
           if l.get("ok")}
    names = {p["name"]: p.get("label") or p["name"] for p in parameter or []
             if _is_str(p.get("name"))}
    for pname, label in names.items():
        own = sig.get(f"only:{pname}")
        if own and sig.get("Default") and own == sig["Default"]:
            b.W(P, "slider '{label}' changes nothing in the output — a control without effect is misleading", label=label)

    # Slider and x axis with the same label: then the chart usually already
    # shows what the slider is meant to set.
    x_label = str((blk.get("output") or {}).get("x_label") or "").strip().lower()
    for pname, label in names.items():
        lab = str(label).strip().lower()
        if x_label and lab and (x_label in lab or lab in x_label):
            b.W(P, "slider '{label}' has the same label as the x axis — the chart probably already shows what it is meant to set", label=label)


_SANDBOX_FLAGS: dict[str, list[str]] = {}


def _node_sandbox_flags(node: str) -> list[str]:
    """Flags of the Node permission model, as far as the installed version knows
    them.

    Second layer behind the context separation in sim_probe.mjs: should an
    escape succeed nevertheless, Node refuses write access, child processes
    and workers. Node 22 knows `--permission`, Node 20
    `--experimental-permission`, Node 18 neither — then the context
    separation remains. The result is determined once per Node path.
    """
    if node in _SANDBOX_FLAGS:
        return _SANDBOX_FLAGS[node]
    read = f"--allow-fs-read={_ASSETS}"
    found: list[str] = []
    for flag in ("--permission", "--experimental-permission"):
        try:
            r = subprocess.run([node, flag, read, "-e", "0"],
                               capture_output=True, timeout=10)
        except (subprocess.TimeoutExpired, OSError):
            break
        if r.returncode == 0:
            found = [flag, read]
            break
    _SANDBOX_FLAGS[node] = found
    return found


def _sim_probe(code: str, runs: list) -> dict | None:
    """Runs the simulator function through the Node runner. None = Node missing."""
    node = shutil.which("node")
    if node is None:
        return None
    try:
        proc = subprocess.run(
            [node, *_node_sandbox_flags(node), str(_ASSETS / "sim_probe.mjs")],
            input=json.dumps({"code": code, "runs": runs}),
            capture_output=True, text=True, timeout=10,
        )
        return json.loads(proc.stdout.strip() or "{}")
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as e:
        return {"fatal": f"trial run failed: {e}"}


def _mermaid_probe(diagrams: list[str]) -> list[dict] | None:
    """Parses Mermaid source against the embedded Mermaid version.

    None = Node or Mermaid not available (then it warns instead of checking,
    as with the simulator probe).
    """
    node = shutil.which("node")
    if node is None or not (_ASSETS / "mermaid_probe.mjs").exists():
        return None
    try:
        proc = subprocess.run(
            [node, str(_ASSETS / "mermaid_probe.mjs")],
            input=json.dumps({"diagrams": diagrams}),
            capture_output=True, text=True, timeout=30,
        )
        data_ = json.loads(proc.stdout.strip() or "{}")
        if data_.get("fatal"):
            # Remember the reason: without it the validator would report "Node
            # or Mermaid missing" across the board, even if in truth jsdom is
            # missing or DOMPurify cannot be initialised. Troubleshooting would
            # then lead nowhere.
            _probe_reason["mermaid"] = str(data_["fatal"])[:200]
            return None
        _probe_reason.pop("mermaid", None)
        return data_.get("results")
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as e:
        _probe_reason["mermaid"] = f"{type(e).__name__}: {e}"[:200]
        return None


# Last known reason of failure per probe — for the warning and the start-up
# diagnosis. Shared process-wide — acceptable here, because a probe that
# cannot run is a PROPERTY OF THE ENVIRONMENT and not of the job: in parallel
# runs all fail for the same reason. Only the reason is written, never a
# finding.
_probe_reason: dict[str, str] = {}


def probe_diagnose() -> dict[str, str]:
    """State of the Node probes, for the application's start-up diagnosis."""
    result = {}
    if shutil.which("node") is None:
        return {"node": "not found — all Node probes are skipped"}
    m = _mermaid_probe(["flowchart LR\n A-->B"])
    result["mermaid"] = ("operational" if m and m[0].get("ok")
                           else _probe_reason.get("mermaid", "cannot run"))
    try:
        from src.unit.normalization import katex_present
        result["katex"] = ("operational" if katex_present()
                             else "not installed — formulas in simple notation only")
    except Exception as e:  # noqa: BLE001
        result["katex"] = f"cannot be checked: {e}"
    return result


_CHECKERS = {
    "text": _p_text, "note": _p_note, "table": _p_table,
    "accordion": _p_accordion, "code": _p_code, "quiz": _p_quiz,
    "cloze": _p_cloze, "matching": _p_matching,
    "flashcards": _p_flashcards, "chart": _p_chart, "diagram": _p_diagram,
    "simulator": _p_simulator, "widget": _p_widget, "formula": _p_formula,
    "prediction": _p_prediction, "task": _p_task, "error_analysis": _p_error_analysis,
}


def validate_file(path_: str | Path, node_probe: bool = True) -> Finding:
    try:
        unit = json.loads(Path(path_).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        b = Finding()
        b.F("file", "JSON not readable: {e}", e=e)
        return b
    return validate(unit, node_probe=node_probe)


def check_lesson(lesson: dict, node_probe: bool = True,
                   language: str | None = None) -> Finding:
    """Checks ONE lesson (basic fields + all blocks) — the basis of the
    pipeline's repair loop: format errors are closed where they arise
    instead of piling up at the final gate. If `language` (de/en) is set,
    language mixing (CJK) counts as an ERROR and so triggers the repair."""
    b = Finding()
    P = f"lesson({lesson.get('id', '?')})"
    if (language or "").lower() in ("de", "en"):
        n, probe = _foreign_chars(json.dumps(lesson, ensure_ascii=False))
        if n:
            b.F(P, "contains {n} CJK characters (e.g. '{probe}') — mixed languages, keep all texts in '{language}'", n=n, probe=probe, language=language)
    if not _is_str(lesson.get("title")):
        b.F(P, "title missing")
    blocks = lesson.get("blocks")
    if not isinstance(blocks, list) or not blocks:
        b.F(P, "no blocks")
        return b
    for bi, blk in enumerate(blocks):
        _check_block(b, blk, f"{P}.block[{bi}]", node_probe)
    if not any(isinstance(x, dict) and x.get("type") in SELF_CHECK for x in blocks):
        b.W(P, "no self-check (quiz/cloze/matching) — didactics criterion C1")
    return b


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Aufruf: python -m src.unit.validator <unit.json>")
        sys.exit(1)
    finding = validate_file(sys.argv[1])
    print(finding.report())
    sys.exit(0 if finding.passed else 1)
