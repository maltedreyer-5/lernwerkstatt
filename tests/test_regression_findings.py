# -*- coding: utf-8 -*-
"""Every case found in real runs, checked against the current code.

This file is the project's memory: it contains ONE unit in which every
error is hidden that actually occurred in generated learning units — with
its origin. If one of them comes back, this test fails.

Order as in the application: type alias -> field alias -> normalisation ->
validation -> degradation.
"""
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

for _m in ("openai", "httpx"):
    if _m not in sys.modules:
        try:
            __import__(_m)
        except ImportError:
            _mod = types.ModuleType(_m)
            _mod.__getattr__ = lambda a: object  # type: ignore[attr-defined]
            sys.modules[_m] = _mod

from src.pipeline.learning_pipeline import _resolve_field_aliases  # noqa: E402
from src.unit import degradation as degr  # noqa: E402
from src.unit.normalization import normalise_unit  # noqa: E402
from src.unit.validator import validate  # noqa: E402

B = chr(92)


def check(b, name):
    print(f"  {'ok  ' if b else 'FAIL'} {name}")
    return 0 if b else 1


# ── One block per case found in real runs, with its origin
# ──────────────────────────────
FINDINGS = [
    # (id, origin, block, check after the chain)
    ("mermaid-stadium", "A([Start]) became A(\"[Start]\")",
     {"type": "diagram", "engine": "mermaid",
      "code": "flowchart LR\n  A([Start (Boden)]) --> B[Ziel]",
      "description": "Der Ablauf von der Quelle bis zum Ziel im Überblick"},
     lambda b: "A([" in b.get("code", "")),

    ("mermaid-double-circle", "label protection destroyed A(((X)))",
     {"type": "diagram", "engine": "mermaid",
      "code": "flowchart LR\n  A(((Kern))) --> B[Rand]",
      "description": "Kern und Rand eines Systems in ihrer Beziehung"},
     lambda b: "A(((Kern)))" in b.get("code", "")),

    ("special-tokens", "<s> and <pad> in a lesson on tokenisation were deleted",
     {"type": "flashcards", "cards": [
         {"front": "<s>", "back": "Markiert den Beginn einer Sequenz."},
         {"front": "<pad>", "back": "Füllt kürzere Sequenzen auf."}]},
     lambda b: all(k.get("front") for k in b.get("cards", []))),

    ("field-name-caption", "beschriftung instead of description",
     {"type": "diagram", "engine": "mermaid", "code": "flowchart LR\n  A-->B",
      "caption": "Der Signifikanztest im Ablauf dargestellt"},
     lambda b: bool(b.get("description")) and "caption" not in b),

    ("invented-type", "unknown block type 'grafik'",
     {"type": "grafik", "engine": "mermaid", "code": "flowchart LR\n  A-->B",
      "description": "Ein Ablauf, den das Modell als grafik bezeichnet hat"},
     lambda b: b.get("type") == "diagram"),

    ("literal-escapes", "\\n visible in task material",
     {"type": "error_analysis", "title": "F", "question": "Was stimmt nicht?",
      "material": "Eigenkapital: 1.200 TEUR" + B + "n" + B + "nSchritt 1: prüfen",
      "sample_solution": "Die latenten Steuern fehlen."},
     lambda b: B not in b.get("material", "")),

    ("markdown-list-escaped", "dash list in preformatted material",
     {"type": "error_analysis", "title": "F2", "question": "Und hier?",
      "material": "Der Lauf zeigt:\n- Erster Punkt\n- Zweiter Punkt",
      "sample_solution": "Beide Punkte sind falsch."},
     lambda b: "- Erster Punkt" in b.get("material", "")),

    ("bare-subscript", "q_{m+1} in a description",
     {"type": "note", "variant": "info",
      "html": "<p>Die Komponenten q_m und q_{m+1} rotieren gemeinsam.</p>"},
     lambda b: "_{" not in b.get("html", "")),

    ("categorisation", "repeated right values — not an error",
     {"type": "matching", "task": "Ordne zu", "pairs": [
         {"left": "Trägt die Bedeutung", "right": "Embedding"},
         {"left": "Kodiert die Position", "right": "Positional Encoding"},
         {"left": "Bleibt konstant", "right": "Embedding"}]},
     lambda b: len(b.get("pairs", [])) == 3),

    ("bind-without-name", "params[0]('alpha_slider') without name",
     {"type": "chart", "engine": "vegalite",
      "description": "Stelle Alpha ein und beobachte die Fehlerrate",
      "spec": {"data": {"values": [{"x": 1, "y": 2}]},
               "transform": [{"calculate": "datum.y * alpha_slider", "as": "s"}],
               "mark": "line",
               "encoding": {"x": {"field": "x", "type": "quantitative"},
                            "y": {"field": "s", "type": "quantitative"}},
               "params": [{"name": "alpha_slider", "value": 1,
                           "bind": {"input": "range", "min": 0, "max": 2}}]}},
     lambda b: b["spec"]["params"][0]["bind"].get("name") == "Alpha"),

    ("block-type-mindmap", "Mermaid type as block type — an intact mind map was downgraded",
     {"type": "mindmap",
      "description": "Vorschau: Welche Komponenten müssen zusammenspielen, "
                      "damit aus einem Eingabetext eine Vorhersage wird?",
      "code": "mindmap\n  root((Transformer-Architektur))\n    Eingabe\n"
              "      Tokenisierung\n      Embedding\n    Verarbeitung\n"
              "      Self-Attention\n      Feedforward"},
     lambda b: b.get("type") == "diagram" and b.get("engine") == "mermaid"
     and "\n    Eingabe" in b.get("code", "")),

    ("mermaid-quadrant-colon", "colon in quadrant labels (depends on the Mermaid version)",
     {"type": "diagram", "engine": "mermaid",
      "description": "Einordnung der Korrekturmethoden nach Forschungsziel "
                      "und Kosten falscher Positiver",
      "code": "quadrantChart\ntitle Einordnung: Forschungsziel x Kosten\n"
              "x-axis Exploratorisch --> Konfirmatorisch\n"
              "y-axis Niedrige Kosten --> Hohe Kosten\n"
              "quadrant-1 Konfirmatorisch, hohe Kosten: FWER (Bonferroni)\n"
              "quadrant-3 Exploratorisch, niedrige Kosten: FDR (BH)\n"
              "\"GWAS mit Therapiebezug\": [0.2, 0.8]"},
     lambda b: "Kosten: FWER" not in b.get("code", "")
     and "Kosten – FWER" in b.get("code", "")
     and '"GWAS mit Therapiebezug": [' in b.get("code", "")),

    ("mermaid-inner-quote", "mixed quotes in a label, downgraded depending on the version",
     {"type": "diagram", "engine": "mermaid",
      "description": "Vergleich von Einzelstudie, großer Studie und "
                      "registrierter Replikation nach fünf Kriterien",
      "code": "flowchart TD\nsubgraph Stichprobe[\"Studientypen\"]\ndirection LR\n"
              "A[\"Einzelstudie<br/>n=30-50<br/>Power: selten\"]\n"
              "B[\"Große Studie<br/>n>\"200<br/>Power: ja a priori<br/>"
              "Effekt robust: mittel'\"]\n"
              "C[\"Registrierte Replikation<br/>n=Power≥.80\"]\n"
              "A --> B --> C\nend"},
     lambda b: "n>'200" in b.get("code", "") and '>"2' not in b.get("code", "")
     and b.get("code", "").splitlines()[4].count('"') == 2),

    ("mermaid-sankey-umlaut", "the sankey lexer accepts no umlauts",
     {"type": "diagram", "engine": "mermaid",
      "description": "Fluss von 1000 untersuchten Hypothesen bis zu "
                      "publizierten Befunden",
      "code": 'sankey-beta\n"Untersuchte Hypothesen","Als relevant ausgewählt",200\n'
              '"Als relevant ausgewählt","Signifikant durch Zufall",80\n'
              '"Signifikant durch Zufall","Abgelehnt in Review",30'},
     lambda b: b.get("code", "").isascii() and "ausgewaehlt" in b.get("code", "")),

    ("mermaid-erdiagram", "flowchart heuristics destroyed an erDiagram",
     {"type": "diagram", "engine": "mermaid",
      "code": "erDiagram\n    DOKUMENT ||--o{ KAPITEL : enthaelt\n"
              "    KAPITEL ||--o{ CHUNK : zerfaellt_in\n"
              "    CHUNK {\n        string chunk_id\n        int token_anzahl\n    }",
      "description": "Eltern-Kind-Beziehungen: Dokument, Kapitel, Chunk mit "
                      "Kardinalitäten"},
     lambda b: "||--o{" in b.get("code", "") and "<br/>" not in b.get("code", "")
     and '"' not in b.get("code", "")),

    ("mermaid-pipe-label", "edge label quoting mangled P(Daten | H0)",
     {"type": "diagram", "engine": "mermaid",
      "code": "flowchart TD\n    A[p = P(Daten | H0) und nicht P(H0 | Daten)] --> B[Fazit]",
      "description": "Der p-Wert ist die Wahrscheinlichkeit der Daten unter "
                      "der Nullhypothese, nicht umgekehrt"},
     lambda b: b.get("code", "").count('"') == 2
     and '"p = P(Daten | H0) und nicht P(H0 | Daten)"' in b.get("code", "")),

    ("mermaid-subscript", "a Sankey failed on 'H₀' alone",
     {"type": "diagram", "engine": "mermaid",
      "code": "sankey-beta\nZutreffende H\u2080 (9500),Nicht signifikant,9025\n"
              "Zutreffende H\u2080 (9500),Signifikante Ergebnisse R,475",
      "description": "Erwarteter Anteil falscher positiver Befunde unter den "
                      "Ablehnungen als Schlauchbreite"},
     lambda b: "\u2080" not in b.get("code", "") and "H0" in b.get("code", "")),

    ("reference-line", "constant series next to a changing one",
     {"type": "chart", "engine": "chartjs",
      "description": "Verlauf gegen die Signifikanzschwelle",
      "spec": {"type": "line", "data": {"labels": ["a", "b", "c", "d"], "datasets": [
          {"label": "p-Wert", "data": [0.2, 0.1, 0.04, 0.01]},
          {"label": "Schwelle", "data": [0.05, 0.05, 0.05, 0.05]}]}}},
     lambda b: True),
]

