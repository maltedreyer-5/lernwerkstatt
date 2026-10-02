# -*- coding: utf-8 -*-
"""Teaching script: the overarching guiding document of the learning unit.

Why it is needed. The detail plan prompt sees a single chapter, the script
phase a single concept, the cross context at most 300 words about all
previous chapters. Every context is local or backward-looking and heavily
compressed; nothing is global, nothing looks ahead.

The result without it is meandering: no section can know that a topic
comes in detail later — so it anticipates it whenever it fits. And because
the concept authors write in parallel and without seeing each other, each
one would introduce the same foundations again, each time worded a little
differently.

The teaching script answers three questions:
  1. What is the arc? (common thread per chapter)
  2. Where is each concept INTRODUCED — and where only resumed?
  3. What does it build on? (dependency graph)

From 2 and 3 every section gets a precise brief: "The reader knows A, B,
C. You introduce D. E and F come later — do not anticipate them."
"""
from __future__ import annotations

from dataclasses import dataclass, field

from src.i18n import Msg, render, tr


@dataclass
class Node:
    """A concept in the teaching script."""
    id: str
    introduction: str = ""              # lesson ID where it is introduced
    requires: list[str] = field(default_factory=list)
    resumption: list[str] = field(default_factory=list)
    contribution: str = ""                  # what it contributes to the arc (1 sentence)

    def to_dict(self) -> dict:
        return {"id": self.id, "introduction": self.introduction,
                "requires": self.requires,
                "resumption": self.resumption, "contribution": self.contribution}


