# -*- coding: utf-8 -*-
"""German interface texts. Keys are the English source texts used in the code."""

CATALOG: dict[str, str] = {
    # ── wizard: layout ──
    "From prior knowledge and a learning goal to an interactive HTML learning unit — its scope derived, not set.":
        "Aus Vorwissen und Lernziel wird eine interaktive HTML-Lerneinheit — Umfang hergeleitet, nicht eingestellt.",
    "## 1 · Job": "## 1 · Auftrag",
    "Where do you stand? (prior knowledge — one sentence or a full competence profile)":
        "Wo stehen Sie? (Vorwissen — ein Satz oder ein ganzes Kompetenzprofil)",
    "e.g. I administer servers and know Docker well …": "z. B. Ich bin Admin und kenne Docker sehr gut …",
    "What do you want to learn? (goal or knowledge gap)": "Was wollen Sie lernen? (Ziel oder Wissenslücke)",
    "e.g. understand and use Kubernetes": "z. B. Kubernetes verstehen und anwenden",
    "Time budget in minutes (optional, 0 = none — a constraint, never a silent cut)":
        "Zeitbudget in Minuten (optional, 0 = keins — wirkt als Nebenbedingung, nie als stille Kürzung)",
    "Language of the unit": "Sprache der Lerneinheit",
    "Sets the language of all content AND of the controls of the generated unit.":
        "Bestimmt die Sprache aller Inhalte UND der Bedienoberfläche der erzeugten Lerneinheit.",
    "Your own material (optional: pdf, docx, pptx, md, txt, csv, html)":
        "Eigene Unterlagen (optional: pdf, docx, pptx, md, txt, csv, html)",
    "Next →": "Weiter →",
    "Build without follow-up questions ⏩": "Ohne Rückfragen durchbauen ⏩",
    "_The express route skips follow-up questions and the planning checkpoint: gap analysis and teaching script are generated and approved unchecked. The outline plan and the teaching script remain in the job folder and can be read there; single chapters can be corrected through rework._":
        "_Der Expressweg überspringt Rückfragen und den Planungs-Checkpoint: Gap-Analyse und Lehrskript werden erzeugt und ungeprüft freigegeben. Grobplan und Lehrskript liegen danach im Auftragsordner und lassen sich nachlesen; einzelne Kapitel können über die Nacharbeit korrigiert werden._",
    "Continue or delete a job": "Auftrag fortsetzen oder löschen",
    "Production continues on the server even if this window is closed. To continue or delete a job, enter the pickup code that was shown when the job was created.":
        "Die Produktion läuft serverseitig weiter, auch wenn dieses Fenster geschlossen wird. Zum Fortsetzen oder Löschen den Abholcode eingeben, der beim Anlegen des Auftrags angezeigt wurde.",
    "Pickup code": "Abholcode",
    "XXXX-XXXX-XXXX": "XXXX-XXXX-XXXX",
    "Load job": "Auftrag laden",
    "Delete the job with all its files for good (material, intermediate results, result)":
        "Auftrag mit allen Dateien endgültig löschen (Unterlagen, Zwischenstände, Ergebnis)",
    "Delete job": "Auftrag löschen",
    "## 2 · Briefing": "## 2 · Briefing",
    "Your answers (free text)": "Ihre Antworten (frei formuliert)",
    "On to the gap analysis →": "Weiter zur Gap-Analyse →",
    "## 3 · Plan review — the checkpoint": "## 3 · Plan-Review — der Checkpoint",
    "**Concept inventory (editable).** Classes: V = full (derive, activate, practise) · K = compact · D = delta/pitfall · R = glossary only · DELETE = remove the concept":
        "**Konzeptinventar (editierbar).** Klassen: V = vollständig (herleiten, aktivieren, üben) · K = kompakt · D = Delta/Stolperstein · R = nur Glossar · DELETE oder STREICHEN = Konzept entfernen",
    "ID": "ID", "Concept": "Konzept", "Class": "Klasse", "Rationale": "Begründung",
    "**Teaching script — common thread and concept graph.** It steers all following phases: every section learns from it which concept it may introduce and what it must not anticipate. Corrections here affect the whole production.":
        "**Lehrskript — roter Faden und Konzeptgraph.** Steuert alle folgenden Phasen: Jeder Abschnitt erfährt daraus, welches Konzept er einführen darf und was er nicht vorwegnehmen soll. Korrekturen hier wirken auf die gesamte Produktion.",
    "introduced in": "eingeführt in", "builds on (IDs, comma)": "baut auf (IDs, Komma)",
    "✓ Approve and start production": "✓ Freigeben und Produktion starten",
    "Re-derive the gap analysis with the changes": "Gap-Analyse mit Änderungen neu herleiten",
    "## 4 · Production (chapter by chapter, on the server — the window may be closed)":
        "## 4 · Produktion (kapitelweise, serverseitig — das Fenster darf geschlossen werden)",
    "Log": "Protokoll",
    "Stop after the current layer": "Stopp nach aktueller Schicht",
    "Continue production": "Produktion fortsetzen",
    "## 5 · Result": "## 5 · Ergebnis",
    "Learning unit (single-file HTML) — main output": "Lerneinheit (Single-File-HTML) — Hauptausgabe",
    "Create script handout (MD + Word)": "Skript-Handout erzeugen (MD + Word)",
    "Script handout": "Skript-Handout",
    "Rework: regenerate a single chapter": "Nacharbeit: einzelnes Kapitel neu anstoßen",
    "Chapter no. (1 = first)": "Kapitel-Nr. (1 = erstes)",
    "Note for the revision": "Hinweis für die Überarbeitung",
    "Regenerate chapter": "Kapitel neu erzeugen",
    "Technical report": "Technischer Bericht",
    "Rework log": "Nacharbeit-Protokoll",
    "Preview": "Vorschau",
    # ── wizard: messages ──
    "**Job #{number} — pickup code: `{code}`**\n\nPlease write it down. With this code the job can be continued or deleted later. It is shown only now and cannot be recovered; the operator can issue a new one.":
        "**Auftrag #{number} — Abholcode: `{code}`**\n\nBitte notieren. Mit diesem Code lässt sich der Auftrag später fortsetzen oder löschen. Er wird nur jetzt angezeigt und lässt sich nicht wiederherstellen; die Betreiberin kann einen neuen ausstellen.",
    "**Derivation:** {summary}": "**Herleitung:** {summary}",
    "**Interference:** {level} — {rationale}": "**Interferenz:** {level} — {rationale}",
    "**Chapter plan:**": "**Kapitelplan:**",
    "**Prioritisation proposal (time budget):**": "**Priorisierungsvorschlag (Zeitbudget):**",
    "**Changes applied:**": "**Übernommene Änderungen:**",
    "Please state prior knowledge and learning goal.": "Bitte Vorwissen und Lernziel angeben.",
    "Error: {error}": "Fehler: {error}",
    "The planning still needs some information:": "Für die Planung fehlen noch Angaben:",
    "No open questions — you can continue directly.": "Keine offenen Fragen — Sie können direkt fortfahren.",
    "Express route aborted: {error}": "Expressweg abgebrochen: {error}",
    "Job #{number} — express route, approved without follow-up questions and without checkpoint. {hints} {skipped}":
        "Auftrag #{number} — Expressweg, ohne Rückfragen und ohne Checkpoint freigegeben. {hints} {skipped}",
    "Skipped follow-up questions: {n}.": "Übersprungene Rückfragen: {n}.",
    "Chapter {done}/{total}": "Kapitel {done}/{total}",
    "Creating detail plans": "Feinpläne werden erstellt",
    "Detail plans created: {n} chapters": "Feinpläne erstellt: {n} Kapitel",
    "Detail plans created in parallel: {n} chapters": "Feinpläne parallel erstellt: {n} Kapitel",
    "Consolidation": "Konsolidierung",
    "Completion": "Abschluss",
    "Job #{number} is running on the express route. The window can be closed.":
        "Auftrag #{number} läuft im Expressweg. Das Fenster kann geschlossen werden.",
    "Gap analysis failed: {error}": "Gap-Analyse fehlgeschlagen: {error}",
    "_No teaching script created — production runs without a common thread._":
        "_Kein Lehrskript erzeugt — die Produktion läuft ohne roten Faden._",
    "**Guiding question:** {q}": "**Leitfrage:** {q}",
    "**Findings:**": "**Befunde:**",
    "Session lost": "Sitzung verloren",
    "The session no longer exists (page reloaded or server restarted). Please load the job again with its pickup code in step 1.":
        "Die Sitzung ist nicht mehr vorhanden (Seite neu geladen oder Server neu gestartet). Bitte den Auftrag in Schritt 1 mit seinem Abholcode wieder laden.",
    "Job #{number} — approved. {hints}": "Auftrag #{number} — Freigabe erteilt. {hints}",
    "Production started. The window can be closed — generation continues.":
        "Produktion gestartet. Das Fenster kann geschlossen werden — die Erzeugung läuft weiter.",
    "Abort requested.": "Abbruch angefordert.",
    "No running job.": "Kein laufender Auftrag.",
    "### No lessons\n\nThis job has no generated unit (`content/unit.json` is missing or empty). Production has to run again.":
        "### Keine Lektionen vorhanden\n\nZu diesem Auftrag liegt keine erzeugte Einheit vor (`content/unit.json` fehlt oder ist leer). Die Produktion muss neu laufen.",
    "### The result could not be created": "### Ergebnis konnte nicht erzeugt werden",
    "### Final gate: NOT passed — no output can be created": "### Final-Gate: NICHT bestanden — keine Ausgabe erzeugbar",
    "### Final gate NOT passed — the DRAFT is below\n**{name}** ({kb} KB) is clearly marked as a draft and can be viewed and downloaded. Close the errors below (for instance through rework per chapter) — the final file then replaces the draft.":
        "### Final-Gate NICHT bestanden — unten der ENTWURF\n**{name}** ({kb} KB) ist deutlich als Entwurf markiert und kann angesehen und heruntergeladen werden. Schließen Sie die Fehler unten (z. B. über die Nacharbeit je Kapitel) — danach ersetzt die finale Datei den Entwurf.",
    "### Done: {name} ({kb} KB, {mode})": "### Fertig: {name} ({kb} KB, {mode})",
    "offline": "offline", "CDN fallback": "CDN-Rückfall",
    "Please enter the pickup code.": "Bitte Abholcode angeben.",
    "There is no job for this pickup code.": "Zu diesem Abholcode gibt es keinen Auftrag.",
    "Job #{number} has no saved state yet (planning was not finished).":
        "Auftrag #{number} hat noch keinen gespeicherten Stand (die Planung war noch nicht abgeschlossen).",
    "Loading failed: {error}": "Laden fehlgeschlagen: {error}",
    "Job #{number} loaded: {title} — {done}/{total} chapters done.":
        "Auftrag #{number} geladen: {title} — Stand {done}/{total} Kapitel.",
    "Continue with “Continue production”.": "Weiter mit „Produktion fortsetzen“.",
    "Continuing job #{number} from chapter {chapter}.": "Fortsetzung Auftrag #{number} ab Kapitel {chapter}.",
    "Continuation running. The window can be closed.": "Fortsetzung läuft. Das Fenster kann geschlossen werden.",
    "Please confirm the deletion explicitly (tick the box).": "Bitte das Löschen ausdrücklich bestätigen (Häkchen).",
    "Job #{number} was still running and has been asked to stop. Please delete it again in a few seconds.":
        "Auftrag #{number} lief noch und wurde zum Abbruch aufgefordert. Bitte in einigen Sekunden erneut löschen.",
    "Job #{number} could not be deleted.": "Auftrag #{number} konnte nicht gelöscht werden.",
    "Job #{number} was deleted with all its files.": "Auftrag #{number} wurde mit allen Dateien gelöscht.",
    "Please give a chapter number and a note.": "Kapitelnummer und Hinweis angeben.",
    "Chapter {n} does not exist.": "Kapitel {n} existiert nicht.",
    "Rework of chapter {n} — note: {note}": "Nacharbeit Kapitel {n} — Hinweis: {note}",
    "Rework finished.": "Nacharbeit abgeschlossen.",
    "No scripts available.": "Keine Skripte vorhanden.",
    # ── job runner ──
    "started": "gestartet", "waiting": "wartet", "aborted": "abgebrochen", "error": "Fehler",
    "done": "fertig", "running": "läuft", "interrupted": "unterbrochen",
    # ── gap analysis ──
    "Kind: {kind} · interference: {interference} · {concepts} concepts ({v}×V, {k}×K, {d}×D, {r}×R) → ~{minutes} min learning time → format: {format} ({chapters} chapters)":
        "Art: {kind} · Interferenz: {interference} · {concepts} Konzepte ({v}×V, {k}×K, {d}×D, {r}×R) → ~{minutes} Min. Lernzeit → Format: {format} ({chapters} Kapitel)",
    "paradigm shift": "Paradigmenwechsel", "extension": "Erweiterung", "version delta": "Versionsdelta",
    "knowledge": "Wissen", "high": "hoch", "medium": "mittel", "low": "gering", "unknown": "unbekannt",
    "impulse": "Impuls", "learning unit": "Lerneinheit", "book": "Buch",
    "Edit ignored: concept '{cid}' unknown": "Edit ignoriert: Konzept '{cid}' unbekannt",
    "{cid} ({name}): {old} → {new}": "{cid} ({name}): {old} → {new}",
    "Edit ignored: class '{cls}' unknown (V|K|D|R|DELETE)": "Edit ignoriert: Klasse '{cls}' unbekannt (V|K|D|R|DELETE|STREICHEN)",
    "Removed: {ids}": "Gestrichen: {ids}",
    "Chapter '{title}' became empty and is dropped": "Kapitel '{title}' wurde leer und entfällt",
    # ── pipeline: progress events ──
    "Chapter {n}/{total}: {title}{rework}": "Kapitel {n}/{total}: {title}{rework}",
    " (rework)": " (Nacharbeit)",
    "Detail plan: {n} lessons": "Feinplan: {n} Lektionen",
    "Chapter {n}: run A taken over from the saved state (half-chapter resumption)":
        "Kapitel {n}: Lauf A aus Zwischenstand übernommen (Halbkapitel-Wiederaufnahme)",
    "Repair loop: {n} item(s) format-corrected": "Reparaturschleife: {n} Element(e) formatkorrigiert",
    "Validation after chapter {n}: {errors} errors, {warnings} warnings (remaining list)":
        "Validierung nach Kapitel {n}: {errors} Fehler, {warnings} Warnungen (Restliste)",
    "Run B aborted: {error}": "Lauf B abgebrochen: {error}",
    "⏹ Stopped — state saved.": "⏹ Gestoppt — Zwischenstand gesichert.",
    "Consolidation: final test + critic pass (parallel)": "Konsolidierung: Abschlusstest + Critic-Pass (parallel)",
    "Final test: answer without a list of questions — skipped (can be done later through rework)":
        "Abschlusstest: Antwort ohne Fragenliste — übersprungen (per Nacharbeit nachholbar)",
    "Final test failed: {error}": "Abschlusstest fehlgeschlagen: {error}",
    "Critic {id}: score {score} — {patch}": "Critic {id}: Score {score} — {patch}",
    "Critic {id}: score {score} — {outcome}": "Critic {id}: Score {score} — {outcome}",
    "revised": "überarbeitet", "revision failed": "Revision fehlgeschlagen",
    "Critic {id}: revision discarded ({reason}) — original kept": "Critic {id}: Revision verworfen ({reason}) — Original behalten",
    "Consolidation finished": "Konsolidierung abgeschlossen",
    "Redundancy check across the whole unit": "Redundanzprüfung über die ganze Einheit",
    "Redundancy check: no repeated explanations": "Redundanzprüfung: keine Mehrfacherklärungen",
    "Redundancy: '{concept}' explained in {first} and again in {again}": "Redundanz: '{concept}' erklärt in {first} und erneut in {again}",
    "Fact check against the source material (parallel)": "Faktenprüfung gegen das Quellmaterial (parallel)",
    "Fact check {id}: {n} finding(s) ({kinds})": "Faktenprüfung {id}: {n} Befund(e) ({kinds})",
    "Fact check {id}: contradiction — lesson revised": "Faktenprüfung {id}: Widerspruch — Lektion überarbeitet",
    "Fact check {id}: revision discarded ({reason}) — original kept": "Faktenprüfung {id}: Revision verworfen ({reason}) — Original behalten",
    # ── pipeline: reasons ──
    "no object structure": "keine Objektstruktur",   # "title missing", "no blocks": see validator
    "only {new} instead of {old} blocks": "nur {new} statt {old} Blöcken",
    "only {new} instead of {old} words": "nur {new} statt {old} Wörtern",
    "same type '{type}' directly adjacent": "gleicher Typ '{type}' direkt benachbart",
    "a block with the same content exists": "inhaltsgleicher Block vorhanden",
    "no finding refers to a block": "kein Befund mit Blockbezug",
    "patch failed ({error})": "Patch fehlgeschlagen ({error})",
    "{n} block(s) replaced": "{n} Block/Blöcke ersetzt", "{n} discarded": "{n} verworfen",
    "{parts}": "{parts}",
    # ── pipeline: handout ──
    "Script exported as Markdown and Word.": "Skript als Markdown und Word exportiert.",
    "Script exported as Markdown and Word (minimal layout; the formatted export was not available).":
        "Skript als Markdown und Word exportiert (Minimal-Layout; der formatierte Export war nicht verfügbar).",
    "Script exported as Markdown; Word export failed ({e1} / {e2})": "Skript als Markdown exportiert; Word-Export fehlgeschlagen ({e1} / {e2})",
    # ── job files: learner profile, outline plan, fact check ──
    "# Learner profile": "# Lernprofil",
    "# Outline plan — {title} (CHECKPOINT)": "# Grobplan — {title} (CHECKPOINT)",
    "**Gap analysis:** {summary}": "**Gap-Analyse:** {summary}",
    "## Concept inventory": "## Konzeptinventar",
    "| ID | Concept | Class | Rationale |": "| ID | Konzept | Klasse | Begründung |",
    "## Chapter plan": "## Kapitelplan",
    "**C{i} · {title}** — concepts: {concepts}": "**K{i} · {title}** — Konzepte: {concepts}",
    "  Objective: {objective}": "  Ziel: {objective}",
    "**Time budget (constraint):** {minutes} min": "**Zeitbudget (Nebenbedingung):** {minutes} Min.",
    "## Prioritisation proposal": "## Priorisierungsvorschlag",
    "**CHECKPOINT:** scope and chapter plan must be approved before production starts.":
        "**CHECKPOINT:** Freigabe von Umfang und Kapitelplan erforderlich, bevor die Produktion startet.",
    "Derived scope ~{derived} min exceeds the budget of {budget} min. Proposal (gives ~{minutes} min):\n{rows}{note}":
        "Hergeleiteter Umfang ~{derived} Min. übersteigt das Budget von {budget} Min. Vorschlag (ergibt ~{minutes} Min.):\n{rows}{note}",
    "\nNote: the budget cannot be reached even with all downgrades — remove concepts as well or relax the budget.":
        "\nHinweis: Budget auch mit allen Abstufungen nicht erreichbar — zusätzlich Konzepte streichen oder Budget lockern.",
    "# Fact check against the source material": "# Faktenprüfung gegen das Quellmaterial",
    "- {id}: no objections": "- {id}: keine Beanstandungen",
    # ── teaching script ──
    "Teaching script not created ({error}) — production runs without a common thread":
        "Lehrskript nicht erzeugt ({error}) — Produktion läuft ohne roten Faden",
    "## Concept graph": "## Konzeptgraph",
    "# Teaching script — common thread and concept graph": "# Lehrskript — roter Faden und Konzeptgraph",
    "**Guiding question of the unit:** {q}": "**Leitfrage der Einheit:** {q}",
    "## Arc": "## Bogen",
    "## Concepts in learning order": "## Konzepte in Lernreihenfolge",
    "| # | Concept | introduced in | builds on | resumed in |": "| # | Konzept | eingeführt in | baut auf | wiederaufgenommen in |",
    "## Contribution to the arc": "## Beitrag zum Bogen",
    "## Findings of the check": "## Befunde der Prüfung",
    "This document steers all following phases. Every section learns from it which concept it may introduce, what it can build on and what it must not anticipate. Corrections here affect the whole production.":
        "Dieses Dokument steuert alle folgenden Phasen. Jeder Abschnitt erfährt daraus, welches Konzept er einführen darf, worauf er aufbauen kann und was er nicht vorwegnehmen soll. Korrekturen hier wirken auf die gesamte Produktion.",
    "Teaching script names unknown concept '{cid}' — ignored": "Lehrskript nennt unbekanntes Konzept '{cid}' — ignoriert",
    "Concept '{cid}' is missing from the teaching script — no place of introduction":
        "Konzept '{cid}' fehlt im Lehrskript — ohne Einführungsort",
    "{cid}: unknown prerequisite {foreign} — removed": "{cid}: unbekannte Voraussetzung {foreign} — entfernt",
    "{cid}: requires itself — removed": "{cid}: setzt sich selbst voraus — entfernt",
    "{cid}: no place of introduction given": "{cid}: kein Einführungsort angegeben",
    "Dependency cycle: {cycle}": "Abhängigkeitszyklus: {cycle}",
    "{cid} is introduced in {place}, but requires {v}, which is only introduced in {later}":
        "{cid} wird in {place} eingeführt, setzt aber {v} voraus, das erst in {later} eingeführt wird",
    "{cid}: introduction {old} → {new}": "{cid}: Einführung {old} → {new}",
    "{cid}: builds on {old} → {new}": "{cid}: baut auf {old} → {new}",
    "⚠️ Cycle after editing: {cycle}": "⚠️ Zyklus nach Bearbeitung: {cycle}",
    # ── validator ──
    "no self-check (quiz/cloze/matching) — didactics criterion C1":
        "keine Selbstkontrolle (quiz/cloze/matching) — Didaktik-Kriterium C1",
    "no blocks":
        "keine blocks",
    "title missing":
        "title fehlt",
    "contains {n} CJK characters (e.g. '{probe}') — mixed languages, keep all texts in '{language}'":
        "enthält {n} CJK-Zeichen (z. B. '{probe}') — Sprachmischung, alle Texte in '{language}' halten",
    "JSON not readable: {e}":
        "JSON nicht lesbar: {e}",
    "slider '{label}' has the same label as the x axis — the chart probably already shows what it is meant to set":
        "Regler '{label}' trägt dieselbe Beschriftung wie die x-Achse — vermutlich zeigt das Diagramm bereits, was er einstellen soll",
    "slider '{label}' changes nothing in the output — a control without effect is misleading":
        "Regler '{label}' ändert nichts an der Ausgabe — ein Bedienelement ohne Wirkung führt in die Irre",
    "output ({name}) has {v1} points — thin it out for display":
        "Ausgabe ({name}) hat {v1} Punkte — für die Darstellung ausdünnen",
    "series '{v1}': {v2} of {v3} values are NaN or infinite — the curve breaks off there":
        "Reihe '{v1}': {v2} von {v3} Werten sind NaN oder unendlich — dort bricht die Kurve ab",
    "series '{v1}' is 0 throughout — it lies invisibly on the axis":
        "Reihe '{v1}' ist durchgehend 0 — sie liegt unsichtbar auf der Achse",
    "series[{si}].name missing":
        "series[{si}].name fehlt",
    "series[{si}].values ({name}) not as long as x":
        "series[{si}].values ({name}) nicht gleich lang wie x",
    "output form ({name}) invalid — expected {{x:[], series:[{{name,values}}]}}":
        "Ausgabeform ({name}) ungültig — erwartet {{x:[], series:[{{name,values}}]}}",
    "output has only {v1} data point(s) — as '{kind}' that sits as a dot at the left edge of the axis. modell(p) should return a CURVE: run x over a range of values (sweep) instead of returning the single value for the current slider position":
        "Ausgabe hat nur {v1} Stützstelle(n) — als '{kind}' liegt das als Punkt am linken Achsenrand. modell(p) soll eine KURVE liefern: x über einen Wertebereich durchlaufen (Sweep), nicht den Einzelwert der aktuellen Reglerstellung zurückgeben",
    "trial run ({name}) takes {v1} ms — target budget ~50 ms":
        "Probeausführung ({name}) dauert {v1} ms — Zielbudget ~50 ms",
    "trial run ({name}) fails: {v1}":
        "Probeausführung ({name}) schlägt fehl: {v1}",
    "trial run skipped (Node.js not found) — static check only":
        "Probeausführung übersprungen (Node.js nicht gefunden) — nur statische Prüfung",
    "code uses '{forbidden}' — level 3 contract: a pure function without environment":
        "code verwendet '{forbidden}' — Stufe-3-Vertrag: reine Funktion ohne Umgebung",
    "code missing":
        "code fehlt",
    "min >= max":
        "min >= max",
    "{k} missing/not a number":
        "{k} fehlt/kein Zahlwert",
    "label missing":
        "label fehlt",
    "name missing":
        "name fehlt",
    "parameters missing":
        "parameters fehlen",
    "level 4 in use — justification in the detail plan and a smoke test required":
        "Stufe 4 im Einsatz — Begründung im Feinplan und Smoke-Test erforderlich",
    "widget loads external resources — forbidden (offline, sandbox without network)":
        "widget lädt externe Ressourcen — verboten (offline, sandbox ohne Netz)",
    "widget.html must be a complete HTML document (<!DOCTYPE …)":
        "widget.html muss ein vollständiges HTML-Dokument sein (<!DOCTYPE …)",
    "html missing":
        "html fehlt",
    "sample_solution missing":
        "sample_solution fehlt",
    "question missing":
        "question fehlt",
    "material missing":
        "material fehlt",
    "empty":
        "leer",
    "task missing":
        "task fehlt",
    "text missing":
        "text fehlt",
    "options: at least 2, or leave them out entirely (then a free-text commitment)":
        "options: mindestens 2 oder ganz weglassen (dann Freitext-Festlegung)",
    "resolution missing":
        "resolution fehlt",
    "the formula could not be displayed (neither simple notation nor MathML) — simplify the LaTeX or provide KaTeX":
        "Formel konnte nicht dargestellt werden (weder einfache Notation noch MathML) — LaTeX vereinfachen oder KaTeX bereitstellen",
    "html missing — the formula was not translated into a display (src.unit.normalization)":
        "html fehlt — Formel wurde nicht in Darstellung übersetzt (src.unit.normalization)",
    "unknown display '{v1}' (inline|block)":
        "unbekannte display '{v1}' (inline|block)",
    "latex missing":
        "latex fehlt",
    "Mermaid syntax error: {v1}":
        "Mermaid-Syntaxfehler: {v1}",
    "{type_}: {shortcoming}":
        "{type_}: {shortcoming}",
    "diagram type not recognised — the source must begin with a Mermaid keyword ({v1} …)":
        "Diagrammtyp nicht erkannt — der Quelltext muss mit einem Mermaid-Startwort beginnen ({v1} …)",
    "code (Mermaid) missing":
        "code (Mermaid) fehlt",
    "interactive graphic: description names no exploration task (\"Set X to …, observe Y\") — criterion D2":
        "interaktive Grafik: description nennt keine Erkundungsaufgabe (\"Stelle X auf …, beobachte Y\") — Kriterium D2",
    "params[{i}]('{v1}'): binding without name — the control then carries the technical identifier":
        "params[{i}]('{v1}'): Bindung ohne name — das Bedienelement trägt dann den technischen Bezeichner",
    "params[{i}]('{v1}'): select binding without options":
        "params[{i}]('{v1}'): select-Bindung ohne options",
    "params[{i}]('{v1}'): range binding without min/max — Vega guesses the limits":
        "params[{i}]('{v1}'): range-Bindung ohne min/max — Vega rät die Grenzen",
    "params[{i}]('{v1}') is bound but has no value — the graphic starts empty":
        "params[{i}]('{v1}') ist gebunden, hat aber keinen value — die Grafik startet leer",
    "params[{i}] without name — no transformation can refer to a parameter without a name":
        "params[{i}] ohne name — auf einen Parameter ohne Namen kann keine Transformation verweisen",
    "params[{i}] is not an object":
        "params[{i}] ist kein Objekt",
    "params must be a list":
        "params muss eine Liste sein",
    "vegalite spec contains \"signal\" — that is Vega syntax, not Vega-Lite; express it as params/bind":
        "vegalite-spec enthält \"signal\" — das ist Vega-Syntax, nicht Vega-Lite; als params/bind ausdrücken",
    "vegalite spec references a URL — the unit must work offline; put the data inline under data.values":
        "vegalite-spec referenziert eine URL — Einheit muss offline funktionieren, Daten inline unter data.values legen",
    "chartjs spec without type":
        "chartjs-spec ohne type",
    "spec missing":
        "spec fehlt",
    "engine '{v1}' unknown (chartjs|vegalite)":
        "engine '{v1}' unbekannt (chartjs|vegalite)",
    "params['{name}'] is addressed as 'datum.{v1}' — a parameter is not a data field. Correct is '{v2}' alone; otherwise the graphic stays empty":
        "params['{name}'] wird als 'datum.{v1}' angesprochen — ein Parameter ist kein Datenfeld. Richtig ist '{v2}' allein; sonst bleibt die Grafik leer",
    "params['{name}'] is used nowhere — the control appears but does nothing":
        "params['{name}'] wird nirgends verwendet — das Bedienelement erscheint, bewirkt aber nichts",
    "encoding.{channel}.field '{field_}' does not occur in the data (present: {v1})":
        "encoding.{channel}.field '{field_}' kommt in den Daten nicht vor (vorhanden: {v1})",
    "encoding.{channel}.field '{field_}' is a PARAMETER, not a data field — addressed like this the graphic stays empty. For a parameter value use 'datum' with expr or bind it in a transform":
        "encoding.{channel}.field '{field_}' ist ein PARAMETER, kein Datenfeld — so angesprochen bleibt die Grafik leer. Für einen Parameterwert 'datum' mit expr verwenden oder ihn in einem transform binden",
    "encoding.{channel} has {kind} without type — Vega-Lite needs quantitative, nominal, ordinal or temporal":
        "encoding.{channel} hat {kind} ohne type — Vega-Lite braucht quantitative, nominal, ordinal oder temporal",
    "data.values is empty — the graphic stays empty":
        "data.values ist leer — die Grafik bleibt leer",
    "vegalite spec without data.values — the graphic stays empty":
        "vegalite-spec ohne data.values — die Grafik bleibt leer",
    "all {v1} data series are constant — the chart shows no difference":
        "alle {v1} Datenreihen sind konstant — das Diagramm zeigt keinen Unterschied",
    "{v1} values, but {v2} labels — the mapping shifts":
        "{v1} Werte, aber {v2} labels — die Zuordnung verschiebt sich",
    "data missing or empty — empty chart":
        "data fehlt oder ist leer — leeres Diagramm",
    "not an object":
        "kein Objekt",
    "chartjs spec without datasets":
        "chartjs-spec ohne datasets",
    "chartjs spec without data":
        "chartjs-spec ohne data",
    "duplicate front ({v1}) — the same question with two answers":
        "doppelte Vorderseite ({v1}) — dieselbe Frage mit zwei Antworten",
    "front/back missing":
        "front/back fehlt",
    "cards missing":
        "cards fehlen",
    "left and right are identical — trivial pair":
        "left und right sind identisch — triviales Paar",
    "left values must be unique — two equal prompts with different solutions cannot be answered":
        "left-Werte müssen eindeutig sein — zwei gleiche Vorgaben mit verschiedenen Lösungen sind nicht beantwortbar",
    "all pairs point to the same value — there is nothing to match":
        "alle Paare zeigen auf denselben Wert — es gibt nichts zuzuordnen",
    "left/right missing":
        "left/right fehlt",
    "at least 2 pairs required":
        "mindestens 2 pairs nötig",
    "solution '{v1}' appears literally in the surrounding text — the gap can be read off":
        "Lösung '{v1}' steht wörtlich im umgebenden Text — die Lücke ist ablesbar",
    "gaps['{k}'].answers contains empty entries":
        "gaps['{k}'].answers enthält leere Einträge",
    "gaps['{k}'].answers missing":
        "gaps['{k}'].answers fehlt",
    "gaps['{k}'] is not an object":
        "gaps['{k}'] ist kein Objekt",
    "gaps['{k}'] defined, but no placeholder in the text":
        "gaps['{k}'] definiert, aber kein Platzhalter im Text",
    "gap {{{{{k}}}}} in the text, but not defined in gaps":
        "Lücke {{{{{k}}}}} im Text, aber nicht in gaps definiert",
    "no {{n}} placeholders in the html":
        "keine {{n}}-Platzhalter im html",
    "gaps must be an object":
        "gaps muss ein Objekt sein",
    "feedback missing — didactics criterion C3":
        "feedback fehlt — Didaktik-Kriterium C3",
    "identical options ({v1}) — one of them cannot be answered":
        "identische Optionen ({v1}) — eine davon ist unbeantwortbar",
    "all options are correct — the question checks nothing":
        "alle Optionen sind korrekt — die Frage prüft nichts",
    "{correct_ones} correct options, but multiple=false":
        "{correct_ones} korrekte Optionen, aber multiple=false",
    "no correct option marked":
        "keine korrekte Option markiert",
    "at least 2 options required":
        "mindestens 2 options nötig",
    "questions missing":
        "questions fehlen",
    "content missing":
        "content fehlt",
    "items missing":
        "items fehlen",
    "number of columns does not match the header":
        "Spaltenzahl passt nicht zum header",
    "rows missing":
        "rows fehlen",
    "header missing":
        "header fehlt",
    "unknown variant '{v1}' (expected key_point|info|warning)":
        "unbekannte variant '{v1}' (erwartet key_point|info|warning)",
    "description very short — it should state the key message, not just the type":
        "description sehr kurz — soll die Kernaussage nennen, nicht nur den Typ",
    "description (alternative text) is required":
        "description (Alternativtext) ist Pflicht",
    "{msg} (in an escaped field — hard to read there)":
        "{msg} (in escaptem Feld — dort nur schwer lesbar)",
    "{msg} — HTML is the lead format":
        "{msg} — HTML ist das Leitformat",
    "unknown block type '{type_}'":
        "unbekannter Blocktyp '{type_}'",
    "type missing":
        "type fehlt",
    "{v1} short field(s) over 300 characters (e.g. {v2}) — too much for a hover":
        "{v1} short-Feld(er) über 300 Zeichen (z. B. {v2}) — für einen Hover zu viel",
    "{v1} of {v2} entries without a short field (e.g. {v3}) — the hover shows the full definition there":
        "{v1} von {v2} Einträgen ohne short-Feld (z. B. {v3}) — der Hover zeigt dort die volle Definition",
    "concept '{name}' ({v1}) has no glossary entry — without it there is no hover explanation":
        "Konzept '{name}' ({v1}) hat keinen Glossareintrag — ohne ihn keine Hover-Erklärung",
    "possible glossary duplicate of '{v1}' ({reason}) — merge them or make the distinction explicit in the term":
        "mögliche Glossar-Dublette mit '{v1}' ({reason}) — zusammenführen oder die Unterscheidung im Begriff explizit machen",
    "{v1} diagram(s) not syntax-checked: {v2}. This is a setup problem, not a flaw of the unit — syntax errors then only show up for the learner.":
        "{v1} Diagramm(e) nicht auf Syntax geprüft: {v2}. Das ist ein Einrichtungsproblem, kein Mangel der Einheit — Syntaxfehler fallen dann erst beim Lernenden auf.",
    "all {v1} interactions of the unit are of type '{v2}' — also available: flashcards, matching, cloze, prediction, simulator":
        "alle {v1} Interaktionen der Einheit sind vom Typ '{v2}' — verfügbar sind auch flashcards, matching, cloze, prediction, simulator",
    "{v1}x vegalite without a single interactive parameter — that embeds about 1.5 MB of library for static graphics; chartjs does the same at about a seventh of the size":
        "{v1}x vegalite ohne einen einzigen interaktiven Parameter — das bindet rund 1,5 MB Bibliothek für statische Grafiken ein; chartjs leistet das gleiche bei rund einem Siebtel der Größe",
    "illustration unevenly distributed ({v1} per lesson) — the weakest lesson is almost text only":
        "Veranschaulichung ungleich verteilt ({v1} je Lektion) — die schwächste Lektion trägt fast nur Text",
    "two '{t1}' blocks directly in a row — distribute or merge them (C1b/C1c)":
        "zwei '{t1}'-Blöcke direkt hintereinander — verteilen oder zusammenführen (C1b/C1c)",
    "~{w} words of reading text with only {act} interaction(s) — guideline C1b: about one per 400 words ({needed} would be the floor), spread over the lesson":
        "~{w} Wörter Lesetext bei nur {act} Interaktion(en) — Richtwert C1b: etwa eine je 400 Wörter ({needed} wären der Boden), über die Lektion verteilt",
    "only {v1} different forms of display and interaction in the whole unit ({v2}) — also available: chart (interactive via params too), simulator, flashcards, prediction, cloze, formula":
        "nur {v1} verschiedene Darstellungs- und Interaktionsformen in der ganzen Einheit ({v2}) — verfügbar sind außerdem chart (auch interaktiv über params), simulator, flashcards, prediction, cloze, formula",
    "in {longest} of {countable} quiz questions the correct answer is the longest option — it can be solved without understanding. Justify wrong options as fully as the correct one":
        "in {longest} von {countable} Quizfragen ist die richtige Antwort die längste Option — das lässt sich ohne Verständnis lösen. Falsche Optionen ebenso ausführlich begründen wie die richtige",
    "not a single diagram in {v1} blocks — tables show values, diagrams show relations (processes, states, dependencies). Everything structural stays in running text":
        "kein einziges Diagramm bei {v1} Blöcken — Tabellen zeigen Werte, Diagramme zeigen Beziehungen (Abläufe, Zustände, Abhängigkeiten). Alles Strukturelle bleibt so im Fließtext",
    "~{w} words without any illustration (diagram, table, chart, formula, simulator) — derive the form of display from the type of content, not running text only":
        "~{w} Wörter ohne jede Veranschaulichung (Diagramm, Tabelle, Chart, Formel, Simulator) — Darstellungsform aus dem Inhaltstyp ableiten, nicht nur Fließtext",
    "~{w} words of text without h3/h4 subheadings — headings become search anchors and deep links":
        "~{w} Wörter Text ohne h3/h4-Zwischenüberschriften — Überschriften werden zu Suchankern und Deeplinks",
    "{cnt} lessons without glossary — looking things up later is hardly possible":
        "{cnt} Lektionen ohne glossary — Nachschlagen später kaum möglich",
    "{cnt} lessons without modules grouping — the learning path becomes hard to follow":
        "{cnt} Lektionen ohne modules-Gruppierung — Lernpfad wird unübersichtlich",
    "no application part (exercises) — consolidated tasks per chapter are part of the book model":
        "kein Anwendungsteil (exercises) — konsolidierte Aufgaben je Kapitel sind Teil des Buchmodells",
    "~{w} words of text with {act} interaction(s) and {show} display(s) — too thin for depth profile 'detailed'. Either developed running text (800–1500 words) or more activity and illustration":
        "~{w} Wörter Text bei {act} Interaktion(en) und {show} Darstellung(en) — für Tiefenprofil 'detailed' zu dünn. Entweder entwickelter Fließtext (800–1500 Wörter) oder mehr Handlung und Anschauung",
    "~{w} words of text — interactions do not replace developing running text (B8: 800–1500 words in depth profile 'detailed')":
        "~{w} Wörter Text — Interaktionen ersetzen den entwickelnden Fließtext nicht (B8: 800–1500 Wörter im Tiefenprofil 'detailed')",
    "'{v1}' unknown (compact|detailed)":
        "'{v1}' unbekannt (compact|detailed)",
    "{n} CJK characters found (e.g. '{probe}') — mixed languages? unit.language is '{lang}'":
        "{n} CJK-Zeichen gefunden (z. B. '{probe}') — Sprachmischung? unit.language ist '{lang}'",
    "V concept '{cid}' ({v1}) is not practised in any application part":
        "V-Konzept '{cid}' ({v1}) wird in keinem Anwendungsteil geübt",
    "unknown concept '{cid}'":
        "unbekanntes Konzept '{cid}'",
    "no concepts assigned — coverage of this lesson cannot be checked":
        "keine concepts-Zuordnung — Abdeckung dieser Lektion nicht prüfbar",
    "id duplicated":
        "id doppelt",
    "concept_class '{v1}' unknown (V|K|D|R)":
        "concept_class '{v1}' unbekannt (V|K|D|R)",
    "id missing":
        "id fehlt",
    "must be an array":
        "muss ein Array sein",
    "'{v1}' unknown (draft|final)":
        "'{v1}' unbekannt (draft|final)",
    "lesson '{v1}' does not exist — the reference is not shown":
        "lesson '{v1}' existiert nicht — Verweis wird nicht angezeigt",
    "term duplicated in the glossary":
        "term doppelt im Glossar",
    "definition missing":
        "definition fehlt",
    "term missing":
        "term fehlt",
    "lesson '{lid}' is not assigned to any module — it appears under 'More lessons'":
        "Lektion '{lid}' ist keinem Modul zugeordnet — erscheint unter 'Weitere Lektionen'",
    "lesson '{lid}' is assigned to several modules":
        "Lektion '{lid}' ist mehreren Modulen zugeordnet",
    "references unknown lesson '{lid}'":
        "referenziert unbekannte Lektion '{lid}'",
    "lessons (list of lesson ids) missing":
        "lessons (Liste von Lektions-IDs) fehlt",
    "all {v1} interactions are of type '{v2}' — derive the form from the learning purpose (recall terms, separate what is easily confused, reconstruct an order, confront a misconception)":
        "alle {v1} Interaktionen sind vom Typ '{v2}' — Form aus dem Lernzweck ableiten (Begriffe abrufen, Verwechselbares trennen, Reihenfolge rekonstruieren, Fehlvorstellung stellen)",
    "~{wtext} words of reading text, but only {v1} interaction(s) — about {target} would be appropriate. The learner should not have to wait until the end of the lesson to act":
        "~{wtext} Wörter Lesetext, aber nur {v1} Interaktion(en) — angemessen wären etwa {target}. Der Lernende soll nicht erst am Ende der Lektion handeln dürfen",
    "no self-check (quiz/cloze/matching/flashcards) — didactics criterion C1":
        "keine Selbstkontrolle (quiz/cloze/matching/flashcards) — Didaktik-Kriterium C1",
    "no learning objectives given":
        "keine learning_objectives angegeben",
    "id is reserved (start|test|glossary|ex-*)":
        "id ist reserviert (start|test|glossary|ex-*)",
    "block check aborted ({v1}: {e}) — the block counts as faulty":
        "Blockprüfung abgebrochen ({v1}: {e}) — Block gilt als fehlerhaft",
    "provenance.sources missing — provenance incomplete":
        "provenance.sources fehlt — Herkunftsnachweis unvollständig",
    "at least one lesson required":
        "mindestens eine Lektion nötig",
    "missing or empty":
        "fehlt oder leer",
    "WARNING  {text}":
        "WARNUNG  {text}",
    "ERROR    {text}":
        "FEHLER   {text}",
    "{errors} errors, {warnings} warnings — {verdict}":
        "{errors} Fehler, {warnings} Warnungen — {verdict}",
    "NOT passed.":
        "NICHT bestanden.",
    "passed.":
        "bestanden.",
    "all {n} diagrams are of type '{kind}' — Mermaid also knows {others}":
        "alle {n} Diagramme sind vom Typ '{kind}' — Mermaid kennt auch {others}",
    "code not evaluable: {detail}":
        "code nicht auswertbar: {detail}",
    "code is not a function":
        "code ergibt keine Funktion",
    "simulator probe failed: {detail}":
        "Simulator-Probe fehlgeschlagen: {detail}",
    "Markdown bold (**…**) instead of <strong>":
        "Markdown-Fettung (**…**) statt <strong>",
    "Markdown italics (*…*) instead of <em>":
        "Markdown-Kursivierung (*…*) statt <em>",
    "Markdown heading (#) instead of <h3>/<h4>":
        "Markdown-Überschrift (#) statt <h3>/<h4>",
    "Markdown list (-) instead of <ul><li>":
        "Markdown-Liste (-) statt <ul><li>",
    "Markdown code (`…`) instead of <code>":
        "Markdown-Code (`…`) statt <code>",
    "Markdown link instead of <a>":
        "Markdown-Link statt <a>",
    "Markdown table instead of a table block":
        "Markdown-Tabelle statt table-Block",
    "LaTeX command (\\…) — belongs in a formula block":
        "LaTeX-Befehl (\\…) — gehört in einen formula-Block",
    "LaTeX delimiters (\\( \\)) not resolved":
        "LaTeX-Delimiter (\\( \\)) nicht aufgelöst",
    "LaTeX between dollar signs":
        "LaTeX zwischen Dollarzeichen",
    "LaTeX super/subscript (^{…}) instead of <sup>/<sub>":
        "LaTeX-Hoch/Tiefstellung (^{…}) statt <sup>/<sub>",
    "concept '{cid}' ({name}, class {cls}) appears in NO lesson{consequence}":
        "Konzept '{cid}' ({name}, Klasse {cls}) taucht in KEINER Lektion auf{consequence}",
    " — blocks delivery": " — blockiert die Auslieferung",
    " (state: draft)": " (state: draft)",
    # ── technical report ──
    "### Technical report": "### Technischer Bericht",
    "_Usage figures from the original production run (this process only loaded the unit)._":
        "_Verbrauchszahlen aus dem ursprünglichen Produktionslauf (dieser Prozess hat die Einheit nur geladen)._",
    "**Model usage**": "**Modellverbrauch**",
    "| Role | Model | Calls | Input tokens | Output tokens | truncated | empty |":
        "| Rolle | Modell | Calls | Eingabe-Tokens | Ausgabe-Tokens | abgeschnitten | leer |",
    "Total": "Summe", "strong": "stark", "fast": "schnell",
    "{n} empty answer(s) rescued by a retry without thinking — JSON mode and thinking do not work together on this endpoint.":
        "{n} leere Antwort(en) durch Wiederholung ohne Thinking gerettet — json_mode und Thinking vertragen sich auf diesem Endpunkt nicht.",
    "⚠️ {n} answer(s) cut off at the budget": "⚠️ {n} Antwort(en) am Budget abgeschnitten",
    ", {n} of them completely empty — the budget went into thinking. A higher budget does NOT help then; set BLOCKS_THINKING=false or LLM_REASONING_EFFORT_OFF.":
        ", davon {n} vollständig leer — dann floss das Budget ins Denken. Höheres Budget hilft dann NICHT; BLOCKS_THINKING=false bzw. LLM_REASONING_EFFORT_OFF setzen.",
    ". Adjust with BLOCKS_MAX_TOKENS.": ". Mit BLOCKS_MAX_TOKENS nachjustieren.",
    "Tokens in total: **{n}**": "Tokens gesamt: **{n}**",
    "**Scope**": "**Umfang**", "**Components**": "**Bausteine**", "**Density**": "**Dichte**",
    "**Concept classes** — {classes}": "**Konzeptklassen** — {classes}",
    "**Per lesson**": "**Je Lektion**",
    "| Lesson | Words | Displays | Interactions | Tasks |": "| Lektion | Wörter | Darstellungen | Interaktionen | Aufgaben |",
    "**Production**": "**Produktion**",
    "Display": "Darstellung", "Interaction": "Interaktion", "Text": "Text", "Tasks": "Aufgaben",
    "text blocks": "Textblöcke", "callouts": "Hinweisboxen", "accordions": "Akkordeons", "tables": "Tabellen",
    "diagrams (Mermaid)": "Diagramme (Mermaid)", "charts": "Charts", "formulas": "Formeln", "code blocks": "Codeblöcke",
    "quizzes": "Quiz", "cloze texts": "Lückentexte", "matching exercises": "Zuordnungen", "flashcard sets": "Karteikarten-Sets",
    "predictions": "Vorhersagen", "simulators": "Simulatoren", "widgets": "Widgets", "tasks": "Aufgaben",
    "error analyses": "Fehleranalysen",
    "Material size (characters)": "Materialumfang (Zeichen)", "Use of material": "Materialnutzung",
    "indexed in {n} segments": "indiziert in {n} Segmenten", "as excerpts only (no embedder index)": "nur als Auszüge (kein Embedder-Index)",
    "Concepts with evidence in the material": "Konzepte mit Materialbeleg", "{n} of {total}": "{n} von {total}",
    "Concepts from model knowledge": "Konzepte aus Modellwissen", "Material segments without a concept": "Materialsegmente ohne Konzept",
    "Relevance confirmed by reranker": "Relevanz durch Reranker bestätigt", "yes": "ja", "no": "nein",
    "Chapters": "Kapitel", "Lessons": "Lektionen", "Blocks in total": "Blöcke gesamt", "Words of reading text": "Wörter Lesetext",
    "Concepts": "Konzepte", "Glossary entries": "Glossareinträge", "Learning objectives": "Lernziele",
    "Estimated duration (min)": "geschätzte Dauer (min)", "Displays": "Darstellungen", "Interactions": "Interaktionen",
    "of which in lessons": "davon in Lektionen", "Tasks/error analyses in lessons": "Aufgaben/Fehleranalysen in Lektionen",
    "Share of non-text blocks": "Anteil nicht-textueller Blöcke", "Words per interaction (lessons)": "Wörter je Interaktion (Lektionen)",
    "Lost lessons": "verlorene Lektionen", "Downgraded blocks": "herabgestufte Blöcke",
    "Blocks added by enrichment": "durch Anreicherung ergänzte Blöcke",
    "Proposed by enrichment, but discarded": "durch Anreicherung vorgeschlagen, aber verworfen",
    "Critic scores (per lesson)": "Critic-Scores (je Lektion)", "Fixed technical terms": "gesetzte Fachbegriffe",
    "Open term candidates": "offene Begriffskandidaten", "Replaced coinages": "ersetzte Wortneuschöpfungen",
    "Teaching script nodes": "Lehrskript-Knoten",
    # ── material coverage ──
    "### Material coverage": "### Materialabdeckung",
    "_No material index available._": "_Kein Materialindex vorhanden._",
    "> Without a reranker there is only a ranking, no relevance decision. Read the assignment as a pointer, not as evidence.":
        "> Ohne Reranker liegt nur eine Rangfolge vor, keine Relevanzentscheidung. Die Zuordnung ist als Hinweis zu lesen, nicht als Beleg.",
    "**{n} of {total} concepts** have evidence in the material.": "**{n} von {total} Konzepten** haben Belegstellen im Material.",
    "| Concept | Evidence | best score | Source |": "| Konzept | Belege | bester Wert | Herkunft |",
    "**Without evidence — written from model knowledge:**": "**Ohne Beleg — wird aus Modellwissen geschrieben:**",
    "**Material without a concept ({n} segments)** — possibly overlooked content:":
        "**Material ohne Konzept ({n} Segmente)** — möglicherweise übersehene Inhalte:",
    "- … and {n} more": "- … und {n} weitere",
    "material": "Unterlagen", "material (unchecked)": "Unterlagen (ungeprüft)", "model knowledge": "Modellwissen",
    # ── job runner ──
    "⚠️ Aborted: {error}. The intermediate state is in the job folder; the job can be continued with its pickup code.":
        "⚠️ Abbruch: {error}. Der Zwischenstand liegt im Auftragsordner; mit dem Abholcode lässt sich der Auftrag fortsetzen.",
    "Error": "Fehler", "Aborted.": "Abgebrochen.",
    "In the queue (position {pos}). {running} jobs run at the same time; this one starts automatically as soon as a slot is free.":
        "In der Warteschlange (Position {pos}). Es laufen {running} Aufträge gleichzeitig; dieser startet automatisch, sobald ein Platz frei wird.",
    "Abort requested — stops at the next chapter boundary.": "Abbruch angefordert — endet an der nächsten Kapitelgrenze.",
    "waiting · position {pos} of {total}": "wartet · Position {pos} von {total}",
    # ── pipeline findings added to the check report ──
    "{loss} — the unit is incomplete": "{loss} — die Einheit ist unvollständig",
    "chapter {n}: detail plan could not be created, emergency plan used — rework recommended":
        "Kapitel {n}: Feinplan nicht erzeugbar, Notfallplan verwendet — Nacharbeit empfohlen",
    "lesson '{title}' could not be created (JSON unreadable, even after a retry)":
        "Lektion '{title}' konnte nicht erzeugt werden (JSON unlesbar, auch nach Wiederholung)",
    "unchecked term candidate '{term}' ({where}) — evidenced neither in the inventory nor in the material":
        "ungeprüfter Begriffskandidat '{term}' ({where}) — weder im Inventar noch in den Unterlagen belegt",
    "{location} ({type}) → replaced by text — {reason}": "{location} ({type}) → Textersatz — {reason}",
    # ── diagram catalogue: structure findings ──
    "no edge — a flowchart without connections only shows boxes": "keine Kante — ein Flowchart ohne Verbindung zeigt nur Kästen",
    "no transition — a state diagram without transitions shows nothing": "kein Übergang — ein Zustandsdiagramm ohne Übergänge zeigt nichts",
    "no message between participants": "keine Nachricht zwischen Beteiligten",
    "no entry in the format 'point in time : event'": "kein Eintrag im Format 'Zeitpunkt : Ereignis'",
    "no branches below the root": "keine Äste unterhalb der Wurzel",
    "no entry in the format \"label\" : number": "kein Eintrag im Format \"Bezeichnung\" : Zahl",
    "no placed point in the format 'name: [x, y]'": "kein eingeordneter Punkt im Format 'Name: [x, y]'",
    "no line in the format 'source,target,quantity'": "keine Zeile im Format 'Quelle,Ziel,Menge'",
    "no relation between entities": "keine Beziehung zwischen Entitäten",
    "no class and no relation": "keine Klasse und keine Beziehung",
    "no step with a rating in the format 'step: score: role'": "kein Schritt mit Bewertung im Format 'Schritt: Note: Rolle'",
    "no task with a date or duration": "keine Aufgabe mit Datum oder Dauer",

    # ── Production log: DAG steps and task titles ──
    "Terminology & cross-references": "Terminologie und Querverweise",
    "Assemble the chapter script": "Kapitelskript zusammensetzen",
    "Chapter summary": "Kapitelzusammenfassung",
    "Application part of the chapter": "Anwendungsteil des Kapitels",
    "Script {id} ({name})": "Skript {id} ({name})",
    "Blocks: {title}": "Bausteine: {title}",
    "Step {layer} of {total}: {n} task(s)": "Schritt {layer} von {total}: {n} Aufgabe(n)",
    "done: {title}": "fertig: {title}",
    "failed: {title} — {error}": "fehlgeschlagen: {title} — {error}",
    "skipped: {title} — {reason}": "übersprungen: {title} — {reason}",
    "Step {layer} finished: {done} done, {failed} failed": "Schritt {layer} abgeschlossen: {done} fertig, {failed} fehlgeschlagen",
    "All tasks finished: {done} of {total}": "Alle Aufgaben abgeschlossen: {done} von {total}",
    "Stopped after step {layer}": "Angehalten nach Schritt {layer}",
    "Removed from the queue.": "Aus der Warteschlange genommen.",
}
