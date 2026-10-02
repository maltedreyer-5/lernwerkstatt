# -*- coding: utf-8 -*-
"""German field names in model output, mapped to the English format.

The prompts ask for English field names, but models sometimes answer in the
language of the unit — for a German unit that means German keys, including
the names this format used before it became English. Every object parsed
from model output passes through `translate_legacy_keys`: a German key is
renamed only if the English key is not present as well. Vega-Lite specs
(`spec`) are left untouched; their keys belong to Vega, not to this format.

This table is data. Generated from the rename table of the format change;
it must not be run through any automatic renaming.
"""
from __future__ import annotations

LEGACY_KEYS: dict[str, str] = {
    "nach_block": "after_block",
    "abdeckung": "coverage", "abgebrochen": "aborted", "abgelehnt": "rejected", "abgeschnitten": "truncated",
    "abschluss": "final", "abschlusstest": "final_test", "akkordeon": "accordion", "aktualisiert": "updated",
    "angelegt": "created", "angereichert": "enriched", "anreicherung_verworfen": "enrichment_discarded", "anteil": "share",
    "antwort": "response", "antwort_pruefen": "check_answer", "antworten": "answers", "anwenden": "apply",
    "anwendungsteil": "application_part", "art": "kind", "auch_richtig": "also_correct", "aufgabe": "task",
    "aufgaben": "tasks", "aufloesung": "resolution", "aufloesung_ein": "resolution_shown", "aufloesung_zeigen": "show_resolution",
    "auftrag": "job", "auftrag_nr": "job_no", "auftrag_nummer": "job_number", "aus_gespeichertem_lauf": "from_saved_run",
    "ausfuehrlich": "detailed", "ausgabe": "output", "aussage": "claim", "balken": "bar",
    "baustein_fehler": "component_error", "befund": "finding", "befunde": "findings", "begriff": "term",
    "begruendung": "rationale", "beitrag": "contribution", "bekannte_konzepte": "known_concepts", "beleg": "evidence",
    "belegt": "evidenced", "beschreibung": "description", "beschriftung": "caption", "bibliothek_fehlt": "library_missing",
    "blockliste": "blocklist", "bloecke": "blocks", "briefing_antworten": "briefing_answers", "darstellung": "display",
    "darstellungsbegruendung": "display_rationale", "dauer": "duration", "dauer_minuten": "duration_minutes", "degradationen": "degradations",
    "diagramm": "diagram", "diagramm_fehler": "diagram_error", "diagramme": "diagrams", "dokument": "document",
    "dubletten": "duplicates", "einfuehrung": "introduction", "eingabe": "input", "einheit": "unit",
    "eintraege": "entries", "elemente": "items", "endlich": "finite", "entwurf": "draft",
    "erfuellt": "fulfilled", "ergebnis_erstellt": "result_created", "ergebnisse": "results", "erklaerung": "explanation",
    "ersatz": "substitute", "ersetzungen": "replacements", "erstellt_mit": "created_with", "erweiterung": "extension",
    "etabliert": "established", "fall": "case", "fallaufgabe": "case_task", "feedback_lesen": "read_feedback",
    "fehler": "errors", "fehleranalyse": "error_analysis", "feinplaene": "detail_plans", "fertig": "done",
    "festlegen": "commit", "formel": "formula", "formeln": "formulas", "fortschritt_zurueck": "reset_progress",
    "frage": "question", "fragen": "questions", "fundstelle": "occurrence", "geaendert": "changed",
    "gerettet": "rescued", "gesetzt": "fixed_terms", "gestartet": "started_at", "glossar": "glossary",
    "glossar_filter": "glossary_filter", "glossar_pfeil": "glossary_arrow", "glossar_platzhalter": "glossary_placeholder", "grafik_fehler": "graphic_error",
    "grund": "reason", "herkunft": "provenance", "hinten": "back", "hinweis": "note",
    "hinweise": "hints", "hoehe": "height", "ignorieren": "ignore", "ihre_loesung": "your_solution",
    "ihre_vorhersage": "your_prediction", "im_glossar": "in_glossary", "inhalt": "content", "inhaltspunkte": "content_points",
    "interaktion": "interaction", "interaktiv": "interactive", "interaktive_grafik": "interactive_graphic", "interferenz": "interference",
    "interferenz_begruendung": "interference_rationale", "inventar_index": "inventory_index", "je_lektion": "per_lesson", "kandidaten": "candidates",
    "kapitel": "chapters", "kapitel_meta": "chapter_meta", "karten": "cards", "kein_terminus": "no_term",
    "keine_funktion": "no_function", "keine_treffer": "no_hits", "klasse": "concept_class", "klassen": "classes",
    "knoten": "nodes", "koennen_danach": "can_afterwards", "kommentar": "comment", "kompakt": "compact",
    "kontext": "context", "konzept": "concept", "konzepte": "concepts", "kopf": "header",
    "korpus": "corpus", "korrekt": "correct", "korrektur": "correction", "kriterium": "criterion",
    "kuerzung": "shortening", "kurz": "short", "kurzabriss": "summary", "kurzbeschreibung": "short_description",
    "laeufe": "runs", "leer": "empty", "lehrskript": "teaching_script", "leitfrage": "guiding_question",
    "lekt_cache": "lesson_cache", "lektion": "lesson", "lektionen": "lessons", "lerneinheit": "learning_unit",
    "lernziele": "learning_objectives", "linie": "line", "links": "left", "loesung_ein": "solution_shown",
    "loesung_erst_pruefen": "check_before_solution", "loesung_zeigen": "show_solution", "loslegen": "get_started", "ls_befunde": "ls_findings",
    "luecke": "gap", "luecken": "gaps", "luecken_richtig": "gaps_correct", "lueckentext": "cloze",
    "läuft": "running", "material_auszuege": "material_excerpts", "material_kontext": "material_context", "material_volltext": "material_full_text",
    "medienplan": "media_plan", "mehrfach": "multiple", "merke": "key_point", "modell": "model",
    "modelle": "models", "module": "modules", "musterloesung": "sample_solution", "musterloesung_ein": "sample_solution_shown",
    "musterloesung_zeigen": "show_sample_solution", "nachschlagen": "look_up", "neue_begriffe": "new_terms", "neue_bloecke": "new_blocks",
    "nummer": "number", "offen": "open", "offene_fragen": "open_questions", "optionen": "options",
    "ordner": "folder", "paare": "pairs", "parameter": "parameters", "pfad": "path",
    "profil": "profile", "pruefbericht": "check_report", "pruefen": "check", "pruefkriterien": "check_criteria",
    "quelle": "source", "quellen": "sources", "quoten": "ratios", "rechts": "right",
    "redundanz": "redundancy", "repariert": "repaired", "roh": "raw", "rolle": "role",
    "roter_faden": "common_thread", "schlagwoerter": "keywords", "serien": "series", "signatur": "signature",
    "skript": "script", "skript_teile": "script_parts", "skripte": "scripts", "spanne": "span",
    "sprache": "language", "stand": "state", "stelle": "location", "suche_label": "search_label",
    "suche_platzhalter": "search_placeholder", "t_skript": "t_script", "tabelle": "table", "terminologie": "terminology",
    "tiefenprofil": "depth_profile", "titel": "title", "titel_der_einheit": "unit_title", "total_leer": "total_empty",
    "total_leer_gerettet": "total_empty_rescued", "typ": "type", "typen": "types", "ueberblick": "overview",
    "uebersprungene_rueckfragen": "skipped_follow_ups", "uebungen": "exercises", "uebungen_modul": "exercises_module", "umdrehen": "flip",
    "unbekannte_konzepte": "unknown_concepts", "unbekannter_typ": "unknown_type", "ungueltige_ausgabe": "invalid_output", "unterbrochen": "interrupted",
    "urteile": "verdicts", "variante": "variant", "verlauf": "history", "verluste": "losses",
    "verwaist": "orphaned", "verworfen": "discarded", "volltext": "full_text", "von": "from",
    "vorausgesetzt": "prerequisite_label", "voraussetzt": "requires", "voraussetzungen": "prerequisites", "vorhersage": "prediction",
    "vorne": "front", "vorschlag": "proposal", "vorwissen": "prior_knowledge", "waehlen": "select",
    "warnung": "warning", "warnungen": "warnings", "wartet": "waiting", "weiter": "next",
    "weitere_bloecke": "further_blocks", "weitere_lektionen": "more_lessons", "wert": "value", "werte": "values",
    "widerspricht": "contradicts", "wiederaufnahme": "resumption", "woerter": "words", "zeilen": "rows",
    "zeitbudget": "time_budget", "ziele_lektion": "lesson_objectives", "zielniveau": "target_level", "zum_ueberblick": "to_overview",
    "zuordnung": "matching", "zuordnung_fuer": "matching_for", "zurueck": "back", "zusammenfassung": "summary",
}

# Values that changed together with their keys.
LEGACY_VALUES: dict[str, dict[str, str]] = {
    "variant": {"merke": "key_point", "warnung": "warning"},
    "depth_profile": {"kompakt": "compact", "ausfuehrlich": "detailed"},
    "state": {"in-arbeit": "draft"},
    "kind": {"linie": "line", "balken": "bar", "tabelle": "table"},
}

_UNTOUCHED = {"spec"}


def translate_legacy_keys(obj):
    """Returns obj with German format keys (and their values) in English."""
    if isinstance(obj, list):
        return [translate_legacy_keys(x) for x in obj]
    if not isinstance(obj, dict):
        return obj
    out = {}
    for key, value in obj.items():
        new = LEGACY_KEYS.get(key, key) if isinstance(key, str) else key
        if new != key and new in obj:
            new = key                      # both present: keep the English one untouched
        if key in _UNTOUCHED or new in _UNTOUCHED:
            out[new] = value
            continue
        value = translate_legacy_keys(value)
        if isinstance(value, str) and new in LEGACY_VALUES:
            value = LEGACY_VALUES[new].get(value, value)
        out[new] = value
    return out