# Findings that MUST remain ERRORS
MUST_ERRORS = [
    ("vega-datum-without-type", "Invalid field type undefined",
     {"type": "chart", "engine": "vegalite",
      "description": "Verlauf mit eingezeichneter Grenze zum Vergleich",
      "spec": {"data": {"values": [{"x": 1}]}, "vconcat": [
          {"mark": "line", "encoding": {"x": {"field": "x", "type": "quantitative"}}},
          {"mark": "rule", "encoding": {"y": {"datum": {"expr": "g"}}}}],
          "params": [{"name": "g", "value": 1,
                      "bind": {"input": "range", "name": "G"}}]}},
     "without type"),
    ("vega-param-as-field", "encoding.x.field 'delta' is a parameter",
     {"type": "chart", "engine": "vegalite",
      "description": "Stelle Delta ein und beobachte die Verschiebung",
      "spec": {"data": {"values": [{"n": 1}]}, "mark": "line",
               "encoding": {"x": {"field": "delta", "type": "quantitative"}},
               "params": [{"name": "delta", "value": 1,
                           "bind": {"input": "range", "name": "Delta"}}]}},
     "is a PARAMETER"),
]


def _chain(unit):
    for l in unit["lessons"]:
        for b in l["blocks"]:
            _resolve_field_aliases(b)
    for m in unit.get("modules") or []:
        for b in m.get("exercises") or []:
            _resolve_field_aliases(b)
    normalise_unit(unit)
    finding = validate(unit, node_probe=False)
    replaced = degr.downgrade(unit, finding)
    if replaced:
        finding = validate(unit, node_probe=False)
    return finding, replaced


def test_all_findings():
    print("all cases found in real runs")
    blocks = [{"type": "text", "html": "<p>" + ("Wort " * 120) + "</p>"}]
    blocks += [b for _, _, b, _ in FINDINGS]
    unit = {"id": "regress", "title": "Regression", "language": "de",
            "state": "final", "depth_profile": "compact", "duration_minutes": 20,
            "learning_objectives": ["Z"], "concepts": [], "glossary": [],
            "lessons": [{"id": "l1", "title": "L", "concepts": [],
                           "blocks": blocks}]}
    finding, replaced = _chain(unit)

    f = check(not finding.errors, "the unit is free of errors"
               + (f" — offen: {finding.errors[:2]}" if finding.errors else ""))
    f += check(not replaced, "no component had to be downgraded"
                + (f" — {replaced[:1]}" if replaced else ""))

    # Every block on its own
    after = unit["lessons"][0]["blocks"][1:]
    for (identifier, provenance, _, check_result), blk in zip(FINDINGS, after):
        f += check(check_result(blk), f"{identifier}  [{provenance[:44]}]")
    return f


