# -*- coding: utf-8 -*-
"""Prompt building blocks of the learning pipeline.

Process knowledge for building learning units: gap analysis with treatment
classes, depth profile, the step rule for freedom of expression, conventions
for the application part. Every function returns a plain prompt string; JSON
answers are parsed by the caller.
"""
from __future__ import annotations

import json
import re

from src.unit import diagram_types as _dtype

# Two cuts: PLANNING needs the purposes to choose the type; GENERATION also
# needs the syntax scaffold.
_DIAGRAM_CATALOG_SHORT = _dtype.prompt_catalog_short()
_DIAGRAM_CATALOG = _dtype.prompt_catalog()

JSON_ONLY = ("Answer ONLY with a single valid JSON object. "
             "No Markdown, no backticks, no text before or after it.")

LANGUAGE_NAMES = {"de": "German", "en": "English", "fr": "French",
                  "es": "Spanish", "it": "Italian"}


def language_rule(language: str) -> str:
    """Binding language rule — appended to EVERY generation prompt, because
    models (Qwen class, for instance) otherwise drift into other languages.

    The exception for protocol vocabulary is necessary: without it the rule
    demands, for units in another language, the translation of ALL JSON
    string values — including the schema values the parsers expect
    literally. A gap analysis for an English unit once answered with the
    kind and interference values translated and failed the hard gate.
    """
    name = LANGUAGE_NAMES.get((language or "de").lower(), language)
    return (f"LANGUAGE RULE (binding): write EVERY text exclusively in {name} — "
            "including all JSON string values, questions, answer options, feedback texts, labels, "
            "definitions, sample solutions and code comments. No Chinese or other "
            "foreign-language characters, no foreign-language insertions; established "
            "technical terms of the domain are allowed. EXEMPT is protocol vocabulary: where "
            "the output schema prescribes fixed values literally (field names, block type "
            "names such as 'prediction' or 'cloze', choice values such as "
            "'high|medium|low', class letters, section markers such as "
            "'=== GLOSSAR ==='), take over exactly that spelling — schema values are "
            "NEVER translated.")


def language_criterion(language: str) -> str:
    """Language discipline as a quality-check criterion (the executor checks and retries)."""
    name = LANGUAGE_NAMES.get((language or "de").lower(), language)
    return (f"Output entirely in {name}; no foreign-language characters or "
            "insertions (established technical terms allowed)")