@dataclass
class TeachingScript:
    common_thread: list[str] = field(default_factory=list)   # one sentence per chapter
    nodes: dict[str, Node] = field(default_factory=dict)
    guiding_question: str = ""

    # ── Derived views ───────────────────────────────────────────────────────

    def sequence_order(self) -> list[str]:
        """Topological order of the concepts (stable, cycles at the end)."""
        open_ = dict(self.nodes)
        done: list[str] = []
        while open_:
            free = [cid for cid, k in open_.items()
                    if all(v in done or v not in self.nodes for v in k.requires)]
            if not free:                       # cycle: the rest in input order
                done += list(open_)
                break
            for cid in free:
                done.append(cid)
                open_.pop(cid)
        return done

    def cycles(self) -> list[list[str]]:
        """Finds dependency cycles (k1 requires k2 and vice versa)."""
        found, path_, visited = [], [], set()

        def run(cid, chain):
            if cid in chain:
                found.append(chain[chain.index(cid):] + [cid])
                return
            if cid in visited or cid not in self.nodes:
                return
            for v in self.nodes[cid].requires:
                run(v, chain + [cid])
            visited.add(cid)

        for cid in self.nodes:
            run(cid, [])
        # Remove duplicates (the same cycle, a different starting corner)
        once_only, seen = [], set()
        for z in found:
            sig = frozenset(z)
            if sig not in seen:
                seen.add(sig)
                once_only.append(z)
        return once_only

    def known_before(self, concept_id: str) -> list[str]:
        """Concepts introduced before this one (transitive closure)."""
        order = self.sequence_order()
        if concept_id not in order:
            return []
        return order[:order.index(concept_id)]

    def later_than(self, concept_id: str) -> list[str]:
        order = self.sequence_order()
        if concept_id not in order:
            return []
        return order[order.index(concept_id) + 1:]

    # ── Brief per section ──────────────────────────────────────────────

    def job(self, concept_id: str, names: dict[str, str]) -> str:
        """The context block a concept author receives.

        Resolves two causes of meandering at once: ownership (only the
        introducing section may explain) and the missing view ahead (what
        comes later is not anticipated).
        """
        k = self.nodes.get(concept_id)
        if k is None:
            return ""
        def n(ids):
            return ", ".join(names.get(i, i) for i in ids) or "—"
        before, afterwards = self.known_before(concept_id), self.later_than(concept_id)
        rows = [
            "BRIEF FROM THE TEACHING SCRIPT (binding):",
            f"- You INTRODUCE: {names.get(concept_id, concept_id)}"
            + (f" — contribution to the arc: {k.contribution}" if k.contribution else ""),
        ]
        if k.requires:
            rows.append((f"- Builds directly on: {n(k.requires)}. These have already been "
                           "explained — connect briefly, do NOT derive them again."))
        if before:
            rows.append((f"- At this point the reader already knows: {n(before[-8:])}. "
                          "What is known is referred to, not repeated."))
        if afterwards:
            rows.append((f"- NOT YET covered (do not anticipate, do not even "
                          f"hint at an explanation): {n(afterwards[:8])}."))
        if k.resumption:
            rows.append((f"- Will be resumed later in: {', '.join(k.resumption)}. "
                          "A back-reference is enough there; the complete explanation belongs here."))
        return "\n".join(rows)

    def job_lesson(self, lesson_id: str, concepts_of_lesson: list[str],
                        names: dict[str, str]) -> str:
        """The brief for a LESSON — not for a concept.

        Needed because run A writes per CONCEPT, but run B builds per
        LESSON. A chapter with two concepts and three lessons has a lesson
        without a concept of its own — a synthesis. Without an explicit
        instruction it explains everything again instead of connecting.
        That is the pattern the redundancy pass reports: l1 and l2
        introduce, l3 repeats.
        """
        own_ones = [cid for cid, k in self.nodes.items()
                  if k.introduction == lesson_id]
        foreign = [cid for cid in (concepts_of_lesson or [])
                 if cid in self.nodes and cid not in own_ones]

        def n(ids):
            return ", ".join(names.get(i, i) for i in ids) or "—"

        if not own_ones and (foreign or concepts_of_lesson):
            return (
                ("BRIEF FROM THE TEACHING SCRIPT — SYNTHESIS LESSON:\n"
                f"- This lesson introduces NO new concept. Covered are: {n(foreign)}.\n"
                "- All these concepts have been explained already. Its task is "
                "CONNECTING: how do they interlock, where do they seem to "
                "contradict each other, which fallacies arise from their interplay?\n"
                "- Repeat NO derivation. Refer back instead "
                "(\"as shown in the lesson on …\") and build on it.\n"
                "- The added value of this lesson lies in relations, use cases "
                "and distinctions — not in explaining again."))

        rows = ["BRIEF FROM THE TEACHING SCRIPT (binding):",
                  f"- This lesson INTRODUCES: {n(own_ones)}"]
        if foreign:
            rows.append((f"- Only RESUME, do not explain again: {n(foreign)}. "
                          "These concepts are introduced elsewhere; a back-reference "
                          "and application are enough here."))
        before = [k for k in self.known_before(own_ones[0])] if own_ones else []
        if before:
            rows.append((f"- The reader already knows: {n(before[-8:])}. "
                          "What is known is referred to, not repeated."))
        return "\n".join(rows)

    def job_resumption(self, concept_ids: list[str], names: dict[str, str]) -> str:
        """For sections that may ONLY resume a concept."""
        if not concept_ids:
            return ""
        list_ = ", ".join((f"{names.get(i, i)} (introduced in "
                           f"{self.nodes[i].introduction or '?'})")
                          for i in concept_ids if i in self.nodes)
        return (("ONLY RESUMPTION (do not explain again, only cross-reference and "
                 f"apply): {list_}"))

    # ── Serialisation ────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {"guiding_question": self.guiding_question, "common_thread": self.common_thread,
                "nodes": [k.to_dict() for k in self.nodes.values()]}

    @staticmethod
    def from_dict(d: dict) -> "TeachingScript":
        ls = TeachingScript(common_thread=list(d.get("common_thread") or []),
                        guiding_question=d.get("guiding_question", ""))
        for k in d.get("nodes") or []:
            if k.get("id"):
                ls.nodes[k["id"]] = Node(
                    id=k["id"], introduction=k.get("introduction", ""),
                    requires=list(k.get("requires") or []),
                    resumption=list(k.get("resumption") or []),
                    contribution=k.get("contribution", ""))
        return ls


def parse_teaching_script(data_: dict, concept_ids: set[str]) -> tuple[TeachingScript, list[str]]:
    """Builds the teaching script from the model answer and checks it.

    Returns (teaching script, findings). Findings are warnings — an
    incomplete teaching script must never block production; it only
    weakens the steering.
    """
    findings: list[str] = []
    ls = TeachingScript.from_dict(data_ or {})

    unknown = set(ls.nodes) - concept_ids
    for cid in sorted(unknown):
        findings.append(Msg("Teaching script names unknown concept '{cid}' — ignored", {"cid": cid}))
        ls.nodes.pop(cid, None)
    for cid in sorted(concept_ids - set(ls.nodes)):
        findings.append(Msg("Concept '{cid}' is missing from the teaching script — no place of introduction",
                            {"cid": cid}))
        ls.nodes[cid] = Node(id=cid)

    for cid, k in ls.nodes.items():
        foreign = [v for v in k.requires if v not in concept_ids]
        if foreign:
            findings.append(Msg("{cid}: unknown prerequisite {foreign} — removed", {"cid": cid, "foreign": foreign}))
            k.requires = [v for v in k.requires if v in concept_ids]
        if cid in k.requires:
            findings.append(Msg("{cid}: requires itself — removed", {"cid": cid}))
            k.requires.remove(cid)
        if not k.introduction:
            findings.append(Msg("{cid}: no place of introduction given", {"cid": cid}))

    for z in ls.cycles():
        findings.append(Msg("Dependency cycle: {cycle}", {"cycle": " → ".join(z)}))

    # Order errors: the check must compare the DECLARED places of introduction,
    # not the topological order — the latter is derived from the dependencies
    # and can therefore never show the contradiction.
    lesson_rank = {}
    for cid in sorted(ls.nodes, key=lambda x: (ls.nodes[x].introduction or "~", x)):
        place = ls.nodes[cid].introduction
        if place and place not in lesson_rank:
            lesson_rank[place] = len(lesson_rank)
    for cid, k in ls.nodes.items():
        own = lesson_rank.get(k.introduction)
        if own is None:
            continue
        for v in k.requires:
            prior = lesson_rank.get(ls.nodes[v].introduction if v in ls.nodes else None)
            if prior is not None and prior > own:
                findings.append(Msg(
                    "{cid} is introduced in {place}, but requires {v}, which is only "
                    "introduced in {later}",
                    {"cid": cid, "place": k.introduction, "v": v, "later": ls.nodes[v].introduction}))
    return ls, findings