def test_real_errors_remain():
    """Whatever really makes the display unusable MUST stay an error."""
    print("real defects are still reported")
    f = 0
    for identifier, provenance, blk, expected in MUST_ERRORS:
        unit = {"id": "t", "title": "T", "language": "de", "state": "final",
                "depth_profile": "compact", "lessons": [
                    {"id": "l1", "title": "L", "concepts": [], "blocks": [
                        {"type": "text", "html": "<p>Text.</p>"}, dict(blk)]}]}
        finding = validate(unit, node_probe=False)
        f += check(any(expected in x for x in finding.errors),
                    f"{identifier}  [{provenance[:44]}]")
    return f


def test_terminology_case_d():
    """The complete corruption chain of the terminology case, step by step.

    The pronoun 'Sie' became a term candidate, the model answered with the
    meta description 'Personalpronomen (kein Fachterminus)', and the
    blocklist wrote it into every sentence by regex — 124 places in the
    chapter scripts, 9 in delivered glossary definitions ('…
    Personalpronomen (kein Fachterminus) basiert auf der Union Bound …').
    """
    print("terminology: the corruption chain")
    from src.unit.terminology import (Terminology, terms_from_text,
                                       substitute_usable)
    f = 0

    # 1. Extraction + candidate check: pronouns, deixis, quantities and short
    #    words do not become candidates; a real term does.
    html = ("<p>Sie bezeichnet die Wahrscheinlichkeit mindestens eines "
            "Fehlers. Dieser Ausdruck beschreibt das Gesamtrisiko. Bei "
            "Tausenden von Genen bezeichnet man die signifikanten Treffer "
            "als sogenannte Hits. Als sogenannte Alpha-Inflation bezeichnet "
            "man den Anstieg des Gesamtfehlers.</p>")
    found_items = terms_from_text(html)
    for artifact in ("Sie", "Dieser Ausdruck", "Tausenden von Genen"):
        f += check(artifact not in found_items, f"'{artifact}' is not extracted")
    t0 = Terminology()
    open_ = [k["term"] for k in t0.check(html, "Kapitel 1")]
    f += check("Hits" not in open_ and "hits" not in t0.candidates_,
                "'Hits' fails MIN_LENGTH (candidate check)")
    f += check("Alpha-Inflation" in open_,
                "a real term is still reported as a candidate")

    # 2. Verdict: a meta 'substitute' is unusable, real terms stay usable.
    f += check(not substitute_usable("Sie", "Personalpronomen (kein Fachterminus)"),
                "a meta description as substitute is rejected")
    f += check(not substitute_usable("X", "PRDS; etablierte Annahme, umschrieben als …"),
                "an explanatory substitute with punctuation is rejected")
    f += check(substitute_usable("Fehlerfamilienrate",
                                 "Family-Wise Error Rate (FWER)"),
                "an insertable term stays allowed as a substitute")

    # 3. adopt_verdict: no_term discards; a meta substitute is treated like
    #    no_term — none of it reaches the blocklist or the fixed terminology.
    t = Terminology()
    t.candidates_["sie"] = {"term": "Sie", "status": "open", "substitute": "",
                           "occurrence": "Kapitel 1"}
    subst = t.adopt_verdict([
        {"term": "Sie", "established": False,
         "substitute": "Personalpronomen (kein Fachterminus)"},
        {"term": "Hits", "established": False, "no_term": True},
    ])
    f += check(not subst, "no replacement from meta verdicts")
    f += check("sie" not in t.blocklist and "hits" not in t.blocklist,
                "the blocklist stays free of artefacts")
    f += check(not any("kein fachterminus" in (e.get("term") or "").lower()
                        for e in t.fixed_terms.values()),
                "the fixed terminology stays free of meta descriptions")

    # 4. replace: even an OLD, persisted blocklist with such an entry must no
    #    longer touch the text.
    t2 = Terminology()
    t2.blocklist = {"sie": "Personalpronomen (kein Fachterminus)"}
    t2.candidates_["sie"] = {"term": "Sie", "status": "rejected",
                            "substitute": "Personalpronomen (kein Fachterminus)"}
    text, n = t2.replace("Solange Sie nur einen Vergleich betrachten, "
                         "steuern Sie das Risiko gezielt.")
    f += check(n == 0 and "Personalpronomen" not in text and "Sie" in text,
                "an old blocklist no longer replaces 'Sie'")

    # 5. Inflection dedup: the variant with another ending takes over the
    #    decision instead of staying open for good.
    t3 = Terminology()
    t3.candidates_["positiveregressionsabhaengigenstruktur"] = {
        "term": "positive regressionsabhängigen Struktur",
        "status": "rejected", "substitute": "PRDS", "occurrence": ""}
    t3.blocklist["positiveregressionsabhaengigenstruktur"] = "PRDS"
    hits = t3._check_one("positiven regressionsabhängigen Struktur",
                               "Kapitel 2", "text")
    f += check(hits is not None and hits.get("reason") == "blocklist"
                and hits.get("substitute") == "PRDS",
                "an inflection variant takes over the existing decision")
    f += check(not t3.open_candidates(), "no candidate that stays open for good")

    # 6. set_: bracket variants collapse into ONE entry.
    t4 = Terminology()
    t4.set_("Benjamini-Hochberg-Verfahren (BH-Verfahren)", "Def A", "script")
    t4.set_("Benjamini-Hochberg-Verfahren (BH)", "Def B", "kapitel-meta")
    f += check(len(t4.fixed_terms) == 1, "bracket variants become one entry")
    return f


def test_enrichment_does_not_clump():
    """2x (or 4x) prediction directly in a row."""
    print("enrichment: no adjacent duplicates, correct C1b target")
    from src.pipeline.learning_pipeline import LearningPipeline as _L
    f = 0
    blocks = [{"type": "text", "html": "<p>…</p>"},
               {"type": "prediction", "question": "<p>Wie hoch?</p>",
                "resolution": "<p>…</p>"},
               {"type": "text", "html": "<p>…</p>"}]
    new_ = {"type": "prediction", "question": "<p>Und jetzt?</p>",
           "resolution": "<p>…</p>"}
    ok, _ = _L._block_insertable(blocks, 2, new_)      # direkt HINTER Block 1
    f += check(not ok, "the same type directly adjacent is rejected")
    ok, _ = _L._block_insertable(blocks, 3, new_)      # at the end, text in between
    f += check(ok, "the same type at a distance stays allowed")
    duplicate_entry = {"type": "prediction", "question": "<p>Wie hoch?</p>",
                "resolution": "<p>anders</p>"}
    ok, _ = _L._block_insertable(blocks, 3, duplicate_entry)
    f += check(not ok, "a task with the same content is rejected")

    # C1b target: ceil instead of round — 605 words ask for 2, not 1.5→2 by
    # chance of rounding; 850 ask for 3; 'detailed' from 500 on at least 2.
    f += check(_L._interaction_target(605, None) == 2, "605 words -> target 2")
    f += check(_L._interaction_target(850, None) == 3, "850 words -> target 3 (ceil)")
    f += check(_L._interaction_target(550, "detailed") == 2,
                "550 words detailed -> at least 2 (not 1)")
    return f


