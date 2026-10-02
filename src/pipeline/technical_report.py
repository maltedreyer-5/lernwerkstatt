# -*- coding: utf-8 -*-
"""Technical report on a finished production.

Answers two questions that otherwise only show scattered in the logs: what
did the run cost, and what came out of it.

The usage figures come from the LLM clients (`total_calls`,
`total_input_tokens`, `total_output_tokens`); the content summary is
counted from the finished unit, not carried along — so it cannot diverge
from reality.
"""
from __future__ import annotations

import json

from src.i18n import N_, Msg, render, tr
import re
from collections import Counter

# Grouping of block types for the summary.
GROUPS = {
    N_("Display"): ["diagram", "chart", "table", "formula", "code"],
    N_("Interaction"): ["quiz", "cloze", "matching", "flashcards",
                    "prediction", "simulator", "widget"],
    N_("Text"): ["text", "note", "accordion"],
    N_("Tasks"): ["task", "error_analysis"],
}
LABELS = {
    "text": N_("text blocks"), "note": N_("callouts"), "accordion": N_("accordions"),
    "table": N_("tables"), "diagram": N_("diagrams (Mermaid)"), "chart": N_("charts"),
    "formula": N_("formulas"), "code": N_("code blocks"), "quiz": N_("quizzes"),
    "cloze": N_("cloze texts"), "matching": N_("matching exercises"),
    "flashcards": N_("flashcard sets"), "prediction": N_("predictions"),
    "simulator": N_("simulators"), "widget": N_("widgets"),
    "task": N_("tasks"), "error_analysis": N_("error analyses"),
}
ROLE_LABEL = {"strong": N_("strong"), "fast": N_("fast")}


def _words(html: str) -> int:
    return len(re.sub(r"<[^>]+>", " ", html or "").split())


def _blocks(unit: dict):
    for l in unit.get("lessons") or []:
        for b in l.get("blocks") or []:
            if isinstance(b, dict):
                yield b
    for m in unit.get("modules") or []:
        for b in m.get("exercises") or []:
            if isinstance(b, dict):
                yield b


def _material_mode(pipeline) -> dict:
    """How was the uploaded material actually used?

    Without this line it would go unnoticed that an embedder failure
    reduced the material to mere excerpts.
    """
    full_text = getattr(pipeline, "material_full_text", "") or ""
    if not full_text:
        return {}
    index = getattr(pipeline, "inventory_index", None)
    entries = len(getattr(index, "_entries", None) or []) if index else 0
    return {
        N_("Material size (characters)"): len(full_text),
        N_("Use of material"): (Msg("indexed in {n} segments", {"n": entries}) if entries
                                else Msg("as excerpts only (no embedder index)")),
    }


def _coverage_metrics(ab: dict) -> dict:
    """Material coverage figures for the technical report."""
    entries = ab.get("coverage") or []
    if not entries:
        return {}
    evidenced = sum(1 for a in entries if getattr(a, "evidenced", False))
    return {
        N_("Concepts with evidence in the material"): Msg("{n} of {total}", {"n": evidenced, "total": len(entries)}),
        N_("Concepts from model knowledge"): len(entries) - evidenced,
        N_("Material segments without a concept"): len(ab.get("orphaned") or []),
        N_("Relevance confirmed by reranker"): Msg("yes") if ab.get("reranker") else Msg("no"),
    }


