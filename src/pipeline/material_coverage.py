# -*- coding: utf-8 -*-
"""Assigns planned concepts to evidence in the uploaded material.

Answers two questions, and the second is the more valuable one:
  * For which planned concept is there usable material?
  * Which material covers something that does not occur in the plan at all?

The structure mirrors the terminology check: cheap filters first, the
model only on the rest.

  1. LEXICAL — the technical terms of the concept name in the normalised
     full text and in the keywords of the segments. Costs nothing, and in
     technical texts a literal occurrence is a strong signal, because terms
     occur exactly.
  2. SEMANTIC, SEVERAL QUERIES — not only the concept name (that is a
     wording of the gap analysis, not the language of the source), but also
     rationale and learning objectives as queries of their own; hits merged.
  3. THE RERANKER DECIDES — its relevance score is comparable across
     queries, because query and document are rated together. Only that
     makes a fixed threshold meaningful; cosine values are not suitable for
     it.

Without a reranker there is a ranking without a decision — then the result
is marked explicitly as uncertain instead of pretending something is
evidenced.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.i18n import N_, tr

# Display labels for Coverage.provenance(); the codes are never shown.
PROVENANCE_LABEL = {"material": N_("material"), "material_unchecked": N_("material (unchecked)"),
                    "model_knowledge": N_("model knowledge")}

# Relevance threshold of the reranker. Cohere- and Jina-style endpoints
# return 0..1; 0.5 is set deliberately conservatively and has to be tuned on
# real material — a guessed threshold remains an estimate.
RERANKER_THRESHOLD = 0.5
# Below this limit a concept counts as not evidenced even if hits came back:
# retrieval ALWAYS returns top_k, even from a book that does not cover the
# concept.
MIN_EVIDENCE = 1


@dataclass
class Evidence:
    entry_id: str
    document: str
    title: str
    value: float
    source: str                 # "reranker" | "cosine"
    excerpt: str = ""


@dataclass
class Coverage:
    concept_id: str
    concept_name: str
    evidence: list[Evidence] = field(default_factory=list)
    lexical: list[str] = field(default_factory=list)

    @property
    def evidenced(self) -> bool:
        return len(self.evidence) >= MIN_EVIDENCE

    @property
    def safe(self) -> bool:
        """Evidenced AND confirmed by the reranker."""
        return self.evidenced and any(b.source == "reranker" for b in self.evidence)

    def provenance(self) -> str:
        if self.safe:
            return "material"
        if self.evidenced:
            return "material_unchecked"
        return "model_knowledge"


def _terms(name: str) -> list[str]:
    """Extracts the essential technical terms from a concept name.

    Concept names are descriptive phrases; the material is searched for the
    terms in them, though.
    """
    stop = {"und", "oder", "als", "im", "in", "der", "die", "das", "des", "den",
             "from", "vom", "zur", "zum", "bei", "auf", "aus", "durch", "fuer",
             "für", "mit", "ueber", "über", "sowie", "eines", "einer"}
    raw = re.split(r"[\s\-–—/(),:]+", name or "")
    return [w for w in raw if len(w) >= 5 and w.lower() not in stop]


def lexical_hits(concept_name: str, corpus_normal: str,
                         entries) -> list[str]:
    """Segment IDs whose keywords or title contain a term."""
    terms = [t.lower() for t in _terms(concept_name)]
    if not terms:
        return []
    hits = []
    for e in entries or []:
        haystack = " ".join([e.title or "", e.summary or "",
                        " ".join(e.keywords or [])]).lower()
        if any(t in haystack for t in terms):
            hits.append(e.id)
    return hits


async def check_concept(concept: dict, index, corpus_normal: str = "",
                         learning_objectives: list[str] | None = None,
                         top_k: int = 5) -> Coverage:
    """Searches evidence for a single concept."""
    name = concept.get("name") or ""
    ab = Coverage(concept_id=concept.get("id", "?"), concept_name=name)
    if index is None or not getattr(index, "_entries", None):
        return ab

    ab.lexical = lexical_hits(name, corpus_normal, index._entries)

    # Query several wordings of the same thing and merge the results.
    requests_made = [name]
    if concept.get("rationale"):
        requests_made.append(f"{name}. {concept['rationale']}")
    for lo in (learning_objectives or [])[:2]:
        requests_made.append(lo)

    seen: dict[str, Evidence] = {}
    for request_text in requests_made:
        try:
            hits = await index.retrieve_scored(request_text, top_k=top_k)
        except Exception:  # noqa: BLE001 — coverage must never block
            continue
        for entry, value, source in hits:
            if source == "reranker" and not (value >= RERANKER_THRESHOLD):
                continue
            present = seen.get(entry.id)
            if present is None or value > present.value:
                seen[entry.id] = Evidence(
                    entry_id=entry.id, document=entry.document,
                    title=entry.title, value=round(float(value), 3),
                    source=source,
                    excerpt=(entry.summary or entry.full_text)[:300])
    ab.evidence = sorted(seen.values(), key=lambda b: -b.value)[:top_k]
    return ab


async def matrix(concepts: list[dict], index, corpus_normal: str = "",
                 objectives_per_concept: dict | None = None) -> dict:
    """Coverage matrix in both directions.

    Returns:
      coverage   — the evidence per concept
      orphaned   — material segments that match no concept
      reranker   — whether the decision is reliable
    """
    result = []
    evidenced_ids: set[str] = set()
    for k in concepts or []:
        ab = await check_concept(
            k, index, corpus_normal,
            (objectives_per_concept or {}).get(k.get("id")) or [])
        evidenced_ids.update(b.entry_id for b in ab.evidence)
        result.append(ab)

    orphaned = []
    for e in (getattr(index, "_entries", None) or []):
        if e.id not in evidenced_ids:
            orphaned.append({"id": e.id, "document": e.document,
                             "title": e.title, "kind": e.kind,
                             "summary": (e.summary or "")[:200]})
    with_reranker = any(b.source == "reranker" for ab in result for b in ab.evidence)
    return {"coverage": result, "orphaned": orphaned,
            "reranker": with_reranker}


def as_markdown(m: dict, lang: str | None = None) -> str:
    ab = m.get("coverage") or []
    z = [tr("### Material coverage", lang), ""]
    if not ab:
        return "\n".join(z + [tr("_No material index available._", lang)])
    if not m.get("reranker"):
        z += [tr("> Without a reranker there is only a ranking, no relevance decision. Read "
                 "the assignment as a pointer, not as evidence.", lang), ""]
    without = [a for a in ab if not a.evidenced]
    z += [tr("**{n} of {total} concepts** have evidence in the material.", lang,
             n=len(ab) - len(without), total=len(ab)), "",
          tr("| Concept | Evidence | best score | Source |", lang), "|---|---:|---:|---|"]
    for a in ab:
        best = f"{a.evidence[0].value:.2f}" if a.evidence else "—"
        z.append(f"| {a.concept_name} ({a.concept_id}) | {len(a.evidence)} "
                 f"| {best} | {tr(PROVENANCE_LABEL[a.provenance()], lang)} |")
    z.append("")
    if without:
        z += [tr("**Without evidence — written from model knowledge:**", lang), ""]
        z += [f"- {a.concept_name} ({a.concept_id})" for a in without] + [""]
    orphaned = m.get("orphaned") or []
    if orphaned:
        z += [tr("**Material without a concept ({n} segments)** — possibly overlooked "
                 "content:", lang, n=len(orphaned)), ""]
        for e in orphaned[:15]:
            z.append(f"- [{e['kind']}] {e['title']} ({e['document']})")
        if len(orphaned) > 15:
            z.append(tr("- … and {n} more", lang, n=len(orphaned) - 15))
        z.append("")
    return "\n".join(z)


def evidence_block(ab: Coverage, limit: int = 3) -> str:
    """Evidence as context for the concept author."""
    if not ab.evidence:
        return (("EVIDENCE: none found in the uploaded material. "
                "Write from subject knowledge and mark nothing as a quotation."))
    z = [("EVIDENCE FROM THE MATERIAL (authoritative — terminology and "
         "statements follow it, not model knowledge):")]
    for b in ab.evidence[:limit]:
        z.append(f"— [{b.entry_id}] {b.title} ({b.document}): {b.excerpt}")
    return "\n".join(z)