def test_detail_plan_density_check():
    """Detail plans with too few interactions propagate into the unit."""
    print("detail plan: deterministic density check (depends on the profile)")
    from src.pipeline.learning_pipeline import LearningPipeline as _L
    f = 0
    thin = {"lessons": [
        {"id": "l1", "concepts": ["k1"],
         "media_plan": ["text mit h3-Gliederung", "formel (Union Bound)",
                        "quiz (…)"]},
        {"id": "l2", "concepts": ["k2"],
         "media_plan": ["text", "quiz (…)", "quiz (…)"]}]}
    findings = _L._detail_plan_findings(thin, depth_profile="detailed",
                                   v_ids={"k1", "k2"})
    f += check(any("l1" in b and "interaction" in b for b in findings),
                "detailed: one interaction per lesson is objected to")
    f += check(any("l2" in b and "display" in b for b in findings),
                "V lesson without a display is objected to")
    f += check(any("interaction" in b for b in findings),
                "quiz monoculture in the chapter is objected to")
    # In the profile 'compact' ONE self-check per lesson complies (C1) — the
    # same planning must not produce an interaction finding there.
    compact = _L._detail_plan_findings(thin, depth_profile="compact",
                                   v_ids={"k1", "k2"})
    f += check(not any("Interaktion(en) im" in b for b in compact),
                "compact: one interaction per lesson complies")
    # K/D lessons without a display are allowed (the rule only applies to V).
    kd = _L._detail_plan_findings(thin, depth_profile="detailed", v_ids=set())
    f += check(not any("display" in b for b in kd),
                "without a V concept no duty to display")
    dense = {"lessons": [
        {"id": "l1", "concepts": ["k1"],
         "media_plan": ["text mit h3-Gliederung", "chart (Verlauf)",
                        "vorhersage (…)", "quiz (…)"]},
        {"id": "l2", "concepts": ["k2"],
         "media_plan": ["text", "diagramm:flowchart (Ablauf)",
                        "zuordnung (…)", "lueckentext (…)"]}]}
    f += check(not _L._detail_plan_findings(dense, depth_profile="detailed",
                                         v_ids={"k1", "k2"}),
                "a dense plan passes without findings")
    # Nomenclature in other languages is translated instead of miscounted — a
    # correct English plan must not trigger a revision.
    en = {"lessons": [
        {"id": "l1", "concepts": ["k1"],
         "media_plan": ["text", "diagram:flowchart (process)",
                        "matching (terms)", "quiz (misconception)"]},
        {"id": "l2", "concepts": ["k2"],
         "media_plan": ["text", "chart (trend)", "cloze (…)",
                        "prediction (…)"]}]}
    f += check(not _L._detail_plan_findings(en, depth_profile="detailed",
                                         v_ids={"k1", "k2"}),
                "an English media plan is translated, no false alarm")
    # Completely unknown nomenclature: no verdict instead of a wrong verdict.
    foreign = {"lessons": [
        {"id": "l1", "concepts": ["k1"],
         "media_plan": ["texte", "schéma (processus)", "questionnaire"]}]}
    f += check(not _L._detail_plan_findings(foreign, depth_profile="detailed",
                                         v_ids={"k1"}),
                "unknown nomenclature is skipped, no wrong verdict")
    return f


def test_glossary_variants_stay_general():
    """Dedup merges only notation variants — never genuine distinctions.

    The counter-examples come deliberately from OTHER domains (law, ML), so
    that the rules are not overfitted to one statistics unit.
    """
    print("glossary: notation variants vs. genuine distinctions")
    from src.unit.terminology import glossary_duplicate, glossary_suspect
    f = 0
    # Merge: provable notation variants.
    f += check(glossary_duplicate("Benjamini-Hochberg-Verfahren (BH)",
                                 "Benjamini-Hochberg-Verfahren (BH-Verfahren)"),
                "abbreviation bracket variants are duplicates")
    f += check(glossary_duplicate("Family-Wise Error Rate (FWER)",
                                 "Family-Wise Error Rate"),
                "with/without its own abbreviation is a duplicate")
    # Do NOT merge: qualifying brackets (genuine distinctions).
    f += check(not glossary_duplicate("q-Wert", "q-Wert (Storey)"),
                "'q-Wert (Storey)' stays an entry of its own")
    f += check(not glossary_duplicate("Anbieter (KI-Verordnung)",
                                     "Anbieter (DSGVO)"),
                "disambiguated homonyms stay separate")
    f += check(not glossary_duplicate("Union Bound",
                                     "Union Bound (Boolesche Ungleichung)"),
                "an explanatory bracket is not merged silently")
    # Suspect: cases that can be confused are REPORTED instead of deleted.
    f += check(bool(glossary_suspect("q-Wert", "q-Wert (Storey)")),
                "the q-Wert pair is reported as a suspect")
    f += check(bool(glossary_suspect(
        "PRDS (Positive Regression-Dependent on a Subset)",
        "Positive Regression Dependence on a Subset (PRDS)")),
                "PRDS: core↔bracket crossing is reported")
    f += check(bool(glossary_suspect(
        "Positive Regression Dependence on a Subset (PRDS)",
        "Positive regressionsabhängige Struktur (PRDS)")),
                "PRDS: the same abbreviation on two cores is reported")
    # No suspect: a shared qualifier (e.g. a statute abbreviation) and homonyms
    # disambiguated on both sides are legitimate.
    f += check(not glossary_suspect("Anbieter (KI-VO)", "Betreiber (KI-VO)"),
                "a shared statute abbreviation is no suspect")
    f += check(not glossary_suspect("Anbieter (KI-Verordnung)",
                                     "Anbieter (DSGVO)"),
                "homonyms disambiguated on both sides are no suspect")
    return f


def test_terminology_stays_general():
    """The terminology filters must not cut content of other domains."""
    print("terminology: filters hit only artefacts, not terms")
    from src.unit.terminology import Terminology, stem_form
    f = 0
    t = Terminology()
    # Hyphenated compounds are ONE term — even if a component happens to be a
    # function word (security, linguistics, shell domains).
    for term in ("Man-in-the-Middle-Angriff", "Hier-Dokument",
                    "Wer-darf-was-Matrix"):
        f += check(t._eligible_candidate(term),
                    f"{term!r} stays eligible as a candidate")
    # Free-standing function words stay out.
    for term in ("Sie", "Dieser Ausdruck", "Tausenden von Genen"):
        f += check(not t._eligible_candidate(term),
                    f"{term!r} stays excluded")
    # The stem form also merges genitive + base form (iterative stripping) …
    f += check(stem_form("Prüfverfahren") == stem_form("Prüfverfahrens"),
                "genitive s and base form come together")
    # … but different numbers of words never merge (protection in
    # _stem_matches).
    t2 = Terminology()
    t2.candidates_["risikostufenkaskade"] = {
        "term": "Risikostufenkaskade", "status": "rejected",
        "substitute": "Eskalationsstufen", "occurrence": ""}
    f += check(t2._stem_matches("Risikostufen Kaskade") is None,
                "a different number of words takes over no foreign decision")
    return f