def collect(unit: dict, pipeline=None) -> dict:
    """Collects all figures."""
    types_ = Counter(b.get("type") for b in _blocks(unit))
    lessons = unit.get("lessons") or []
    words = sum(_words(b.get("html", "")) for b in _blocks(unit)
                  if b.get("type") in ("text", "note"))

    classes = Counter(k.get("concept_class") for k in (unit.get("concepts") or []))
    interactive = sum(types_[t] for t in GROUPS["Interaction"])
    display = sum(types_[t] for t in GROUPS["Display"])
    # For "words per interaction" numerator and denominator must refer to the
    # same set: the words come from the lessons, so only lesson interactions
    # are counted here — not the predictions of the application part, which
    # would skew the figure downwards.
    interactive_lesson = sum(
        1 for l in lessons for b_ in (l.get("blocks") or [])
        if isinstance(b_, dict) and b_.get("type") in GROUPS["Interaction"])
    # Tasks/error analyses IN lessons are activity as well — without them the
    # interaction count misses lessons that carry them.
    task_lesson = sum(
        1 for l in lessons for b_ in (l.get("blocks") or [])
        if isinstance(b_, dict) and b_.get("type") in GROUPS["Tasks"])

    data_ = {
        "content": {
            N_("Chapters"): len({l.get("chapters") for l in lessons if l.get("chapters")})
                       or len(unit.get("modules") or []) or None,
            N_("Lessons"): len(lessons),
            N_("Blocks in total"): sum(types_.values()),
            N_("Words of reading text"): words,
            N_("Concepts"): len(unit.get("concepts") or []),
            N_("Glossary entries"): len(unit.get("glossary") or []),
            N_("Learning objectives"): len(unit.get("learning_objectives") or []),
            N_("Estimated duration (min)"): unit.get("duration_minutes"),
        },
        "types": types_,
        "classes": classes,
        "ratios": {
            N_("Displays"): display,
            N_("Interactions"): interactive,
            N_("of which in lessons"): interactive_lesson,
            N_("Tasks/error analyses in lessons"): task_lesson,
            N_("Share of non-text blocks"): (
                f"{100 * (display + interactive) / max(sum(types_.values()), 1):.0f} %"),
            N_("Words per interaction (lessons)"): (
                f"{words // interactive_lesson}" if interactive_lesson else "—"),
        },
        "per_lesson": [
            {
                "id": l.get("id"),
                "words": sum(_words(b.get("html", ""))
                               for b in (l.get("blocks") or [])
                               if isinstance(b, dict) and b.get("type") in ("text", "note")),
                "display": sum(1 for b in (l.get("blocks") or [])
                                   if isinstance(b, dict)
                                   and b.get("type") in GROUPS["Display"]),
                "interaction": sum(1 for b in (l.get("blocks") or [])
                                   if isinstance(b, dict)
                                   and b.get("type") in GROUPS["Interaction"]),
                "tasks": sum(1 for b in (l.get("blocks") or [])
                                if isinstance(b, dict)
                                and b.get("type") in GROUPS["Tasks"]),
            }
            for l in lessons
        ],
        "llm": [],
        "history": {},
    }

    if pipeline is not None:
        seen = set()
        for label, client in (("strong", getattr(pipeline, "llm", None)),
                              ("fast", getattr(pipeline, "llm_fast", None))):
            if client is None or id(client) in seen:
                continue
            seen.add(id(client))
            data_["llm"].append({
                "role": label,
                "model": getattr(client, "model", "?"),
                "calls": getattr(client, "total_calls", 0),
                "input": getattr(client, "total_input_tokens", 0),
                "output": getattr(client, "total_output_tokens", 0),
                "truncated": getattr(client, "total_truncated", 0),
                "empty": getattr(client, "total_empty", 0),
                "rescued": getattr(client, "total_empty_rescued", 0),
            })
        term = getattr(pipeline, "terminology", None)
        scores = getattr(pipeline, "critic_scores", {}) or {}
        data_["history"] = {
            N_("Lost lessons"): len(getattr(pipeline, "losses", []) or []),
            N_("Downgraded blocks"): len(getattr(pipeline, "degradations", []) or []),
            N_("Blocks added by enrichment"): getattr(pipeline, "enriched", 0),
            N_("Proposed by enrichment, but discarded"): getattr(
                pipeline, "enrichment_discarded", 0),
            # Critics can rate ALL lessons 1-3 — the distribution belongs
            # visibly in the report, otherwise strictness of the rubric cannot
            # be told apart from quality of generation.
            N_("Critic scores (per lesson)"): ", ".join(
                f"{k}: {v}" for k, v in scores.items()) or "—",
            N_("Fixed technical terms"): len(getattr(term, "fixed_terms", {}) or {}),
            N_("Open term candidates"): len(term.open_candidates()) if term else 0,
            N_("Replaced coinages"): len(getattr(term, "blocklist", {}) or {}),
            N_("Teaching script nodes"): len(getattr(getattr(pipeline, "teaching_script", None),
                                             "nodes", {}) or {}),
            **_material_mode(pipeline),
            **_coverage_metrics(getattr(pipeline, "coverage", {}) or {}),
        }
    return data_


