# -*- coding: utf-8 -*-
"""Interface texts of the delivered learning unit in five languages.

Without this table a Spanish learning unit would have German controls —
which looks like a bug, not like a missing feature.

The table is put into the file as `const T = {…}` during assembly;
`shell.html` accesses it only through `T.<key>`. That makes completeness
checkable: a new key without a translation shows up in a test, not with
the learner.

Terms from learning psychology are translated idiomatically, not
literally: "Das können Sie danach" becomes "What you'll be able to do" in
English, not "That you can afterwards".
"""
from __future__ import annotations

import json

LANGUAGES = ("de", "en", "fr", "es", "it")

# Display name per language, for the select field in the interface.
CHOICES = [("de", "Deutsch"), ("en", "English"), ("fr", "Français"),
           ("es", "Español"), ("it", "Italiano")]

TEXTS: dict[str, dict[str, str]] = {
    # ── Navigation and frame ──────────────────────────────────────────
    "overview":        {"de": "Überblick", "en": "Overview", "fr": "Vue d’ensemble",
                          "es": "Resumen", "it": "Panoramica"},
    "to_overview":    {"de": "Zum Überblick", "en": "Back to overview",
                          "fr": "Vue d’ensemble", "es": "Ir al resumen",
                          "it": "Alla panoramica"},
    "learning_unit":       {"de": "Lerneinheit", "en": "Learning unit",
                          "fr": "Unité d’apprentissage", "es": "Unidad de aprendizaje",
                          "it": "Unità didattica"},
    "lessons":         {"de": "Lektionen", "en": "Lessons", "fr": "Leçons",
                          "es": "Lecciones", "it": "Lezioni"},
    "more_lessons": {"de": "Weitere Lektionen", "en": "More lessons",
                          "fr": "Autres leçons", "es": "Más lecciones",
                          "it": "Altre lezioni"},
    "modules":            {"de": "Module", "en": "Modules", "fr": "Modules",
                          "es": "Módulos", "it": "Moduli"},
    "duration":             {"de": "Dauer", "en": "Duration", "fr": "Durée",
                          "es": "Duración", "it": "Durata"},
    "final":         {"de": "Abschluss", "en": "Final test", "fr": "Évaluation finale",
                          "es": "Prueba final", "it": "Test finale"},
    "get_started":          {"de": "Loslegen ›", "en": "Start ›", "fr": "Commencer ›",
                          "es": "Empezar ›", "it": "Inizia ›"},
    "next":            {"de": "Weiter ›", "en": "Next ›", "fr": "Suivant ›",
                          "es": "Siguiente ›", "it": "Avanti ›"},
    "exercises_module":    {"de": "Übungen · Modul ", "en": "Exercises · Module ",
                          "fr": "Exercices · Module ", "es": "Ejercicios · Módulo ",
                          "it": "Esercizi · Modulo "},
    "apply":          {"de": "Anwenden und Abtesten", "en": "Apply and check",
                          "fr": "Appliquer et vérifier", "es": "Aplicar y comprobar",
                          "it": "Applicare e verificare"},
    "reset_progress": {"de": "Fortschritt zurücksetzen", "en": "Reset progress",
                            "fr": "Réinitialiser la progression",
                            "es": "Restablecer el progreso",
                            "it": "Azzera i progressi"},

    # ── Objectives and prerequisites ──────────────────────────────────────
    "can_afterwards":    {"de": "Das können Sie danach",
                          "en": "What you’ll be able to do",
                          "fr": "Ce que vous saurez faire",
                          "es": "Lo que sabrá hacer",
                          "it": "Che cosa saprà fare"},
    "prerequisite_label":     {"de": "Vorausgesetzt wird", "en": "Prerequisites",
                          "fr": "Prérequis", "es": "Requisitos previos",
                          "it": "Prerequisiti"},
    "lesson_objectives":     {"de": "Ziele dieser Lektion", "en": "Objectives of this lesson",
                          "fr": "Objectifs de cette leçon",
                          "es": "Objetivos de esta lección",
                          "it": "Obiettivi di questa lezione"},

    # ── Search and glossary ──────────────────────────────────────────────
    "search_placeholder": {"de": "In der Einheit suchen…", "en": "Search this unit…",
                          "fr": "Rechercher dans l’unité…", "es": "Buscar en la unidad…",
                          "it": "Cerca nell’unità…"},
    "search_label":       {"de": "In der Lerneinheit suchen", "en": "Search the learning unit",
                          "fr": "Rechercher dans l’unité d’apprentissage",
                          "es": "Buscar en la unidad de aprendizaje",
                          "it": "Cerca nell’unità didattica"},
    "no_hits":     {"de": "Keine Treffer für", "en": "No results for",
                          "fr": "Aucun résultat pour", "es": "Sin resultados para",
                          "it": "Nessun risultato per"},
    "glossary":           {"de": "Glossar", "en": "Glossary", "fr": "Glossaire",
                          "es": "Glosario", "it": "Glossario"},
    "glossary_arrow":     {"de": "Glossar ›", "en": "Glossary ›", "fr": "Glossaire ›",
                          "es": "Glosario ›", "it": "Glossario ›"},
    "glossary_filter":    {"de": "Glossar filtern", "en": "Filter glossary",
                          "fr": "Filtrer le glossaire", "es": "Filtrar el glosario",
                          "it": "Filtra il glossario"},
    "glossary_placeholder": {"de": "Begriff oder Stichwort filtern…",
                            "en": "Filter by term or keyword…",
                            "fr": "Filtrer par terme ou mot-clé…",
                            "es": "Filtrar por término o palabra clave…",
                            "it": "Filtra per termine o parola chiave…"},
    "look_up":      {"de": "Nachschlagen", "en": "Reference", "fr": "Références",
                          "es": "Consulta", "it": "Consultazione"},
    "in_glossary":        {"de": "Im Glossar nachschlagen ›", "en": "Look up in glossary ›",
                          "fr": "Consulter le glossaire ›", "es": "Consultar el glosario ›",
                          "it": "Cerca nel glossario ›"},

    # ── Tasks and feedback ──────────────────────────────────────
    "question":             {"de": "Frage", "en": "Question", "fr": "Question",
                          "es": "Pregunta", "it": "Domanda"},
    "response":           {"de": "Antwort", "en": "Answer", "fr": "Réponse",
                          "es": "Respuesta", "it": "Risposta"},
    "check_answer":   {"de": "Antwort prüfen", "en": "Check answer",
                          "fr": "Vérifier la réponse", "es": "Comprobar la respuesta",
                          "it": "Verifica la risposta"},
    "check":           {"de": "Prüfen", "en": "Check", "fr": "Vérifier",
                          "es": "Comprobar", "it": "Verifica"},
    "read_feedback":    {"de": "Lies das Feedback bei den markierten Antworten.",
                          "en": "Read the feedback on the marked answers.",
                          "fr": "Lisez le retour sur les réponses signalées.",
                          "es": "Lea los comentarios en las respuestas marcadas.",
                          "it": "Legga il riscontro sulle risposte segnalate."},
    "task":           {"de": "Aufgabe", "en": "Exercise", "fr": "Exercice",
                          "es": "Ejercicio", "it": "Esercizio"},
    "note":           {"de": "Hinweis", "en": "Hint", "fr": "Indice",
                          "es": "Pista", "it": "Suggerimento"},
    "your_solution":      {"de": "Ihre Lösung", "en": "Your answer", "fr": "Votre réponse",
                          "es": "Su respuesta", "it": "La sua risposta"},
    "show_sample_solution": {"de": "Musterlösung anzeigen", "en": "Show model answer",
                             "fr": "Afficher la réponse type",
                             "es": "Mostrar la respuesta modelo",
                             "it": "Mostra la risposta modello"},
    "sample_solution":     {"de": "Musterlösung:", "en": "Model answer:",
                          "fr": "Réponse type :", "es": "Respuesta modelo:",
                          "it": "Risposta modello:"},
    "sample_solution_shown": {"de": "Musterlösung eingeblendet", "en": "Model answer shown",
                          "fr": "Réponse type affichée", "es": "Respuesta modelo mostrada",
                          "it": "Risposta modello mostrata"},

    # ── Cloze ────────────────────────────────────────────────────
    "cloze":       {"de": "Lückentext", "en": "Fill in the blanks",
                          "fr": "Texte à trous", "es": "Texto con huecos",
                          "it": "Testo da completare"},
    "gap":            {"de": "Lücke", "en": "Blank", "fr": "Trou",
                          "es": "Hueco", "it": "Spazio"},
    "gaps_correct":   {"de": "Lücken richtig.", "en": "blanks correct.",
                          "fr": "trous corrects.", "es": "huecos correctos.",
                          "it": "spazi corretti."},
    "from":               {"de": "from", "en": "of", "fr": "sur", "es": "de", "it": "su"},
    "show_solution":    {"de": "Lösung anzeigen", "en": "Show solution",
                          "fr": "Afficher la solution", "es": "Mostrar la solución",
                          "it": "Mostra la soluzione"},
    "check_before_solution": {"de": "Erst selbst versuchen — mindestens einmal prüfen",
                          "en": "Try it yourself first — check at least once",
                          "fr": "Essayez d'abord vous-même — vérifiez au moins une fois",
                          "es": "Inténtelo primero — compruebe al menos una vez",
                          "it": "Provi prima da solo — verifichi almeno una volta"},
    "solution_shown":       {"de": "Lösung eingeblendet", "en": "Solution shown",
                          "fr": "Solution affichée", "es": "Solución mostrada",
                          "it": "Soluzione mostrata"},
    "also_correct":      {"de": "auch richtig:", "en": "also correct:",
                          "fr": "aussi correct :", "es": "también correcto:",
                          "it": "corretto anche:"},

    # ── Matching ──────────────────────────────────────────────────────
    "matching_for":    {"de": "Zuordnung für", "en": "Match for",
                          "fr": "Correspondance pour", "es": "Correspondencia para",
                          "it": "Abbinamento per"},

    # ── Vorhersage ─────────────────────────────────────────────────────
    "prediction":        {"de": "Vorhersage", "en": "Prediction", "fr": "Prédiction",
                          "es": "Predicción", "it": "Previsione"},
    "your_prediction":   {"de": "Ihre Vorhersage", "en": "Your prediction",
                          "fr": "Votre prédiction", "es": "Su predicción",
                          "it": "La sua previsione"},
    "commit":         {"de": "Legen Sie sich fest, bevor Sie auflösen …",
                          "en": "Commit to an answer before revealing …",
                          "fr": "Décidez-vous avant de révéler la réponse …",
                          "es": "Decídase antes de ver la solución …",
                          "it": "Si decida prima di rivelare la soluzione …"},
    "show_resolution": {"de": "Auflösung anzeigen", "en": "Reveal answer",
                          "fr": "Révéler la réponse", "es": "Ver la solución",
                          "it": "Mostra la soluzione"},
    "resolution_shown":    {"de": "Auflösung eingeblendet", "en": "Answer revealed",
                          "fr": "Réponse révélée", "es": "Solución mostrada",
                          "it": "Soluzione mostrata"},

    # ── Error messages in the browser ─────────────────────────────────────
    "graphic_error":     {"de": "Grafik konnte nicht gezeichnet werden:",
                          "en": "Chart could not be rendered:",
                          "fr": "Le graphique n’a pas pu être affiché :",
                          "es": "No se pudo dibujar el gráfico:",
                          "it": "Impossibile disegnare il grafico:"},
    "diagram_error":   {"de": "Diagramm-Fehler:", "en": "Diagram error:",
                          "fr": "Erreur de diagramme :", "es": "Error de diagrama:",
                          "it": "Errore nel diagramma:"},
    "library_missing":  {"de": "Grafik-Bibliothek nicht eingebunden.",
                          "en": "Charting library not included.",
                          "fr": "Bibliothèque graphique non incluse.",
                          "es": "Biblioteca de gráficos no incluida.",
                          "it": "Libreria grafica non inclusa."},
    "interactive_graphic": {"de": "Interaktive Grafik:", "en": "Interactive chart:",
                           "fr": "Graphique interactif :", "es": "Gráfico interactivo:",
                           "it": "Grafico interattivo:"},
    "no_function":    {"de": "code enthält keine Funktion",
                          "en": "code contains no function",
                          "fr": "le code ne contient aucune fonction",
                          "es": "el código no contiene ninguna función",
                          "it": "il codice non contiene alcuna funzione"},
    "invalid_output": {"de": "Ungültige Ausgabeform des Modells.",
                           "en": "Invalid output format from the model.",
                           "fr": "Format de sortie du modèle non valide.",
                           "es": "Formato de salida del modelo no válido.",
                           "it": "Formato di output del modello non valido."},
    "component_error":   {"de": "Dieser Baustein konnte nicht dargestellt werden.",
                          "en": "This element could not be displayed.",
                          "fr": "Cet élément n’a pas pu être affiché.",
                          "es": "Este elemento no se pudo mostrar.",
                          "it": "Questo elemento non ha potuto essere visualizzato."},
    # ── Handout (Markdown/Word) ────────────────────────────────────────
    "script":            {"de": "Skript", "en": "Script", "fr": "Support de cours",
                          "es": "Guion", "it": "Dispensa"},
    "chapters":           {"de": "Kapitel", "en": "Chapter", "fr": "Chapitre",
                          "es": "Capítulo", "it": "Capitolo"},

    "select":           {"de": "– wählen –", "en": "– select –", "fr": "– choisir –",
                          "es": "– elegir –", "it": "– scegli –"},
    "back":           {"de": "‹ Zurück", "en": "‹ Back", "fr": "‹ Retour",
                          "es": "‹ Atrás", "it": "‹ Indietro"},
    "flip":          {"de": "Umdrehen", "en": "Flip", "fr": "Retourner",
                          "es": "Girar", "it": "Gira"},
    # ── Herkunftsvermerk (Handout) ─────────────────────────────────────
    "created_with":      {"de": "Erstellt mit", "en": "Created with", "fr": "Créé avec",
                          "es": "Creado con", "it": "Creato con"},
    "models":           {"de": "Modelle", "en": "Models", "fr": "Modèles",
                          "es": "Modelos", "it": "Modelli"},
    "unknown_type":   {"de": "Unbekannter Blocktyp:", "en": "Unknown block type:",
                          "fr": "Type de bloc inconnu :", "es": "Tipo de bloque desconocido:",
                          "it": "Tipo di blocco sconosciuto:"},
    # ── callouts, results, hints (shell) ──
    "label_key_point":  {"de": "Merke", "en": "Key point", "fr": "À retenir", "es": "Para recordar", "it": "Da ricordare"},
    "label_warning":    {"de": "Achtung", "en": "Caution", "fr": "Attention", "es": "Atención", "it": "Attenzione"},
    "quiz_result":      {"de": "{n} von {total} richtig.", "en": "{n} of {total} correct.",
                         "fr": "{n} sur {total} correctes.", "es": "{n} de {total} correctas.",
                         "it": "{n} su {total} corrette."},
    "well_done":        {"de": "Gut gemacht!", "en": "Well done!", "fr": "Bravo !", "es": "¡Bien hecho!", "it": "Ben fatto!"},
    "matching_result":  {"de": "{n} von {total} Zuordnungen richtig.", "en": "{n} of {total} matches correct.",
                         "fr": "{n} associations correctes sur {total}.", "es": "{n} de {total} asignaciones correctas.",
                         "it": "{n} abbinamenti corretti su {total}."},
    "hint_n":           {"de": "Hinweis {n}", "en": "Hint {n}", "fr": "Indice {n}", "es": "Pista {n}", "it": "Suggerimento {n}"},
    # ── Navigation, saving, accessibility ──
    "final_test":       {"de": "Abschlusstest", "en": "Final test", "fr": "Test final", "es": "Prueba final",
                         "it": "Test finale"},
    "contents":         {"de": "Inhalt", "en": "Contents", "fr": "Sommaire", "es": "Contenido", "it": "Indice"},
    "learning_path":    {"de": "Lernpfad", "en": "Learning path", "fr": "Parcours", "es": "Itinerario de aprendizaje",
                         "it": "Percorso di apprendimento"},
    "lesson_n_of":      {"de": "Lektion {n} von {total}", "en": "Lesson {n} of {total}", "fr": "Leçon {n} sur {total}",
                         "es": "Lección {n} de {total}", "it": "Lezione {n} di {total}"},
    "saved_locally":    {"de": "Stand wird nur in diesem Browser gespeichert.",
                         "en": "Progress is stored only in this browser.",
                         "fr": "La progression n'est enregistrée que dans ce navigateur.",
                         "es": "El progreso solo se guarda en este navegador.",
                         "it": "I progressi vengono salvati solo in questo browser."},
    "stored_note":      {"de": "(wird nur in diesem Browser gespeichert)", "en": "(stored only in this browser)",
                         "fr": "(enregistré uniquement dans ce navigateur)", "es": "(solo se guarda en este navegador)",
                         "it": "(salvato solo in questo browser)"},
    "flip_card":        {"de": "Karteikarte umdrehen", "en": "Flip the card", "fr": "Retourner la carte",
                         "es": "Dar la vuelta a la tarjeta", "it": "Girare la scheda"},
    "exercises_lede":   {"de": "Erst selbst festlegen bzw. lösen, dann aufdecken — der Lerngewinn steckt im Vergleich mit der eigenen Antwort.",
                         "en": "Commit to your own answer or solution first, then reveal — the learning lies in comparing the two.",
                         "fr": "Engagez-vous d'abord sur votre propre réponse ou solution, puis dévoilez — on apprend en comparant les deux.",
                         "es": "Primero comprométase con su propia respuesta o solución y después revele: se aprende al comparar ambas.",
                         "it": "Prima impegnatevi con la vostra risposta o soluzione, poi scopritela: si impara confrontando le due."},
    "correct_title":    {"de": "richtig", "en": "correct", "fr": "correct", "es": "correcto", "it": "corretto"},
    "not_yet_correct":  {"de": "noch nicht richtig", "en": "not correct yet", "fr": "pas encore correct",
                         "es": "todavía no es correcto", "it": "non ancora corretto"},
    "sim_code_error":   {"de": "Simulator-Code fehlerhaft:", "en": "Simulator code faulty:",
                         "fr": "Code du simulateur erroné :", "es": "Código del simulador erróneo:",
                         "it": "Codice del simulatore errato:"},
    "sim_calc_error":   {"de": "Fehler bei der Berechnung:", "en": "Error in the calculation:",
                         "fr": "Erreur de calcul :", "es": "Error en el cálculo:", "it": "Errore nel calcolo:"},
    "error_analysis":   {"de": "Fehleranalyse", "en": "Error analysis", "fr": "Analyse d’erreur",
                         "es": "Análisis de errores", "it": "Analisi degli errori"},
    # ── provenance (assembler) ──
    "prov_created":     {"de": "Erstellt am {date}", "en": "Created on {date}", "fr": "Créé le {date}",
                         "es": "Creado el {date}", "it": "Creato il {date}"},
    "prov_sources":     {"de": "Quellen: {sources}", "en": "Sources: {sources}", "fr": "Sources : {sources}",
                         "es": "Fuentes: {sources}", "it": "Fonti: {sources}"},
    "prov_no_sources":  {"de": "Basiert auf Modellwissen ohne verbindliche Quelldokumente",
                         "en": "Based on model knowledge without authoritative source documents",
                         "fr": "Fondé sur les connaissances du modèle, sans documents sources de référence",
                         "es": "Basado en el conocimiento del modelo, sin documentos fuente de referencia",
                         "it": "Basato sulla conoscenza del modello, senza documenti di riferimento"},
    "prov_ai":          {"de": "Interaktive Lerneinheit, generiert mit KI-Unterstützung — Inhalte vor verbindlicher Nutzung fachlich prüfen.",
                         "en": "Interactive learning unit, generated with AI assistance — check the content before relying on it.",
                         "fr": "Unité d’apprentissage interactive, générée avec l’aide de l’IA — vérifier le contenu avant tout usage engageant.",
                         "es": "Unidad de aprendizaje interactiva, generada con ayuda de IA — revisar el contenido antes de un uso vinculante.",
                         "it": "Unità di apprendimento interattiva, generata con il supporto dell’IA — verificare i contenuti prima di un uso vincolante."},
    "source_material":  {"de": "Unterlagen des Users", "en": "the user’s material", "fr": "documents de l’utilisateur",
                         "es": "materiales del usuario", "it": "materiali dell’utente"},
    "source_model":     {"de": "Modellwissen", "en": "model knowledge", "fr": "connaissances du modèle",
                         "es": "conocimiento del modelo", "it": "conoscenza del modello"},
    # ── placeholder for a block that cannot be displayed (degradation) ──
    "not_displayable":  {"de": "Baustein nicht darstellbar.", "en": "Component cannot be displayed.",
                         "fr": "Élément non affichable.", "es": "Componente no se puede mostrar.",
                         "it": "Componente non visualizzabile."},
    "not_displayable_diagram":   {"de": "Diagramm nicht darstellbar.", "en": "Diagram cannot be displayed.",
                                  "fr": "Diagramme non affichable.", "es": "El diagrama no se puede mostrar.",
                                  "it": "Diagramma non visualizzabile."},
    "not_displayable_chart":     {"de": "Grafik nicht darstellbar.", "en": "Chart cannot be displayed.",
                                  "fr": "Graphique non affichable.", "es": "El gráfico no se puede mostrar.",
                                  "it": "Grafico non visualizzabile."},
    "not_displayable_formula":   {"de": "Formel nicht darstellbar.", "en": "Formula cannot be displayed.",
                                  "fr": "Formule non affichable.", "es": "La fórmula no se puede mostrar.",
                                  "it": "Formula non visualizzabile."},
    "not_displayable_simulator": {"de": "Simulator nicht darstellbar.", "en": "Simulator cannot be displayed.",
                                  "fr": "Simulateur non affichable.", "es": "El simulador no se puede mostrar.",
                                  "it": "Simulatore non visualizzabile."},
    "not_displayable_widget":    {"de": "Interaktives Element nicht darstellbar.", "en": "Interactive element cannot be displayed.",
                                  "fr": "Élément interactif non affichable.", "es": "El elemento interactivo no se puede mostrar.",
                                  "it": "Elemento interattivo non visualizzabile."},
}


def table_(language: str) -> dict[str, str]:
    """All interface texts of one language. Falls back to English."""
    s = (language or "en").lower()
    if s not in LANGUAGES:
        s = "en"
    return {k: v.get(s) or v["en"] for k, v in TEXTS.items()}


def as_js(language: str) -> str:
    """The table as a JavaScript constant for the shell."""
    return "const T = " + json.dumps(table_(language), ensure_ascii=False,
                                     indent=1, sort_keys=True) + ";"


def missing_ones() -> dict[str, list[str]]:
    """Keys without a translation, per language. Empty = complete."""
    return {s: sorted(k for k, v in TEXTS.items() if not v.get(s))
            for s in LANGUAGES if any(not v.get(s) for v in TEXTS.values())}