def test_gap_protocol_vocabulary():
    """A gap analysis failed at the hard gate with kind and interference values
    translated into English — the language rule asked for JSON string values
    in the unit's language and collided with the protocol vocabulary."""
    print("gap analysis: translated schema values are normalised")
    import src.pipeline.gap_analysis as ga
    from src.prompts import learning
    f = 0
    basis = {"interference_rationale": "…",
             "concepts": [{"id": "k1", "name": "Testkonzept", "concept_class": "v",
                           "rationale": ""}],
             "chapters": [{"title": "T", "concepts": ["k1"],
                          "learning_objectives": ["Kann …"], "prerequisites": []}],
             "unit_title": "T", "description": ""}
    # Unambiguous translations (including spelling variants) parse without
    # errors …
    for raw_kind, raw_int in (("paradigm_shift", "high"),
                             ("Paradigm Shift", "HIGH"),
                             ("extension", "medium"),
                             ("version-delta", "low"),
                             # German protocol values, as models produce them
                             # when the unit is German:
                             ("paradigmenwechsel", "hoch"),
                             ("Erweiterung", "mittel"),
                             ("versionsdelta", "gering")):
        try:
            g = ga.parse_gap({**basis, "kind": raw_kind, "interference": raw_int})
            ok = (g.kind in ("paradigm_shift", "extension", "version_delta")
                  and g.interference in ("high", "medium", "low")
                  and g.concepts[0].concept_class == "V")
        except ga.GapParseError:
            ok = False
        f += check(ok, f"'{raw_kind}'/'{raw_int}' is normalised")
    # … the concrete case lands on the right values …
    g = ga.parse_gap({**basis, "kind": "paradigm_shift", "interference": "high"})
    f += check((g.kind, g.interference) == ("paradigm_shift", "high"),
                "the observed values map to paradigm_shift/high")
    # … and what is really unknown stays a hard error (gate intact).
    try:
        ga.parse_gap({**basis, "kind": "mystery", "interference": "high"})
        f += check(False, "an unknown kind stays a hard error")
    except ga.GapParseError as e:
        f += check("mystery" in str(e), "an unknown kind stays a hard error")
    # The cause: the language rule exempts protocol vocabulary.
    rule = learning.language_rule("en")
    f += check("LANGUAGE RULE" in rule and "NEVER translated" in rule,
                "the language rule carries the protocol exception")
    return f


def test_english_unit_nomenclature():
    """A systematic search following the gap case: where else does model
    nomenclature in another language meet protocol vocabulary?

    Three places — block types (cost repair calls or degradation), field
    names (likewise) and the glossary marker (failed SILENTLY: no error,
    simply no glossary, and the handout kept the glossary block in the
    text).
    """
    print("units in other languages: block types, field names, glossary marker")
    from src.pipeline.learning_pipeline import (_resolve_field_aliases,
                                           _normalise_glossary_marker,
                                           _resolve_type_alias)
    f = 0
    # Block types: English names (= media plan nomenclature) are read.
    for raw, target in (("prediction", "prediction"), ("cloze", "cloze"),
                      ("error_analysis", "error_analysis"), ("Note", "note"),
                      ("formula", "formula"), ("flashcard", "flashcards")):
        blk = {"type": raw, "question": "x"}
        _resolve_type_alias(blk)
        f += check(blk["type"] == target, f"type '{raw}' is read as '{target}'")
    # Field names: question/solution & co. land on the required fields.
    blk = {"type": "prediction", "question": "<p>Wie hoch?</p>",
           "solution": "<p>…</p>"}
    _resolve_field_aliases(blk)
    f += check(blk["type"] == "prediction" and blk.get("question")
                and blk.get("resolution") and "solution" not in blk,
                "prediction: solution → resolution, question stays")
    # German field names, as a model writing a German unit produces them
    blk = {"type": "vorhersage", "frage": "<p>Wie hoch?</p>", "loesung": "<p>…</p>"}
    _resolve_field_aliases(blk)
    f += check(blk["type"] == "prediction" and blk.get("question")
                and blk.get("resolution") and "frage" not in blk,
                "vorhersage/frage/loesung → prediction/question/resolution")
    blk = {"type": "task", "task": "<p>Berechne …</p>", "answer": "<p>…</p>"}
    _resolve_field_aliases(blk)
    f += check(blk["type"] == "task" and blk.get("task")
                and blk.get("sample_solution"),
                "task: task/answer → task/sample_solution")
    # Legitimate German blocks stay untouched (no overreach).
    blk = {"type": "table", "caption": "Vergleich", "header": [], "rows": []}
    _resolve_field_aliases(blk)
    f += check(blk.get("caption") == "Vergleich",
                "table.caption stays a field of its own")
    # Glossary marker: English and varied spellings are recognised …
    for marker in ("=== GLOSSARY ===", "===GLOSSAR===", "=== glossary ==="):
        script = f"<p>Text</p>\n{marker}\nFWER :: kurz :: Definition :: l1"
        norm = _normalise_glossary_marker(script)
        f += check("=== GLOSSAR ===" in norm
                    and "FWER :: kurz" in norm.split("=== GLOSSAR ===", 1)[1],
                    f"marker {marker!r} is harvested")
    # … but '===' in running text is NOT mistaken for a marker.
    script = "<p>Der Operator === prüft in JS typgleich.</p>"
    f += check("=== GLOSSAR ===" not in _normalise_glossary_marker(script),
                "'===' in running text stays untouched")
    return f