def as_markdown(data_: dict, lang: str | None = None) -> str:
    t = lambda text, **kw: tr(text, lang, **kw)          # noqa: E731
    r = lambda value: render(value, lang)                # noqa: E731
    z = [t("### Technical report"), ""]
    if data_.get("from_saved_run"):
        z += [t("_Usage figures from the original production run (this process only loaded "
                "the unit)._"), ""]

    if data_["llm"]:
        z += [t("**Model usage**"), "",
              t("| Role | Model | Calls | Input tokens | Output tokens | truncated | empty |"),
              "|---|---|---:|---:|---:|---:|---:|"]
        s_c = s_e = s_a = 0
        for m in data_["llm"]:
            role = t(ROLE_LABEL.get(m["role"], m["role"]))
            z.append(f"| {role} | `{m['model']}` | {m['calls']} | "
                     f"{m['input']:,} | {m['output']:,} | "
                     f"{m.get('truncated', 0)} | {m.get('empty', 0)} |")
            s_c += m["calls"]; s_e += m["input"]; s_a += m["output"]
        s_t = sum(m.get("truncated", 0) for m in data_["llm"])
        s_l = sum(m.get("empty", 0) for m in data_["llm"])
        z.append(f"| **{t('Total')}** | | **{s_c}** | **{s_e:,}** | **{s_a:,}** | "
                 f"**{s_t}** | **{s_l}** |")
        s_g = sum(m.get("rescued", 0) for m in data_["llm"])
        if s_g:
            z += ["", t("{n} empty answer(s) rescued by a retry without thinking — JSON mode "
                        "and thinking do not work together on this endpoint.", n=s_g)]
        if s_t:
            z += ["", t("⚠️ {n} answer(s) cut off at the budget", n=s_t)
                  + (t(", {n} of them completely empty — the budget went into thinking. A "
                       "higher budget does NOT help then; set BLOCKS_THINKING=false or "
                       "LLM_REASONING_EFFORT_OFF.", n=s_l)
                     if s_l else t(". Adjust with BLOCKS_MAX_TOKENS."))]
        z += ["", t("Tokens in total: **{n}**", n=f"{s_e + s_a:,}"), ""]

    z += [t("**Scope**"), ""]
    for k, v in data_["content"].items():
        if v is not None:
            z.append(f"- {t(k)}: **{r(v)}**")
    z.append("")

    z += [t("**Components**"), ""]
    for group, types_ in GROUPS.items():
        parts = [f"{t(LABELS.get(x, x))} {data_['types'][x]}"
                 for x in types_ if data_["types"][x]]
        if parts:
            z.append(f"- {t(group)}: " + ", ".join(parts))
    z.append("")

    z += [t("**Density**"), ""]
    for k, v in data_["ratios"].items():
        z.append(f"- {t(k)}: **{r(v)}**")
    z.append("")

    if data_["classes"]:
        cl = ", ".join(f"{k}: {v}" for k, v in sorted(data_["classes"].items()) if k)
        z += [t("**Concept classes** — {classes}", classes=cl), ""]

    if data_["per_lesson"]:
        z += [t("**Per lesson**"), "",
              t("| Lesson | Words | Displays | Interactions | Tasks |"),
              "|---|---:|---:|---:|---:|"]
        for l in data_["per_lesson"]:
            z.append(f"| {l['id']} | {l['words']} | {l['display']} "
                     f"| {l['interaction']} | {l.get('tasks', 0)} |")
        z.append("")

    if data_["history"]:
        z += [t("**Production**"), ""]
        for k, v in data_["history"].items():
            z.append(f"- {t(k)}: **{r(v)}**")
        z.append("")
    return "\n".join(z)


def report(unit: dict, pipeline=None, lang: str | None = None) -> tuple[str, dict]:
    """Returns (Markdown for the interface, raw data for the file)."""
    data_ = collect(unit, pipeline)
    return as_markdown(data_, lang), data_


def as_json(data_: dict) -> str:
    copy_ = dict(data_)
    copy_.pop("from_saved_run", None)
    copy_["types"] = dict(data_["types"])
    copy_["classes"] = {k: v for k, v in data_["classes"].items() if k}
    # Msg values (such as "3 of 5") are written as English text.
    return json.dumps(copy_, ensure_ascii=False, indent=1, default=str)
