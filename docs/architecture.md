# Architecture

LernWerkstatt turns a description of what someone already knows and what
they want to learn into a self-contained HTML learning unit. The scope of the
unit is derived from the gap between the two, not set by the user.

## Overview

```text
Browser ──► Gradio wizard (src/ui) ──► job runner (src/pipeline/job_runner.py)
                                            │
                                            ▼
                         LearningPipeline (src/pipeline/learning_pipeline.py)
                         │        │            │               │
                     prompts   DAG executor   LLM client    unit layer
                   (src/prompts) (dag.py)    (src/llm)    (src/unit: normalise,
                                                            validate, degrade,
                                                            assemble)
                                            │
                                            ▼
                    work/job-NNNN-<slug>/  state.json · content/unit.json · dist/*.html
```

The wizard only starts jobs and shows their state. Production runs in a
server-side task, so a job keeps running when the window is closed. All
state is in the job folder; a job can be resumed after a restart.

## The pipeline

| Phase | What happens | Model |
|---|---|---|
| 0 Profile | normalise prior knowledge and goal into a learner profile; ask only questions that are really open | fast |
| 1 Gap analysis | kind of gap, interference risk, concept inventory with treatment classes, chapters | strong |
| 1b Teaching script | the common thread: where each concept is introduced, what it builds on | strong |
| 1c Material coverage | which concept is evidenced in the uploaded material, and which material matches no concept (embedder only) | — |
| Checkpoint | the user reviews scope and inventory, may re-classify or remove concepts | — |
| 2 Detail plans | per chapter, in parallel: lessons, media plan, check criteria; a deterministic density check with one revision | strong |
| 3 Run A: script | per concept, a script section; then chapter assembly and an early summary | strong / fast |
| 4 Run B: blocks | per lesson, transformation into blocks; application part; validation and repair | fast |
| 5 Consolidation | final test, critic pass over all lessons in parallel, redundancy pass, fact check | strong / fast |
| 6 Final gate | normalisation, validation of the whole unit, downgrading of unrepairable blocks, assembly | — |

Run A of chapter *k+1* runs in parallel with run B of chapter *k*; run B
stays sequential, so the reading order is guaranteed.

### Treatment classes

The gap analysis gives every new concept one class, and the class decides
how much the unit invests in it:

| Class | Meaning | Rough time |
|---|---|---|
| V | full: derive, activate, practise | 20–30 min |
| K | compact: explain with an example, short check | 5–10 min |
| D | delta: difference and pitfall | 2–5 min |
| R | reference: glossary only | — |

The sum gives the learning time, the learning time the format (impulse,
learning unit, book) and the depth profile (`compact` or `detailed`). If the
user set a time budget and the derived scope exceeds it, the pipeline
proposes downgrades; it never cuts silently.

### Traceability

The DAG tasks are created **from** the concept inventory, and every lesson
carries the concept IDs it covers. The final gate fails if a concept of
class V, K or D appears in no lesson. A concept the detail plan forgot is
attributed to the first lesson of its chapter instead of being lost.

## The DAG executor

`src/pipeline/dag.py` runs a plan of LLM tasks in layers of independent
tasks, in parallel up to a limit. Tasks refer to the outputs of others with
`{dep:TASK_ID}` and `{deps:PHASE}`. Tasks with check criteria get a quality
check by the fast model; a score below 3 triggers one retry with the
feedback. A failed task skips everything that depends on it; a stop request
takes effect after the current layer.

## Checking and repairing

Model output goes through several deterministic layers before anything is
retried:

1. **JSON parsing** (`src/llm/json_parser.py`): five strategies, including
   closing a truncated answer. German field names in model output are mapped
   to the English format (`src/llm/legacy_keys.py`).
2. **Aliases**: invented block types and substitute field names are mapped
   to the real ones (`learning_pipeline.py`).
3. **Normalisation** (`src/unit/normalization.py`): Markdown and LaTeX
   remnants become HTML; simple formulas become HTML with sub/sup, the rest
   MathML via KaTeX at build time; Mermaid labels are secured; HTML is
   reduced to an allowlist.
4. **Validation** (`src/unit/validator.py`): structure, field contracts,
   references, didactic minimums, simulator trial runs in Node.js, Mermaid
   syntax probes, language mixing. Errors block delivery; everything that
   would only improve the unit is a warning.