def test_case_c_findings():
    """Consolidation abort and two validator false alarms.

    Abort: in the critic pass the model answered with valid JSON `null` —
    parse_llm_json then does not raise but returns None, and a `.get` on it
    stood outside the try. The AttributeError broke the whole consolidation
    through asyncio.gather.
    """
    print("consolidation robustness and false alarms")
    from src.llm.json_parser import parse_llm_json
    from src.pipeline.learning_pipeline import LearningPipeline as _L
    from src.unit.validator import validate
    f = 0
    # 1. The root: JSON `null` is a VALID parse result (no raise).
    f += check(parse_llm_json("null", context="test") is None,
                "JSON null parses to None instead of raising (the root of the crash)")
    # 2. Usability guards catch exactly these cases.
    for broken in (None, [], "text", 5):
        f += check(not _L._critic_verdict_usable(broken),
                    f"critic verdict {type(broken).__name__} is skipped")
    f += check(_L._critic_verdict_usable({"score": 3, "findings": []}),
                "a real verdict stays usable")
    for broken in (None, {}, {"questions": []}, {"questions": "x"}, ["f"]):
        f += check(not _L._final_test_usable(broken),
                    "an unusable final test is not set "
                    f"({str(broken)[:20]!r})")
    f += check(_L._final_test_usable(
        {"title": "T", "questions": [{"question": "?", "options": []}]}),
        "a real final test stays usable")

    # 3. D2 false alarm: the formal imperative and English verbs count as a
    #    task.
    def _chart(descr):
        return {"state": "draft", "language": "de", "title": "T",
                "concepts": [{"id": "k1", "name": "Testthema", "concept_class": "K"}],
                "lessons": [{"id": "l1", "title": "L", "concepts": ["k1"],
                               "blocks": [{"type": "chart",
                                            "description": descr,
                                            "spec": {
                    "data": {"values": [{"x": 1, "y": 2}, {"x": 2, "y": 3}]},
                    "mark": "line",
                    "encoding": {"x": {"field": "x", "type": "quantitative"},
                                 "y": {"field": "y", "type": "quantitative"}},
                    "params": [{"name": "alpha", "value": 0.05,
                                "bind": {"input": "range", "min": 0.01,
                                         "max": 0.1, "name": "Alpha"}}]}}]}]}
    for descr, expected, case in (
            ("Stellen Sie verschiedene Werte für α ein und beobachten Sie "
             "den Verlauf.", False, "Sie-Form"),
            ("Set alpha to different values and observe the curve.", False,
             "englische Verben"),
            ("Stelle α auf 0,01 und beobachte die Kurve.", False, "Du-Form"),
            ("Ein Diagramm des korrigierten Niveaus.", True, "ohne Auftrag")):
        b = validate(_chart(descr), node_probe=False)
        has = any("exploration task" in w for w in b.warnings_)
        f += check(has == expected, f"D2 ({case}): warning={expected}")

    # 4. Glossary coverage: the bracket form of the entry covers the concept
    #    name.
    def _unit_glossary(glossary):
        return {"state": "draft", "language": "de", "title": "T",
                "concepts": [{"id": "k5", "concept_class": "K", "name":
                              "Benjamini-Hochberg-Verfahren – "
                              "mathematische Funktionsweise"}],
                "lessons": [{"id": "l1", "title": "L", "concepts": ["k5"],
                               "blocks": [{"type": "text",
                                            "html": "<p>Inhalt.</p>"}]}],
                "glossary": glossary}
    b = validate(_unit_glossary(
        [{"term": "Benjamini-Hochberg-Verfahren (BH-Verfahren)",
          "definition": "…", "short": "…"}]), node_probe=False)
    f += check(not any("no glossary entry" in w for w in b.warnings_),
                "an entry with a parenthetical addition covers the concept name")
    b = validate(_unit_glossary([]), node_probe=False)
    f += check(any("no glossary entry" in w for w in b.warnings_),
                "a really missing entry is still reported")

    # 5. Prompt funnel: the glossary section of the chapter script is harvest
    #    payload and must NEVER go into generation prompts as prose (otherwise
    #    a
    #    text block "Glossar" appears in the last lesson, duplicating the real
    #    hover glossary).
    pipe = object.__new__(_L)
    for marker in ("=== GLOSSAR ===", "=== GLOSSARY ==="):
        script = f"<h2>Lektion</h2><p>Prosa bleibt.</p>\n{marker}\n" \
                 f"FWER :: kurz :: Definition :: l1"
        rest = _L._script_for_prompt(pipe, script)
        f += check("Prosa bleibt" in rest and "FWER ::" not in rest
                    and "GLOSSAR" not in rest,
                    f"glossary section ({marker}) reaches no prompt")
    return f


def test_case_b_findings():
    """A pseudo error blocked the final gate, quoting edge labels downgraded the
    central visual.

    The APA asterisk convention "(* p < .05, ** p < .01, *** p < .001)" is
    subject matter of every statistics unit — a loose bold pattern turned it
    into a format ERROR, and the unit appeared as a DRAFT.
    """
    print("APA asterisks, escaped fields, Mermaid edge labels")
    from src.unit.normalization import strip_md, secure_mermaid
    from src.unit.validator import _format_remnants
    f = 0
    apa = ("<p>Die Sternchen-Konvention (* p &lt; .05, ** p &lt; .01, "
           "*** p &lt; .001) scheint verlässlich.</p>")
    f += check(not _format_remnants(apa),
                "APA asterisks are no Markdown error (final gate blocker)")
    f += check(any("bold" in str(m) for m in _format_remnants("<p>Das ist **wichtig** hier.</p>")),
                "real Markdown bold is still reported")
    f += check(any("italics" in str(m) for m in _format_remnants("<p>Das ist *wichtig* hier.</p>")),
                "real Markdown italics are still reported")
    # strip_md (escaped fields): APA notation stays literally.
    cell = "0,45** und 0,27** (beide signifikant, ** p < .01)"
    new_, _ = strip_md(cell)
    f += check(new_ == cell, "APA asterisks in escaped fields are never stripped")
    new_, _ = strip_md("Das ist **wichtig** und *betont*.")
    f += check(new_ == "Das ist wichtig und betont.",
                "real Markdown is still removed in escaped fields")

    # Mermaid: pipes in the quoted node label stay untouched, real edge labels
    # are still secured.
    code = ('flowchart TD\n'
            '    A[Start] -->|p < 0.05 (zweiseitig)| B[weiter]\n'
            '    B --> C[p = P(Daten | H0) und nicht P(H0 | Daten)]')
    new_, _ = secure_mermaid(code)
    f += check('-->|"p < 0.05 (zweiseitig)"|' in new_,
                "a real edge label with brackets is still quoted")
    f += check('C["p = P(Daten | H0) und nicht P(H0 | Daten)"]' in new_,
                "a node label with pipes stays ONE quoted label")
    f += check(new_.count('"') == 4, "no stray quotes in the result")
    # Idempotence: a second pass (repair loop!) changes nothing — otherwise
    # every repair would be mangled again.
    new2, _ = secure_mermaid(new_)
    f += check(new2 == new_, "the protection is idempotent (repair loop stable)")

    # Redundancy pass: the prompt distinguishes intended resumptions
    # (application and final lessons take concepts up again by design).
    from src.prompts import learning
    p = learning.redundancy_prompt("l1: …")
    f += check("resumptions" in p and "DERIVE" in p,
                "the redundancy prompt separates consolidation from explaining anew")
    return f


