# Didactics criteria

The criteria a learning unit is held to, and where the application enforces
each one. Criterion IDs (A1, C1b …) appear in prompts, validator messages and
the code, so they are kept stable.

Enforcement, from weakest to strongest:

- **prompt** — the instruction to the model;
- **plan check** — the deterministic density check of each detail plan,
  with one revision;
- **critic** — the didactic critic checks the lesson and patches the
  blocks it objects to;
- **warning** — the validator reports it; some warnings go to the repair;
- **error** — the validator blocks delivery until it is fixed.

A finding only counts with evidence from the text. "Seems good" does not.

## A — Fit to the learner profile

| ID | Criterion | Enforced by |
|---|---|---|
| A1 | Nothing is assumed that the profile marks as unknown and no earlier lesson explained. | prompt (script, with the brief from the teaching script) · critic |
| A2 | Nothing marked as prior knowledge is explained again at length; a short sentence that connects to it is welcome. | prompt · critic |
| A3 | Language level and examples fit the target group described in the profile. | prompt (level calibration) · critic |
| A4 | The scope follows the documented gap analysis, and the treatment classes are carried out: V concepts are derived, activated and practised; D concepts get the difference and the pitfall, not a long derivation. | gap analysis and checkpoint · prompt · validator warning if a V concept is practised in no application part |

## B — Didactic structure

| ID | Criterion | Enforced by |
|---|---|---|
| B1 | The lesson pursues its learning objectives from the detail plan; no objective is left unserved, no larger content is without an objective. | check criteria from the detail plan · critic |
| B2 | Simple to complex; new terms are explained when first introduced and used consistently afterwards, across all lessons. | teaching script (one place of introduction per concept) · terminology control |
| B3 | At least one concrete example or analogy per core concept. | prompt · critic |
| B4 | At least one typical misconception is addressed ("One might think … in fact …"). | prompt · critic |
| B5 | Cross-references instead of repetition ("as shown in lesson 2"). | teaching script · chapter assembly removes duplicates · redundancy pass across the unit |
| B6 | Central statements are derived or justified, not only asserted. | prompt · critic |
| B7 | The lesson names where what it explains ends, does not apply, or deliberately does nothing. | prompt · critic |
| B8 | In the depth profile `detailed`, the lesson carries as plain reading text (800–1500 words of developing prose); interactions do not replace text. | prompt · validator warning for very short lessons |

## C — Exercises and feedback

| ID | Criterion | Enforced by |
|---|---|---|
| C1 | Every lesson has at least one self-check (quiz, cloze, matching, flashcards) that tests the objectives, not side issues. | prompt · validator warning |
| C1b | Self-checks are spread over the lesson, about one per 400 words of reading text, not only at the end. | plan check · enrichment pass (with one targeted second attempt) · critic · validator warning |
| C1c | The form follows the purpose: recall terms → flashcards; separate what is easily confused → matching; reconstruct an order → cloze; confront a misconception → quiz; form an expectation before the explanation → prediction. A unit that knows only quizzes misses C1c even if every lesson meets C1. | plan check · critic · validator warnings for monocultures |
| C2 | Quiz distractors are plausible: they are based on real errors of reasoning. Length bias is avoided: the correct answer is not regularly the longest option. | prompt · validator warning for consistent length bias, then a critic criterion for every quiz lesson |
| C3 | Every feedback explains the why: wrong feedback names the error of reasoning, right feedback confirms the reason. No bare "Right!/Wrong!". | prompt · validator warning for missing feedback, which goes to the repair |
| C4 | The final test covers all modules, not only the last lesson. | prompt |

## CA — Application part per chapter

| ID | Criterion | Enforced by |
|---|---|---|
| CA1 | Every module has an application part (`exercises`), after the complete comprehension part; no large open tasks in the middle of the text. | pipeline structure · validator warning if missing |
| CA2 | The application part covers the objectives of all lessons of the module and mixes the forms (prediction, error analysis, open task); it ends with an integrating case task across several concepts. | prompt |
| CA3 | Sample solutions explain the why, name typical deviations and end with a self-check question. | prompt · quality check of the task |
| CA4 | Predictions ask for a real commitment before the resolution; the resolution takes up the plausible wrong expectations. | prompt |

## D — Media and interactions

| ID | Criterion | Enforced by |
|---|---|---|
| D1 | Every block of levels 2–4 visibly contributes to an objective (no decorative chart); the step rule is kept (the lowest sufficient level); level-4 blocks are justified in the detail plan. | prompt (step rule) · validator warning for every widget, warnings for heavy Vega-Lite without interaction and for units without a single diagram |
| D2 | Simulators and interactive charts come with a concrete exploration task ("Set X to …, observe Y"). | prompt · validator warning, which goes to the repair |
| D3 | The alternative text (`description`) is present and states the key message of the graphic, not only its type. | validator error if missing · warning if very short |

## E — Binding to facts

With uploaded material:

| ID | Criterion | Enforced by |
|---|---|---|
| E1 | Checkable statements (numbers, procedures, responsibilities, sections of law, versions) agree with the material, including numbers in charts and tables. | fact check against the material inventory (needs an embedder); a contradiction triggers a revision |
| E2 | Statements without evidence are removed or marked as general knowledge. | fact check findings · critic |
| E3 | The provenance note names the sources correctly. | assembled from the job data |

Without material:

| ID | Criterion | Enforced by |
|---|---|---|
| E4 | No contradictions between lessons; the unit says visibly that its content is based on model knowledge. | redundancy pass · provenance note in every unit |

## F — Technical checks

| ID | Criterion | Enforced by |
|---|---|---|
| F1 | The unit passes validation without errors. | final gate; otherwise a marked draft is delivered |
| F2 | Every page is reachable and every renderer runs. | renderer and browser tests in the test suite; simulator trial runs and Mermaid syntax probes at generation time |
| F3 | The file works without a network. | embedded libraries; the assembler reports a CDN fallback |