5. **Repair**: per lesson, first a patch of only the blocks a finding refers
   to, then a full repair that is accepted only if it makes the lesson
   demonstrably better. Certain warnings are repaired as well (a gap that
   can be read off, quiz options without feedback, controls without a
   label, among others).
6. **Degradation** (`src/unit/degradation.py`): a displaying block that is
   still broken after all repairs is replaced by its own description as
   text. The learner loses the graphic but keeps the statement, and the
   report says what was replaced. Interactions are never replaced:
   swapping a quiz for its description would take the activity away and
   fake completeness. Structural errors stay blocking.

If the final gate still fails, a clearly marked draft is assembled, so the
user always has a visible result and can close the errors through rework.

## Terminology control

Models like to coin terms. `src/unit/terminology.py` separates **fixed**
terms (concept inventory, uploaded material, checked terms) from
**candidates**. Only fixed terms go into prompts as binding. Candidates are
checked cheapest first: whitelist, source corpus, compound splitting; only
the rest goes to the model, which judges each one as established, coined
(with an insertable substitute) or no term at all. Replacements are applied
at word boundaries.

The candidate search looks for terms the text explicitly establishes, using
German definition patterns ("bezeichnet", "versteht man unter",
"sogenannte") on capitalised words. In units in other languages it finds
nothing by design; terminology control there rests on the concept
inventory, the source corpus and the glossary harvest, which work in any
language. Missing a coinage is the safe failure; changing a correct term
would not be.

Two things are open. The thresholds (`MIN_LENGTH = 9`, the function word
list, the base components for compound splitting) are conservative
estimates, not measured on real output. And candidates are reported in their
inflected form, because the check layer deliberately has no dependency
beyond the standard library; a lemmatiser would remove that.

## The delivered unit

`src/unit/assembler.py` combines `assets/shell.html`, the unit JSON and the
renderer libraries into one HTML file. The shell provides navigation,
search, glossary with hover explanations, progress in the browser, and a
renderer for each block type. Its interface texts come from
`src/unit/i18n.py` in five languages and follow the unit's language.

The unit format is described in [unit-format.md](unit-format.md).

## Interface languages

The wizard is available in English and German. Interface texts are written
in English in the code and looked up in a catalog per language
(`src/i18n/`). Messages produced by background jobs are stored as message
objects and rendered in the language of whoever looks at them. Validator
messages are rendered in the interface language in the check report and
always in English in repair prompts and logs. See
[development.md](development.md#adding-an-interface-language).

## Module map

| Path | Purpose |
|---|---|
| `app.py` | entry point; start-up diagnosis |
| `src/config.py`, `src/core/env.py` | configuration from the environment |
| `src/core/jobs.py` | job register (SQLite), pickup codes |
| `src/core/stop_signal.py` | shared stop flag |
| `src/ui/wizard.py`, `src/ui/preview.py` | the five-step interface |
| `src/i18n/` | interface texts per language |
| `src/pipeline/job_runner.py` | server-side runs, queue |
| `src/pipeline/learning_pipeline.py` | the orchestration |
| `src/pipeline/gap_analysis.py` | treatment classes, scope, prioritisation |
| `src/pipeline/teaching_script.py` | common thread and concept graph |
| `src/pipeline/material_coverage.py` | concepts against uploaded material |
| `src/pipeline/inventory.py`, `inventory_builder.py` | embedding index, segmentation of material |
| `src/pipeline/file_reader.py` | text from PDF, DOCX, PPTX, Markdown, HTML, CSV, plain text |
| `src/pipeline/dag.py` | DAG executor |
| `src/pipeline/technical_report.py` | usage and content figures |
| `src/prompts/` | all prompts |
| `src/llm/` | OpenAI-compatible client, JSON parser, legacy key mapping |
| `src/unit/` | normalisation, validation, degradation, terminology, term marking, diagram types, assembly, unit texts |
| `src/exporters/word_exporter.py` | Word handout |
| `assets/shell.html` | the unit's single-page application |
| `assets/*_probe.mjs` | Node probes: simulator, Mermaid, MathML, renderers |
| `scripts/` | benchmark, service check, maintenance, static check, vendor copy |