def test_validator_never_raises():
    """A critic block patch delivered `questions: [null, …]`, and `_p_quiz`
    called `f.get(...)` — an AttributeError through the patch probe and
    asyncio.gather up to the abort of the consolidation.

    The validator is the protective layer of the pipeline and must not raise
    on ANY input: every broken structure becomes an ERROR of the block —
    then the patch probe discards the broken patch (the right result)
    instead of the run dying.
    """
    print("the validator never raises: null entries at every structural place")
    from src.unit.validator import validate
    f = 0
    vandals = {
        "state": "draft", "language": "de", "title": "T",
        "concepts": [None, {"id": "k1", "name": "Testthema", "concept_class": "K"}],
        "glossary": [None, {"term": "X", "definition": "…", "short": "…"}],
        "modules": [None],
        "final_test": ["kein", "objekt"],
        "lessons": [
            None,
            {"id": "l1", "title": "L", "concepts": ["k1"], "blocks": [
                {"type": "quiz", "questions": [None, {
                    "question": "F?", "multiple": False,
                    "options": [None, {"text": "A", "correct": True,
                                        "feedback": "…"},
                                 {"text": "B", "correct": False,
                                  "feedback": "…"}]}]},
                {"type": "accordion", "items": [None]},
                {"type": "matching", "pairs": [None,
                    {"left": "a", "right": "1"},
                    {"left": "b", "right": "2"}]},
                {"type": "flashcards", "cards": [None]},
                {"type": "prediction", "question": "F?", "resolution": "A",
                 "options": [None, {"text": "x"}, {"text": "y"}]},
                {"type": "simulator", "description": "Stelle a ein",
                 "code": "function modell(p){return {x:[1],series:[]};}",
                 "parameters": [None]},
                {"type": "cloze", "html": "<p>{{1}}</p>",
                 "gaps": ["kein", "objekt"]},
                {"type": "table", "caption": "T", "header": ["a"],
                 "rows": [None, ["x"]]},
            ]}]}
    try:
        b = validate(vandals, node_probe=False)
    except Exception as e:  # noqa: BLE001
        f += check(False, f"validate raises: {type(e).__name__}: {e}")
        return f
    f += check(True, "validate survives the vandal unit without an exception")
    errors = "\n".join(b.errors)
    for location in ("lesson[0]", "questions[0]", "options[0]", "items[0]",
                   "pairs[0]", "cards[0]", "parameters[0]",
                   "concepts[0]", "glossary[0]", "modules[0]"):
        f += check(location in errors and "not an object" in errors,
                    f"null at '{location}' is reported as an error")
    f += check("final_test" in errors, "final test as a list is reported")
    f += check("gaps must be an object" in errors,
                "gaps as a list is reported")
    # The intact sibling entries are still checked for content.
    f += check(not any("block check aborted" in x for x in b.errors),
                "all places caught structurally — the net stayed unused")
    return f


def test_case_a_findings():
    """erDiagram degradation and a critic rubric without anchors; plus the cloze
    solution feature (only after one's own attempt)."""
    print("erDiagram, score anchors, cloze solution")
    from src.prompts import learning
    from src.unit import diagram_types as dtype
    from src.unit.i18n import table_
    from src.unit.normalization import secure_mermaid
    f = 0
    # 1. Non-flow types stay untouched by flowchart heuristics — cardinalities
    #    (||--o{) and attribute blocks are STRUCTURE there.
    er = ("erDiagram\n    DOKUMENT ||--o{ KAPITEL : enthaelt\n"
          "    CHUNK {\n        string chunk_id\n    }")
    new_, _ = secure_mermaid(er)
    f += check("||--o{" in new_ and "<br/>" not in new_ and '"' not in new_,
                "erDiagram: cardinality and attribute block stay intact")
    f += check(secure_mermaid(new_)[0] == new_, "erDiagram: idempotent")
    seq = "sequenceDiagram\n    A->>B: Anfrage (mit Klammern)\n    B-->>A: Antwort"
    f += check(secure_mermaid(seq)[0].count('"') == 0,
                "sequenceDiagram: no flowchart quoting")
    f += check(dtype.detect(er) == "erDiagram" and dtype.detect(
        "flowchart TD\nA-->B") == "flowchart", "type detection carries the gate")
    # Sub/superscript protection still applies to ALL types.
    s, _ = secure_mermaid("erDiagram\n    H\u2080 ||--o{ TEST : x")
    f += check("\u2080" not in s and "H0" in s,
                "Unicode subscripts are replaced in non-flow types as well")

    # 2. Critic rubric: an anchored scale (critics can rate every lesson 1-3).
    p = learning.critic_prompt("[0] text: …", ["K1"], "detailed")
    f += check("4 = solid" in p and "EFFECT ON LEARNING" in p and "are a 4" in p,
                "the score scale is anchored, not only '5 = no findings'")

    # 3. Cloze solution: the button exists, starts locked, is only unlocked in
    #    the check handler; revealing marks the gap as revealed.
    shell = open("assets/shell.html", encoding="utf-8").read()
    f += check('data-solution disabled' in shell,
                "the solution button starts locked (try it yourself first)")
    free = shell.find("btnSolution.disabled = false")
    f += check(0 < shell.find('root.querySelectorAll("input.gap")') < free
                < shell.find("btnSolution.addEventListener"),
                "unlocking sits IN the check handler (at least one attempt)")
    f += check('classList.add("revealed")' in shell
                and "input.gap.revealed" in shell,
                "revealed gaps are marked as revealed, not as solved")
    for lang in ("de", "en", "fr", "es", "it"):
        t = table_(lang)
        f += check(bool(t.get("show_solution")) and bool(t.get("check_before_solution")),
                    f"i18n {lang}: solution texts present")
    return f