# Compact block catalogue for the transformation phase (excerpt of the level contracts).
BLOCK_CONTRACT_COMPACT = """Allowed block types (JSON contracts, excerpt):
- {"type":"text","html":"<p>…</p>"} — running text; in lessons structure it with <h3>/<h4> (they become search anchors). Allowed HTML: p strong em ul ol li a code br h3 h4 sub sup.
- {"type":"note","variant":"key_point|info|warning","html":"…"}
- {"type":"table","caption":"…","header":["A","B"],"rows":[["a","b"]]} — number of columns per row = header.
- {"type":"accordion","items":[{"title":"In depth: …","html":"…"}]} — optional material only.
- {"type":"code","language":"bash","content":"…"}
- {"type":"quiz","questions":[{"question":"…","multiple":false,"options":[{"text":"…","correct":true,"feedback":"Why correct/wrong — required"}]}]} — with multiple=false exactly 1 correct.
- {"type":"cloze","html":"… {{1}} …","gaps":{"1":{"answers":["…"],"note":"…"}}}
  QUIZ — avoid length bias: the correct answer must not be the
  longest option. Models justify the correct answer at length and merely
  assert the wrong ones — then the learner guesses by length without
  understanding. All options about equally long and equally plausibly justified.
    WRONG: "Pure prompting, because no training is needed." (49 characters)
           "RAG, because updates take effect automatically in the database,
            without retraining the model." (96 characters, correct)
    RIGHT: both options give a similarly developed reason; the decision
           depends on the content, not on the length.

  CLOZE — the most frequent source of errors: the solution must not appear in
  the visible text of the SAME block. Otherwise the learner reads it off instead
  of recalling it, and the exercise checks nothing.
    WRONG: "The four cells are called true positives, true negatives, false
            positives and false negatives. Assign: {{1}} are correctly
            detected effects."   (the solution is two lines above)
    RIGHT: "A test correctly detects a real effect. This cell of the
            contingency table is called {{1}}."   (the solution only in the reader's head)
  The explanatory text belongs in a PRECEDING text block, not in the cloze
  itself. The cloze contains only the task.
- {"type":"matching","task":"…","pairs":[{"left":"…","right":"unique"}]}
- {"type":"flashcards","cards":[{"front":"…","back":"…"}]}
- {"type":"chart","engine":"chartjs","height":320,"description":"key message as alt text (required, >20 characters)","spec":{"type":"bar","data":{…}}} — Chart.js configuration; vegalite only when grammar features are needed, data inline. Vega-Lite can be INTERACTIVE: `params` with `bind` (slider, select field) or `select` (click, hover) makes the graphic operable — declaratively and without code execution, which is why the level-3 simulator comes only after it. Every bound parameter needs `value`; the description then names an exploration task.
- {"type":"diagram","engine":"mermaid","description":"…","code":"flowchart LR\\n A-->B"} — structure rather than data.
  NO Unicode sub/superscripts (H₀, m², xᵢ) in Mermaid code — the parser breaks on them, even quoted. Use ASCII instead: H0, m^2, x_i.
- {"type":"formula","latex":"Q \\\\cdot K^T","display":"inline|block","description":"the formula in words — required, >20 characters"} — ONLY for formulas that deserve a line of their own; simple expressions belong into the running text as HTML (see FORMAT RULES).
- {"type":"simulator","title":"…","description":"…","explanation":"<p>concrete exploration task</p>","parameters":[{"name":"x","label":"…","min":0,"max":10,"step":1,"value":3,"unit":"…"}],"code":"function model(p){ return {x:[…],series:[{name:'…',values:[…]}]}; }","output":{"kind":"line|bar|table","x_label":"…","y_label":"…"}} — a PURE function: no document/window/fetch/localStorage/setTimeout, <50ms, values as long as x. With output 'line': model(p) returns a CURVE — x runs over a range of values with >=10 data points (a sweep over ONE quantity that is NOT a slider, or over a slider's range), NEVER only the single value of the current slider position; that would sit as a single point at the left edge of the axis.
- Application part types: {"type":"prediction","question":"…","options":[{"text":"…","correct":false,"feedback":"…"}],"resolution":"…","concepts":["k1"]}; {"type":"task","title":"…","task":"…","hints":["…"],"sample_solution":"… <em>Self-check:</em> …","concepts":["k1"]}; {"type":"error_analysis","title":"…","material":"code/text","question":"…","sample_solution":"…","concepts":["k1"]}.
STEP RULE (two stages — in this order):
1. Derive the FORM OF DISPLAY from the type of content, not from convenience:
   process/dependency/decision -> diagram | comparison over >=3 features -> table
   | quantities/shares/development -> chart | parameter dependency to explore -> simulator
   | system of terms to memorise -> flashcards/accordion | mathematical relation -> formula
   | everything else -> text.
2. Within that form choose the SIMPLEST sufficient block.
Running text is the default only for content that matches none of the forms above —
not the standard one falls back on for lack of effort. No decorative chart: a
display must carry a statement the text does not carry equally well. widget
(level 4) is NOT allowed unless the detail plan justifies it explicitly.
__DIAGRAM_CATALOG__

FORMAT RULES (most frequent source of errors — HTML is the lead format):
* Emphasis EXCLUSIVELY <strong> and <em>. NEVER **bold** or *italics* —
  Markdown is not converted and appears to the learner literally as asterisks.
  Wrong: "The **technical term** denotes …"   Right: "The <strong>technical term</strong> denotes …"
* Headings <h3>/<h4>, lists <ul><li>, code <code> — never #, -, or backticks.
* FORMULAS, also in two stages: set simple expressions directly as HTML with <sub>/<sup>
  and Unicode characters (· × ≤ ≥ ± ∑ √ α β π) — readable, searchable and
  accessible. Only two-dimensional material (fractions, sums with limits, matrices, integrals)
  goes into a formula block. NEVER LaTeX in the running text.
  Wrong: "the dot product ($Q \\cdot K^T$)"   Right: "the dot product (Q · K<sup>T</sup>)"
* In fields that are NOT HTML (table.header/rows/caption, accordion.title,
  quiz questions and options, flashcards, all description fields): plain text without
  any markup — tags appear there literally.
FIELD NAMES are binding and EXACTLY as above — no substitute keys such as "text", "solution", "content" or "description" for task fields (prediction: question/options/resolution; error_analysis: material/question/sample_solution; task: title/task/hints/sample_solution)."""


# The didactics criteria (docs/didactics-criteria.md) are not loaded into
# any prompt as a whole. It enters in distilled form: the density and form
# rules in detail_plan_prompt and enrichment_prompt, the fixed additional
# criteria in critic_prompt, and deterministically in
# LearningPipeline._detail_plan_findings and the validator warnings. The full
# catalogue remains the human-readable reference.


# ─────────────────────────── Phase 0 ───────────────────────────

def learner_profile_prompt(prior_knowledge: str, learning_objective: str, time_budget_min: int | None,
                           material_note: str) -> str:
    budget = f"{time_budget_min} minutes (a constraint, not a target)" if time_budget_min else "none given"
    return f"""You are a learning designer. Normalise the input into a learner profile.
The prior knowledge may be half a sentence or a full competence profile — both are valid.

PRIOR KNOWLEDGE (user input):
{prior_knowledge}

LEARNING GOAL / KNOWLEDGE GAP:
{learning_objective}

TIME BUDGET: {budget}
MATERIAL: {material_note}

Produce JSON:
{{"known_concepts": ["…"], "unknown_concepts": ["…"], "target_level": "…",
 "context": "target group/setting in 1-2 sentences", "language": "de",
 "open_questions": ["only questions that are REALLY missing for the planning — leave empty if nothing is missing"]}}
Write all string values in the language of the user input; "language" is its ISO code.
{JSON_ONLY}"""


# ─────────────────────────── Phase 1 ───────────────────────────