def teaching_script_markdown(ls: TeachingScript, names: dict[str, str],
                             findings: list | None = None, lang: str | None = None) -> str:
    """01b-teaching-script.md — checkpoint artefact, editable by the user."""
    z = [tr("# Teaching script — common thread and concept graph", lang), ""]
    if ls.guiding_question:
        z += [tr("**Guiding question of the unit:** {q}", lang, q=ls.guiding_question), ""]
    if ls.common_thread:
        z += [tr("## Arc", lang), ""]
        z += [f"{i+1}. {s}" for i, s in enumerate(ls.common_thread)] + [""]
    z += [tr("## Concepts in learning order", lang), "",
          tr("| # | Concept | introduced in | builds on | resumed in |", lang),
          "|---|---------|---------------|-----------|------------|"]
    for i, cid in enumerate(ls.sequence_order(), 1):
        k = ls.nodes[cid]
        auf = ", ".join(names.get(v, v) for v in k.requires) or "—"
        wi = ", ".join(k.resumption) or "—"
        z.append(f"| {i} | {names.get(cid, cid)} ({cid}) | {k.introduction or '—'} "
                 f"| {auf} | {wi} |")
    z.append("")
    contributions = [(cid, ls.nodes[cid].contribution) for cid in ls.sequence_order()
                 if ls.nodes[cid].contribution]
    if contributions:
        z += [tr("## Contribution to the arc", lang), ""]
        z += [f"- **{names.get(cid, cid)}**: {b}" for cid, b in contributions] + [""]
    if findings:
        z += [tr("## Findings of the check", lang), ""] + [f"- {render(b, lang)}" for b in findings] + [""]
    z += ["---", "",
          tr("This document steers all following phases. Every section learns from it "
             "which concept it may introduce, what it can build on and what it must not "
             "anticipate. Corrections here affect the whole production.", lang)]
    return "\n".join(z)


def mermaid_graph(ls: TeachingScript, names: dict[str, str]) -> str:
    """Concept graph as Mermaid source (for the checkpoint artefact)."""
    rows = ["flowchart TD"]
    for cid in ls.sequence_order():
        title = names.get(cid, cid).replace('"', "'")
        rows.append(f'  {cid}["{title}"]')
    for cid, k in ls.nodes.items():
        for v in k.requires:
            rows.append(f"  {v} --> {cid}")
    return "\n".join(rows)


def apply_edits(ls: TeachingScript, rows: list[list]) -> list[str]:
    """Applies user edits from the checkpoint table.

    Columns: [ID, concept, introduced in, builds on (comma-separated)].
    Analogous to `ga.apply_edits` — at the checkpoint the user corrects what
    the model placed wrongly, and the correction affects the whole
    production.
    """
    hints: list[str] = []
    for z in rows or []:
        if len(z) < 4:
            continue
        cid = str(z[0]).strip()
        k = ls.nodes.get(cid)
        if k is None:
            continue
        new_place = str(z[2]).strip()
        if new_place and new_place != k.introduction:
            hints.append(Msg("{cid}: introduction {old} → {new}",
                             {"cid": cid, "old": k.introduction or "—", "new": new_place}))
            k.introduction = new_place
        raw = str(z[3]).strip()
        new_before = [t.strip() for t in raw.split(",") if t.strip() and t.strip() != "—"]
        new_before = [v for v in new_before if v in ls.nodes and v != cid]
        if set(new_before) != set(k.requires):
            hints.append(Msg("{cid}: builds on {old} → {new}",
                             {"cid": cid, "old": k.requires or "—", "new": new_before or "—"}))
            k.requires = new_before
    for z in ls.cycles():
        hints.append(Msg("⚠️ Cycle after editing: {cycle}", {"cycle": " → ".join(z)}))
    return hints