def test_sankey_and_single_point():
    """A downgraded Sankey and an exploration game with x:[0] (a point on the
    left).

    The repairable Sankey classes are determined empirically against the
    real Mermaid grammar: decimal comma in the value, unquoted commas in node
    names, arrow syntax. Units, percent signs and thousands separators parse
    and are deliberately NOT touched.
    """
    print("Sankey protection and simulator data points")
    import shutil
    from src.unit.normalization import secure_mermaid
    from src.unit.validator import validate
    f = 0
    new_, _ = secure_mermaid("sankey-beta\nHypothesen,Signifikant,47,5")
    f += check(new_.endswith("Hypothesen,Signifikant,47.5"),
                "decimal comma in the value is repaired")
    code = ("sankey-beta\nHypothesen,Publiziert,150\n"
            "Signifikant, aber klein,Publiziert,80\n"
            "Hypothesen,Signifikant, aber klein,90")
    new_, _ = secure_mermaid(code)
    f += check('"Signifikant, aber klein",Publiziert,80' in new_
                and 'Hypothesen,"Signifikant, aber klein",90' in new_,
                "label commas are quoted unambiguously through known nodes")
    f += check(secure_mermaid(new_)[0] == new_, "Sankey protection idempotent")
    new_, _ = secure_mermaid("sankey-beta\nHypothesen --> Signifikant: 280")
    f += check(new_.endswith("Hypothesen,Signifikant,280"),
                "arrow syntax is rewritten to CSV")
    # Anything ambiguous is left to the repair run; whatever parses stays
    # literally.
    ambiguous = "sankey-beta\nA, B,C, D,10"
    f += check(secure_mermaid(ambiguous)[0] == ambiguous,
                "an unresolvable line is not changed")
    unit_ = "sankey-beta\nHypothesen,Signifikant,280 Studien"
    f += check(secure_mermaid(unit_)[0] == unit_,
                "parsing variants (unit in the value) stay untouched")
    # Umlauts: the sankey lexer accepts them in NO form (bisected) —
    # transliteration by German convention instead of degradation.
    new_, _ = secure_mermaid('sankey-beta\n"Als relevant ausgewählt",Größe,80')
    f += check(new_.isascii() and "ausgewaehlt" in new_ and "Groesse" in new_,
                "Sankey umlauts are transliterated (ae/oe/ue/ss)")
    # Inner quotation marks in quoted labels: resolve in a version-independent
    # way without the odd-shape form (id>label]) reaching into the repaired
    # label.
    fl, log_ = secure_mermaid(
        'flowchart TD\nB["Große Studie<br/>n>"200<br/>Effekt: mittel\'"] --> C[x]')
    f += check("n>'200" in fl and fl.splitlines()[1].count('"') == 2
                and secure_mermaid(fl)[0] == fl,
                "mixed quotes in the label are resolved cleanly ONCE")
    fl, _ = secure_mermaid("flowchart LR\nA>Achtung (wichtig)] --> B[x]")
    f += check('A>"Achtung (wichtig)"]' in fl,
                "legitimate odd-shape nodes are still secured")
    # Mermaid type name as the block type: intact code becomes a diagram block
    # — but ONLY if the type name is in the catalogue (the degradation path
    # remains).
    from src.pipeline.learning_pipeline import _resolve_type_alias as _ta
    blk = {"type": "timeline", "code": "timeline\n  2017 : Attention is all you need"}
    _ta(blk)
    f += check(blk["type"] == "diagram" and blk.get("engine") == "mermaid",
                "Mermaid type name as block type becomes diagram/mermaid")
    blk = {"type": "fantasieform", "code": "flowchart TD\nA-->B"}
    _ta(blk)
    f += check(blk["type"] == "fantasieform",
                "a really unknown type is left to the degradation path")
    # quadrantChart: the colon replacement hits ONLY label lines.
    q, _ = secure_mermaid('quadrantChart\ntitle A: B\n"P: Q": [0.1, 0.2]')
    f += check("title A – B" in q and '"P: Q": [' in q
                and secure_mermaid(q)[0] == q,
                "quadrant colons: labels replaced, point-line syntax stays")

    # Single-point simulator: the real case x:[0] with one value per series.
    if shutil.which("node") is None:
        return f
    unit = {"state": "draft", "language": "de", "title": "T",
            "concepts": [{"id": "k1", "name": "Testthema", "concept_class": "K"}],
            "lessons": [{"id": "l1", "title": "L", "concepts": ["k1"],
                           "blocks": [{
                "type": "simulator", "title": "Erkundungsspiel",
                "description": "Stelle n ein und beobachte den p-Wert.",
                "parameters": [{"name": "n", "label": "Stichprobengröße",
                               "min": 10, "max": 500, "step": 10, "value": 50}],
                "code": "function modell(p){const se=Math.sqrt(2/p.n);"
                        "return {x:[0],series:[{name:'Unterschied',"
                        "values:[0.5]},{name:'KI-oben',values:[0.5+1.96*se]}]};}",
                "output": {"kind": "line", "x_label": "Kombination",
                            "y_label": "Effekt"}}]}]}
    b = validate(unit, node_probe=True)
    f += check(any("data point" in w and "sweep" in w for w in b.warnings_),
                "x:[0] single point is reported as a missing sweep")
    curve = dict(unit)
    curve["lessons"][0]["blocks"][0] = dict(
        unit["lessons"][0]["blocks"][0],
        code="function modell(p){const x=[],y=[];for(let i=0;i<12;i++){"
             "x.push(10+i*40);y.push(1/Math.sqrt(x[i]));}"
             "return {x:x,series:[{name:'SE',values:y}]};}")
    b = validate(curve, node_probe=True)
    f += check(not any("data point" in w for w in b.warnings_),
                "a real curve triggers no message")
    return f


def test_lessons_never_lost():
    """The most expensive case: revisions deleted whole lessons."""
    print("revisions can no longer delete a lesson")
    from src.pipeline.learning_pipeline import LearningPipeline as _L
    alt = {"id": "l1", "title": "T", "blocks":
           [{"type": "text", "html": "<p>" + ("Wort " * 400) + "</p>"}]
           + [{"type": "quiz", "questions": []}] * 5}
    cases = [({}, "leere Antwort"), ({"title": "T"}, "nur Titel"),
              ({"title": "T", "blocks": []}, "keine Blöcke"),
              ({"title": "T", "blocks": alt["blocks"][:1]}, "Blöcke verloren"),
              ("kein Objekt", "kein Objekt")]
    f = 0
    for new_, name in cases:
        ok, _ = _L._revision_acceptable(alt, new_)
        f += check(not ok, f"{name} is discarded")
    ok, _ = _L._revision_acceptable(alt, {"title": "T neu", "blocks": alt["blocks"]})
    f += check(ok, "a complete revision is accepted")
    return f


if __name__ == "__main__":
    errors = (test_all_findings() + test_real_errors_remain()
              + test_terminology_case_d() + test_terminology_stays_general()
              + test_glossary_variants_stay_general()
              + test_enrichment_does_not_clump()
              + test_detail_plan_density_check() + test_gap_protocol_vocabulary()
              + test_english_unit_nomenclature()
              + test_case_c_findings()
              + test_case_b_findings()
              + test_validator_never_raises()
              + test_case_a_findings()
              + test_sankey_and_single_point()
              + test_lessons_never_lost())
    print(f"\n{'REGRESSION OK' if not errors else f'{errors} FAILED'}")
    sys.exit(1 if errors else 0)