def gap_prompt(profile: dict, material_context: str) -> str:
    return f"""You carry out a gap analysis for a learning unit. The scope is DERIVED from
the gap, not preset ("Docker→Kubernetes" calls for more than "Docker 24→25").

LEARNER PROFILE:
{json.dumps(profile, ensure_ascii=False, indent=1)}

MATERIAL SITUATION: {material_context}

Step 1 — kind of gap: "paradigm_shift" (a new mental model is needed),
"extension" (new concepts within the familiar model) or "version_delta".
Step 2 — interference risk: how strongly does the prior knowledge mislead
(old reflexes, false analogies)? "high"|"medium"|"low" with a rationale.
Step 3 — concept inventory after subtracting prior knowledge (what is known is
dropped or becomes "optional refresher"): EVERY genuinely new concept with a
stable ID (k1, k2, …) and a treatment class:
  V = full (derive, activate, practise; ~20-30 min) — new + high interference + relevant to application
  K = compact (explain with an example, short check; ~5-10 min)
  D = delta (difference + pitfall; ~2-5 min) — version deltas are almost never V
  R = reference (glossary/table only)
Step 4 — chapters: 2-4 related concepts each, in order of prerequisites.

SCOPE LIMIT — the most frequent and most consequential error:
The inventory answers the QUESTION ASKED, not the subject. Ask yourself for
every concept: does the person need it to reach the learning goal as stated?
If not, it does not belong in the inventory — not even as R.
The typical failure pattern, in the abstract: if the question is about the PURPOSE or the WHY
of something, the answer is not the complete mechanics behind it. The
purposes asked about are then the V concepts; the underlying mechanism
is at most K; the formalisation in technical quantities, model names and
key figures does not belong in at all. The same holds the other way round: if the question
is about the HOW, a list of purposes is no answer.
The treatment class follows the learning goal, not the importance in the subject:
what the person wanted to know is V. What they need for it is K. What the
subject offers beyond that is D or is dropped.
Check at the end: can the learning goal be answered with exactly this inventory
— and would one concept less still be enough?

Produce JSON:
{{"kind": "paradigm_shift|extension|version_delta",
 "interference": "high|medium|low", "interference_rationale": "…",
 "concepts": [{{"id": "k1", "name": "…", "concept_class": "V", "rationale": "1 sentence"}}],
 "chapters": [{{"title": "…", "concepts": ["k1","k2"], "learning_objectives": ["Can …"],
              "prerequisites": ["chapter title or empty"]}}],
 "unit_title": "…", "description": "1-2 sentences"}}
{JSON_ONLY}"""


# ─────────────────── Phase 1b: Lehrskript (roter Faden) ───────────────────

def teaching_script_prompt(gap_dict: dict, profile: dict) -> str:
    """Creates the overarching guide between gap analysis and detail plan.

    It answers what was answered nowhere before: where is each concept
    INTRODUCED, what does it build on, and what is the arc? Every later
    phase derives its precise brief from it.
    """
    return f"""You design the common thread of a learning unit — the guiding document from which
all following sections take their brief.

LEARNER PROFILE: {json.dumps({k: profile.get(k) for k in ('context', 'target_level', 'prior_knowledge')}, ensure_ascii=False)}
GAP ANALYSIS: {json.dumps(gap_dict, ensure_ascii=False, indent=1)}

Deliver three things:

1. GUIDING QUESTION — the one question the unit answers (one sentence).

2. ARC — ONE sentence per chapter naming what changes in the reader's mind.
   Not "covers topic X", but "can then tell X from Y and knows why that
   matters for Z".

3. CONCEPT GRAPH — for EVERY concept from the inventory:
   - `introduction`: the ONE lesson ID in which it is fully introduced.
     Exactly one. A concept explained in three places is explained slightly
     differently in three places — that is the error this document prevents.
   - `requires`: the concepts without which it cannot be understood.
     Direct prerequisites only, no transitive ones. No cycles.
   - `resumption`: lesson IDs in which it is applied but NOT explained
     again.
   - `contribution`: one sentence on what it contributes to the arc.

The order must hold: no concept may require something that is only
introduced later. Check this before you answer.

Produce JSON:
{{"guiding_question": "…",
 "common_thread": ["Chapter 1: …", "Chapter 2: …"],
 "nodes": [{{"id": "k1", "introduction": "l1", "requires": [],
             "resumption": ["l4"], "contribution": "…"}}]}}
{JSON_ONLY}"""


# ─────────────────────────── Phase 2 ───────────────────────────

def detail_plan_prompt(chapters: dict, concepts: list[dict], profile: dict,
                       depth_profile: str) -> str:
    return f"""Create the detail plan for ONE chapter of a learning unit (depth profile: {depth_profile}).

LEARNER PROFILE (excerpt): {json.dumps({k: profile.get(k) for k in ('context', 'target_level', 'prior_knowledge', 'known_concepts')}, ensure_ascii=False)}
Plan for THIS person. Setting the level too high is the more frequent error: what is in the
prior knowledge is assumed and not explained; whatever goes beyond it
needs a lead-in before it is named.
CHAPTER: {json.dumps(chapters, ensure_ascii=False)}
CONCEPTS WITH CLASSES: {json.dumps(concepts, ensure_ascii=False, indent=1)}

Rules: two-stage step rule — first derive the FORM OF DISPLAY from the type of content,
then the simplest block of that form. Mapping:
  process, dependency, decision path, responsibilities -> diagram
    (choice of type see DIAGRAM TYPES below — not flowchart by reflex)
  comparison over >=3 features or cases                 -> table
  quantities, shares, developments, orders of magnitude -> chart
  parameter dependency that is to be explored           -> chart with params
    (Vega-Lite, slider/select — level 2), only if that does not suffice: simulator (level 3)
  system of terms to memorise                           -> flashcards/accordion
  mathematical relation                                 -> formula
Derive INTERACTION from the learning purpose as well, not as an appendix at the end:
  make terms/designations recallable          -> flashcards
  separate what is easily confused, form pairs -> matching
  reconstruct an order or a wording            -> cloze
  confront a concrete misconception            -> quiz (plausible distractors)
  form an expectation before it is explained   -> prediction
  explore a parameter dependency               -> simulator
Interactions belong IN BETWEEN, not at the end: whoever reads 1200 words and
clicks once has acted once. As a minimum about one interaction per
400 words of reading text, spread over the lesson — that is the floor, not the
target. Across the whole unit at least five different forms of display
and interaction shall occur, spread evenly over the lessons;
a unit of text, quiz and table satisfies every counting rule and still stays
monotonous. A single quiz block per
lesson is the floor of C1, not the target — and a whole unit
that knows only quizzes misses the point, even if every lesson complies.

Every lesson with at least one V concept contains at least ONE non-textual
display — or the media plan states explicitly why none is suitable
here ("purely definitional content, no structure to show"). No decorative chart:
a display must carry a statement the text does not carry equally well.
At least one task in the application part per V concept; check criteria are
concrete and verifiable ("addresses misconception X", not "is good").

{_DIAGRAM_CATALOG_SHORT}

Produce JSON:
{{"lessons": [{{"id": "…short-slug…", "title": "…", "concepts": ["k1"],
   "learning_objectives": ["Can …"], "content_points": ["…"],
   "media_plan": ["text with h3 structure", "diagram:flowchart (course of the procedure)", "diagram:stateDiagram-v2 (states and transitions)", "matching (term → feature)", "text", "note:key_point", "flashcards (the central terms)", "quiz (typical misconception)"], "display_rationale": "process with branching — running text forces the reader to follow it in their head",
   "check_criteria": ["…", "…", "…"]}}],
 "application_part": [{{"type": "prediction|error_analysis|task", "concepts": ["k1"],
   "short_description": "…"}}],
 "case_task": {{"concepts": ["k1","k2"], "short_description": "integrates several concepts of the chapter"}}}}
{JSON_ONLY}"""


# ─────────────────────────── Phase 3: script ───────────────────────────

def cross_prompt(previous_summaries: str, glossary_state: str) -> str:
    """Working basis for the following chapters.

    `glossary_state` contains only FIXED terms (concept inventory, sources,
    approved after checking) — see src.unit.terminology. Unchecked
    candidates must not appear here: otherwise a coinage from chapter 2
    becomes the binding standard for chapters 3 to 8.
    """
    return f"""You ensure the coherence of a multi-part teaching text.
PREVIOUS CHAPTERS (summaries):
{previous_summaries or '(first chapter)'}

FIXED TERMINOLOGY (checked — only these terms are binding):
{glossary_state or '(empty)'}

Produce a compact working basis for the authors of the next sections:
binding terminology (term = meaning), concepts already explained
(only cross-reference, do not explain again), notation conventions.

TERMINOLOGY DISCIPLINE: take over only terms from the list above and
from the material. Do NOT coin new technical terms. If there is no established
term for something, describe it in a paraphrase ("the procedure by which …")
instead of forming a new word. Max. 300 words, plain text."""


def script_prompt(concept: dict, lesson_plan: dict, profile: dict, depth_profile: str,
                  cross_ref: str) -> str:
    depth = ("Developing running text; on average across the chapter 800-1500 words per V concept (K: 250-500, D: 80-200). What counts is the chapter total, not the single section: a short, dense derivation is better than a padded one. Nothing is repeated to reach length. "
             "A proven pattern, not a mandatory scheme: lead-in through a concrete problem → precise "
             "clarification of terms → justified mechanism ('because …', not asserted) → placement with "
             "limits. Complexity belongs in the tasks, not in the sentences — write clearly, "
             "not artificially complicated. An <h3> subheading every 3-5 paragraphs."
             if depth_profile == "detailed" else
             "Compact, clear texts; the key statement first, one example per concept.")
    return f"""Write the script section for ONE concept of a lesson.

TARGET GROUP: {profile.get('context', '')} — target level: {profile.get('target_level', '')}
PRIOR KNOWLEDGE (verbatim, as the learner described it): {profile.get('prior_knowledge', '(not given)')}
ALREADY KNOWN: {', '.join(profile.get('known_concepts') or []) or '(nothing given)'}
NEW FOR THIS PERSON: {', '.join(profile.get('unknown_concepts') or []) or '(not given)'}
Use the prior knowledge actively: "You know X — what is new is Y"; do not explain anything known at length.

LEVEL CALIBRATION (the most frequent error is too high, not too low):
Write for the person described above, not for a specialist audience. Every
technical term that is NOT in the concept inventory is explained in half a sentence on
its first use, or left out. Introduce symbols and
quantities (Ψ, MPa, gs) only when they are needed for understanding —
and then with an everyday equivalent. If something can be explained without
a technical term, explain it without one.

CONCEPT: {json.dumps(concept, ensure_ascii=False)} (treatment class {concept.get('concept_class')})
LESSON PLAN: {json.dumps(lesson_plan, ensure_ascii=False, indent=1)}

BINDING TERMINOLOGY AND CROSS-REFERENCES:
{{dep:cross}}

DEPTH OF TEXT: {depth}
Address at least one typical misconception ("One might think … in fact …").
If the media plan contains interactions (quiz/cloze/simulator/chart …), supply their
COMPLETE contents (questions with distractors and feedback texts, simulation logic
in words + parameter list, chart data) — the HTML phase invents nothing on top.

TERMINOLOGY DISCIPLINE: use only technical terms that occur in the binding
terminology above, in the concept inventory or in the material. Do NOT coin
terms of your own. If there is no established term for something, paraphrase
it ("the procedure by which … is achieved") — a new coinage
is always the worse choice, because learners find it nowhere else.

FORMAT: HTML markup, never Markdown — <strong> instead of **bold**, <h3> instead of #,
<ul><li> instead of dashes, <code> instead of backticks. Formulas as HTML with
<sub>/<sup> and Unicode (· × ≤ ≥ ± √ α π), never LaTeX or $…$; only fractions,
sums with limits and matrices belong in a formula block of their own.

Output: plain script text in HTML markup (<h3>, <p>, <code> …), no JSON, no preface.
{cross_ref}"""


def chapter_finalize_prompt(chapter_title: str) -> str:
    return f"""From the following script sections assemble the coherent chapter script
"{chapter_title}": order according to the lesson plan, transition sentences between sections,
unified terminology.

REMOVING DUPLICATES takes PRIORITY. The sections were written in parallel and without
seeing each other; the same foundation is therefore often introduced several times,
each time worded slightly differently. Exactly that is to be removed here: if a
section explains something an earlier one already explains, the most detailed
version stays and the others are replaced by a back-reference
("as shown above", "on this basis").
This is explicitly a shortening and is wanted. What stays forbidden is losing
CONTENT — a statement that appears in only one place must be kept.
Do not invent new facts.

SECTIONS:
{{dep:*process}}

Output: the complete chapter script (HTML markup), followed by the line
=== GLOSSAR === and below it, one per line,
"term :: short form (1-2 sentences, shown as hover explanation in the text) :: definition (more detailed, for the glossary page) :: lesson-id"
for every technical term NEWLY introduced in this chapter. The short form must be
understandable on its own — it appears when the pointer rests on the term,
in the middle of reading, without context."""


# ─────────────────────────── Phase 4: Transformation ───────────────────────────

# Lines of the block contract that belong to exactly ONE block type. Everything
# else (format rules, step rule, language discipline) always applies.
# "typ" is still recognised so that a contract text written for the earlier
# German format keeps working.
_TYPE_LINE = re.compile(r'^\s*-\s*\{"(?:type|typ)"\s*:\s*"([a-z_]+)"')
# Explanation paragraphs that belong to one type and end with a blank line.
_TYPE_SECTION = re.compile(r"^\s{2}([A-ZÄÖÜ]+)\s+—", re.M)


# Translation of media plan nomenclature into block types (English plan
# words, German words, and the type names of earlier format versions). Used
# by contract_for (prompt cut) AND by the pipeline's detail plan density
# check — both must recognise the same entries, otherwise a plan counts as
# "without interactions".
TYPE_TRANSLATION = {
    # English plan words
    "diagram": "diagram", "table": "table", "matching": "matching", "cloze": "cloze",
    "prediction": "prediction", "callout": "note", "note": "note", "chart": "chart",
    "formula": "formula", "exercise": "task", "task": "task", "accordion": "accordion",
    "simulation": "simulator", "error analysis": "error_analysis", "flashcard": "flashcards",
    "flashcards": "flashcards", "text": "text", "code": "code", "quiz": "quiz", "widget": "widget",
    # German plan words and the German type names of earlier format versions
    "diagramm": "diagram", "tabelle": "table", "zuordnung": "matching", "lueckentext": "cloze",
    "vorhersage": "prediction", "hinweis": "note", "formel": "formula", "aufgabe": "task",
    "akkordeon": "accordion", "fehleranalyse": "error_analysis", "karteikarten": "flashcards",
}


def contract_for(types_) -> str:
    """Block contract, cut to the types actually planned.

    The full contract describes 17 block types and so makes up about half
    of the transform prompt — although a media plan names three to five
    types. The diagram catalogue alone is 9,000 characters and is
    superfluous if no diagram is planned at all.

    A smaller, targeted prompt is not only cheaper: it gives the model
    less opportunity to invent components nobody ordered.
    """
    # Media plans may be written in the unit's language or name the types of
    # an earlier format ("tabelle", "zuordnung", "lueckentext"). They are
    # translated, and if even ONE entry stays unclear, the FULL contract
    # applies. A prompt that is too large costs tokens; a missing contract
    # costs the component.
    foreign = TYPE_TRANSLATION
    known = {"text", "note", "table", "accordion", "code", "diagram",
               "chart", "formula", "quiz", "cloze", "matching",
               "flashcards", "prediction", "simulator", "widget", "task",
               "error_analysis"}
    requested: set[str] = set()
    for entry in (types_ or []):
        header = re.split(r"[:(]", str(entry))[0].strip().lower()
        word = header.split()[0] if header.split() else ""
        type_ = word if word in known else foreign.get(word) or foreign.get(header)
        if not type_:
            return BLOCK_CONTRACT_COMPACT      # unclear -> leave nothing out
        requested.add(type_)
    if not requested:
        return BLOCK_CONTRACT_COMPACT

    rows = BLOCK_CONTRACT_COMPACT.split("\n")
    out_, skip = [], False
    for z in rows:
        m = _TYPE_LINE.match(z)
        if m:
            skip = TYPE_TRANSLATION.get(m.group(1), m.group(1)) not in requested
            if not skip:
                out_.append(z)
            continue
        # continuation lines of a type line share its fate
        if skip and z.startswith("  ") and not _TYPE_SECTION.match(z):
            continue
        skip = False
        out_.append(z)
    text = "\n".join(out_)

    # The diagram catalogue only if a diagram is planned at all.
    if "diagram" not in requested and _DIAGRAM_CATALOG in text:
        text = text.replace(_DIAGRAM_CATALOG,
                            "(Diagram types not needed here.)")
    return re.sub(r"\n{3,}", "\n\n", text)


def transform_prompt(lesson_plan: dict, script_excerpt: str, depth_profile: str) -> str:
    return f"""Transform a script section into lesson blocks (unit.json format).
SCOPE OF THIS OUTPUT:
Implement the media plan COMPLETELY — every display and every
interaction named there belongs into this output. A later pass adds
what is missing; do not rely on it, but deliver a complete lesson
here already. Keep the wording compact: a
diagram often replaces three paragraphs, a table a comparative text.

Do not invent new facts — only transform.

PRIORITY in apparent contradiction: the script text is to be taken over
completely — except the passages REPLACED by a display planned in the media plan.
Whoever shows a process as a diagram does not also write it out as a paragraph;
that would be duplication, not completeness. Everything
else goes unshortened into text blocks.

So do NOT condense or omit the script text: the complete running text goes into text blocks (with <h3> subheadings
as search anchors). Every lesson contains at least one self-check (quiz, cloze or
matching) with feedback for every option. The text must carry as plain reading text;
interactions complement it.

{contract_for(lesson_plan.get('media_plan'))}

LESSON PLAN (observe the media plan!): {json.dumps(lesson_plan, ensure_ascii=False, indent=1)}

SCRIPT:
{script_excerpt}

Produce JSON:
{{"id": "{lesson_plan.get('id', 'l1')}", "title": {json.dumps(lesson_plan.get('title', ''), ensure_ascii=False)},
 "learning_objectives": {json.dumps(lesson_plan.get('learning_objectives', []), ensure_ascii=False)},
 "concepts": {json.dumps(lesson_plan.get('concepts', []), ensure_ascii=False)},
 "blocks": [ … ]}}
{JSON_ONLY}"""


# The type catalogue is inserted at load time: BLOCK_CONTRACT_COMPACT is a
# plain string, not an f-string — a placeholder in curly braces would stay in
# it literally.
BLOCK_CONTRACT_COMPACT = BLOCK_CONTRACT_COMPACT.replace(
    "__DIAGRAM_CATALOG__", _DIAGRAM_CATALOG)


TASK_CONTRACT = """The three task types with their EXACT field names (binding —
'task' is NOT 'question', 'sample_solution' is NOT 'solution'):
1. {"type":"prediction","question":"<p>…?</p>","options":[{"text":"…","correct":false,"feedback":"…"},{"text":"…","correct":true,"feedback":"…"}],"resolution":"<p>… and why.</p>","concepts":["k1"]}
   Required: question, resolution. options optional (then a free-text commitment).
2. {"type":"error_analysis","title":"…","material":"faulty code/text (raw text)","question":"<p>Find and justify …</p>","sample_solution":"<p>… <em>Self-check:</em> …</p>","concepts":["k1"]}
   Required: material, question, sample_solution.
3. {"type":"task","title":"…","task":"<p>Task with the expected scope.</p>","hints":["<p>…</p>"],"sample_solution":"<p>… <em>Self-check:</em> …</p>","concepts":["k1"]}
   Required: task, sample_solution. The case task is a "task" whose title begins with "Case task: …"."""


def tasks_prompt(chapter_title: str, detail_plan: dict, concepts: list[dict]) -> str:
    return f"""Create the APPLICATION PART of the chapter "{chapter_title}" — bundled tasks
with which learners test themselves AFTER working through the comprehension part.
Order from guided to open: prediction → error_analysis → task(s) → at the end
an integrating case task (type "task", title begins with "Case task:").

CONCEPTS: {json.dumps(concepts, ensure_ascii=False)}
PLANNED IN THE DETAIL PLAN: {json.dumps({'application_part': detail_plan.get('application_part'), 'case_task': detail_plan.get('case_task')}, ensure_ascii=False, indent=1)}
SCRIPT CONTEXT (content the tasks refer to):
{{dep:cross}}

{TASK_CONTRACT}

Conventions: a prediction demands a real commitment; the resolution takes up the plausible
wrong expectation. Sample solutions are teaching text: they explain the why, name typical
deviations and end with "<em>Self-check:</em> …". Every task carries "concepts": [IDs].
Every V concept of the chapter occurs in at least one task.

Produce JSON: {{"exercises": [ …blocks of the types prediction|error_analysis|task… ]}}
{JSON_ONLY}"""


def chapter_meta_prompt(chapter_title: str) -> str:
    return f"""Summarise, for the coherence of the following chapters, what the chapter "{chapter_title}"
has introduced.

CONTENT:
{{dep:*process}}

Produce JSON: {{"summary": "5-8 sentences: concepts introduced, central examples,
wordings that later chapters can refer back to",
"new_terms": [{{"term": "…", "definition": "1-2 sentences", "lesson": "lesson-id"}}]}}
{JSON_ONLY}"""


# ─────────────────────────── Abschluss ───────────────────────────

def final_test_prompt(unit_title: str, chapter_summaries: str) -> str:
    return f"""Create the final test of the learning unit "{unit_title}". 3-5 questions covering ALL
chapters (not only the last one); distractors are based on real errors of reasoning;
every feedback explains the why. Avoid length bias: the correct answer
must not be the longest option — all options about equally long and equally
plausibly worded, otherwise the learner guesses by length instead of content.

CHAPTERS:
{chapter_summaries}

Produce JSON: {{"title": "Final test", "questions": [{{"question": "…", "multiple": true|false,
"options": [{{"text": "…", "correct": true, "feedback": "…"}}]}}]}}
{JSON_ONLY}"""


def fact_check_prompt(lesson_text: str, evidence: list[str]) -> str:
    """Hallucination check against the material inventory: statements of the
    lesson are checked against the most relevant source evidence."""
    return f"""You check a teaching text AGAINST binding source material (fact check).
Judge only statements of content that concern the material — general knowledge
of the domain does not count as hallucination.

SOURCE EVIDENCE (binding):
{chr(10).join(f"[{i+1}] {b}" for i, b in enumerate(evidence))}

TEACHING TEXT:
{lesson_text}

Produce JSON: {{"findings": [{{"claim": "verbatim or closely paraphrased",
"status": "evidenced|not_evidenced|contradicts", "evidence": "number or empty",
"comment": "1 sentence"}}]}} — list ONLY not_evidenced/contradicts; an empty
list if everything is covered. {JSON_ONLY}"""


def critic_prompt(lesson_compact: str, check_criteria: list[str],
                  depth_profile: str) -> str:
    """Didactic check on a NUMBERED short form of the lesson.

    With the whole lesson as JSON the critic was cut off on long lessons, and
    its findings carried no reference to a block: a correction then had to
    rewrite the whole lesson, which was expensive, broke off on length and
    let the model touch things nobody had objected to.

    With the block number in the finding, ONE block can be replaced in a
    targeted way.
    """
    return f"""You are a didactic critic. Check the lesson against the criteria.
A finding only counts with evidence from the text — "seems good" does not count.

CRITERIA (excerpt from the criteria catalogue):
{chr(10).join('- ' + k for k in check_criteria)}
- Feedback texts explain the why (not a mere right/wrong)
- Depth profile '{depth_profile}': the text carries as plain reading text
- description (alt texts) states the key message
- Self-checks are SPREAD over the lesson (guideline about one per
  400 words of reading text), not only at the end — a stretch of reading with one
  final question misses C1b
- The forms of interaction vary and follow the learning purpose (terms ->
  flashcards, easily confused -> matching, order -> cloze,
  misconception -> quiz, expectation -> prediction); two identical forms
  directly in a row are a finding (C1c)

LESSON (one entry per block, [n] is the block number):
{lesson_compact}

Every finding MUST state the block number it refers to. If it concerns
the lesson as a whole (a missing self-check, for instance), set block to -1.

Produce JSON: {{"score": 1-5, "findings": [{{"block": 3, "criterion": "…",
"evidence": "quote/location", "correction": "concrete instruction"}}]}}

SCORE (anchored — it decides whether anything is changed at all):
5 = no findings. 4 = solid lesson, only minor points without effect on learning —
report findings, but no intervention needed. 3 = single blocks noticeably miss a
criterion (patch them in a targeted way). 2 = several criteria violated or a
core didactic flaw. 1 = the lesson misses its purpose.
Give the score by the EFFECT ON LEARNING of the lesson as a whole, not by the
number of findings: three minor wording points in a sound
lesson are a 4, not a 2. {JSON_ONLY}"""


def block_patch_prompt(blocks_json: str, corrections: str, language: str,
                       block_contract: str) -> str:
    """Replaces SINGLE blocks instead of a whole lesson.

    The output covers only the blocks actually objected to — one or two
    instead of 15,000 characters. It therefore cannot break off, and blocks
    nobody objected to stay literally untouched: they are not even sent
    through the model.
    """
    return f"""Revise ONLY the following blocks according to the corrections.

BLOCKS TO REVISE (with their number in the lesson):
{blocks_json}

CORRECTIONS:
{corrections}

RULES:
- Return ONLY the revised blocks, each with its unchanged number.
- The block type stays the same. Whoever receives a quiz block returns a quiz block.
- Change only what the correction asks for. Everything else stays literally as it is.
- A block you cannot improve is left out — not made worse.

{block_contract}

{language_rule(language)}

Produce JSON: {{"replacements": [{{"number": 3, "block": {{…}}}}]}} {JSON_ONLY}"""


# ─────────────────── Terminology check (verdict on candidates)
# ───────────────────

def terminology_verdict_prompt(candidates_: list[dict], set_ones: str,
                               material: str) -> str:
    """Judges uncovered term candidates.

    Receives only the remainder that the whitelist, the source corpus and
    compound splitting could not settle — which keeps the call cheap. The
    occurrence is attached so that the verdict does not come from the
    model's memory.
    """
    list_ = "\n".join(
        f"- {k['term']} (occurrence: {k.get('occurrence', '?')})"
        for k in candidates_)
    return f"""You check the technical terminology of a learning unit for coinages.

FIXED TERMINOLOGY (concept inventory and sources):
{set_ones or '(empty)'}

MATERIAL — occurrences of the terms checked (authoritative source):
{material or '(no material)'}

TERMS TO CHECK:
{list_}

For EVERY term exactly ONE of three verdicts:

1. ESTABLISHED — it occurs like this in standards, legal texts, textbooks or the
   material. Judge strictly: a term counts as established only
   if you can place it concretely. Plausible-sounding, correctly formed
   compounds are NOT automatically established — they are exactly the
   typical case.
2. COINAGE — the text coined it itself, but there is an
   established term for it. Give it as `substitute`. The substitute must be a
   short noun phrase that can GRAMMATICALLY TAKE THE PLACE of the term
   at the occurrence — NEVER an explanation, classification or
   meta-description (wrong: "personal pronoun (no technical term)",
   "paraphrase for …"; right: "Family-Wise Error Rate (FWER)").
3. NO_TERM — the hit is not a technical term at all, but an
   extraction artefact: a pronoun, an everyday word, a sentence fragment,
   a number. Then set `no_term: true` and leave `substitute` EMPTY
   — such hits are discarded, not replaced.

If there is no established term for a genuine coinage, that is
acceptable — then `no_term: true`, because an explanatory paraphrase
cannot be inserted into a sentence.

Produce JSON:
{{"verdicts": [{{"term": "…", "established": true, "no_term": false,
  "evidence": "source and location", "definition": "…", "substitute": ""}},
 {{"term": "…", "established": false, "no_term": false, "evidence": "",
  "definition": "", "substitute": "established term (insertable noun phrase)"}},
 {{"term": "…", "established": false, "no_term": true, "evidence": "",
  "definition": "", "substitute": ""}}]}}
{JSON_ONLY}"""


# ─────────────────── Consolidation: redundancy pass ───────────────────

def redundancy_prompt(overview: str) -> str:
    """Looks for repeated explanations across the WHOLE unit.

    The critic deliberately checks each lesson on its own and therefore
    cannot see repetitions between lessons structurally — worse still, its
    criterion A1 ("assume nothing that was not explained") pushes it to ask
    for additional explanations. This pass is the counterpart.
    """
    return f"""You check a learning unit for repeated explanations.

OVERVIEW (lesson → subheadings → concepts explained):
{overview}

Find concepts that are explained in SEVERAL places instead of being explained once and
cross-referenced afterwards. What is sought is not every repetition of a word, but
the renewed DERIVATION of something already introduced.

NOT findings are intended resumptions: application, integration
and final lessons of a chapter (checklists, case training, synthesis,
"reading path") TAKE UP introduced concepts AGAIN by design — that is
consolidation, not redundancy. Report such lessons only if they actually
DERIVE a concept a second time (definition and justification from
scratch), instead of applying or summarising it.

For every hit: where does the complete explanation belong (usually the
first occurrence or the place of introduction planned in the teaching script), and which
places are shortened to a back-reference?

Report only what you can support with lesson ID and heading. If you find
nothing, return an empty list — do not invent findings.

Produce JSON:
{{"findings": [{{"concept": "…", "introduction": "l2",
  "duplicates": [{{"lesson": "l5", "location": "heading", "shortening": "back-reference to l2"}}]}}]}}
{JSON_ONLY}"""


# ─────────────────── Enrichment: interaction and display ───────────────────

def enrichment_prompt(lesson_compact: str, media_plan: str, situation: str,
                      block_contract: str) -> str:
    """Second pass per lesson, exclusively for illustration.

    Why separate: in a single call prose and interaction compete for the
    same token budget. The block list starts with text, so whatever lets the
    learner act is the first to fall off at the end; in the logs every
    truncated answer ended in the middle of the lesson.

    This call sees the lesson only in short form and returns ONLY new
    blocks. The output stays small, and illustration can no longer be
    crowded out by prose.
    """
    return f"""You enrich a finished lesson with illustration and activity.

LESSON (short form, one entry per existing block):
{lesson_compact}

MEDIA PLAN FROM THE DETAIL PLAN:
{media_plan or '(none)'}

FINDING:
{situation}

Add what is missing. Guiding questions in this order:
1. Where does the learner have to follow something in their head that a picture could show?
   Process, dependency, decision path -> diagram.
   Comparison over several features -> table.
   Quantities, shares, developments -> chart. Parameter dependency -> chart with params.
2. Where do they read more than 400 words without acting once?
   Recall terms -> flashcards. Separate what is easily confused -> matching.
   Reconstruct an order -> cloze. Confront a misconception -> quiz.
   Form an expectation before the explanation -> prediction.
3. Is a form the same three times in a row? Then change it.

RULES:
* Add blocks ONLY. Existing ones are not changed, not reworded,
  not replaced. Do NOT return the running text.
* Put every new block where its content is covered — not at the
  end. `after_block` is the index of the block it shall follow
  (-1 = at the very beginning, 0 = after the first block).
* No new block of the same type directly next to an existing one — two
  prediction blocks in a row are a duplicate, not a distribution.
* Every new block must carry a statement the text does not carry equally
  well. No decoration, no repetition of what was said in picture form.
* Two to five new blocks. If really nothing is missing, return an empty list
  — do not invent anything just to fill the list.

{block_contract}

Produce JSON:
{{"new_blocks": [{{"after_block": 2, "rationale": "…", "block": {{"type": "…", …}}}}]}}
{JSON_ONLY}"""
