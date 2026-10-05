# Phase 5: enrichment and critique

Phase 5 adds blocks to the lessons, creates the application part of each
chapter and the final test, and reviews the unit.

Implementation: `src/pipeline/learning_pipeline.py`. Prompts:
`enrichment_prompt`, `tasks_prompt`, `final_test_prompt`, `critic_prompt`,
`block_patch_prompt`, `fact_check_prompt`, `redundancy_prompt`.

## Enrichment

The enrichment is executed per lesson by the strong model, after the lesson
has been produced. The input consists of a numbered short form of the lesson
(one entry per block), the media plan and a statement of the current number
of interactions and the target.

The prompt asks for additions under three questions:

1. Which content describes a process, a dependency, a comparison or a
   quantity that can be displayed?
2. Which passages contain more than 400 words without an interaction?
3. Does the same form occur three times in succession?

| Rule | Content |
|---|---|
| additions only | existing blocks are not changed; the running text is not returned |
| position | each new block is inserted after the block whose content it refers to |
| check | each new block is validated individually; blocks with errors are discarded |
| succession | two interactions or displays of the same type in direct succession are not inserted; tasks with identical text are not inserted |

The target value is one interaction per 400 words of reading text, rounded
up; in the detailed profile at least two from 500 words. If the target is not
reached, a second request names the shortfall. No further requests follow.
The technical report records the numbers of added and discarded blocks.

## Application part

The strong model creates the application part of each chapter from
`application_part` and `case_task` of the detail plan.

| Rule | Content |
|---|---|
| order | prediction, error analysis, tasks, case task |
| prediction | requires a choice or a stated expectation; the resolution refers to the plausible wrong expectations |
| sample solutions | contain the justification, typical deviations and a final self-check question |
| coverage | each V concept of the chapter occurs in at least one task |

The field contracts of the three task types are described in
[unit-format.md](../unit-format.md#application-part).

## Consolidation

After the last chapter, four steps are executed for the unit.

### Final test

The strong model creates three to five questions covering all chapters. The
prompt requires distractors based on typical errors of reasoning, feedback
with a justification, and options of similar length. A result without a list
of questions is not included in the unit.

### Critique

The strong model reviews each lesson; the lessons are reviewed in parallel.
The input is a numbered short form of the lesson. The criteria consist of:

- the check criteria of the lesson from the detail plan;
- fixed criteria: feedback contains a justification; in the detailed profile
  the text is readable without the interactions; alternative texts state the
  key message; self-checks are distributed over the lesson; interaction forms
  vary and correspond to the learning purpose;
- up to three findings of the validator for this lesson, marked as proven;
- a criterion on answer length in quizzes, if the validator has found that
  correct answers are systematically the longest option in the unit.

Each finding contains the number of the block concerned, or `-1` for the
lesson as a whole, and a reference to the text.

The prompt defines the score as follows:

| Score | Definition | Processing |
|---|---|---|
| 5 | no findings | none |
| 4 | minor points without effect on learning | findings recorded |
| 3 | individual blocks do not meet a criterion | blocks produced again |
| 2 | several criteria not met, or a fundamental didactic deficiency | blocks or lesson produced again |
| 1 | the lesson does not fulfil its purpose | blocks or lesson produced again |

From score 3, the blocks named in the findings are produced again
individually. Each new block is validated; if it has errors, the original
block is kept. If no finding refers to a block, the complete lesson is
produced again; the new version is used only if it has fewer findings and
retains its content. The scores are recorded in the technical report.

### Fact check

The fact check is executed only if material has been uploaded and an
embedder is configured. The lesson text is divided into sections at sentence
boundaries; numbers in charts and tables are included. For each section the
most relevant passages of the material are retrieved. The strong model
classifies statements as not evidenced or contradictory; general knowledge of
the subject is not classified. A contradiction leads to a revision of the
lesson under the same conditions as in the critique. The results are written
to `04-fact-check.md`.

### Redundancy check

The strong model receives an overview of the unit (lesson, subheadings,
concepts) and identifies concepts that are derived again in a later lesson.
Application, integration and final lessons that take up concepts without
deriving them again are not counted. The findings state where the complete
explanation is located and which passages could be replaced by a reference.
They are recorded in the check report; the text is not changed.

## Final validation

| Step | Processing |
|---|---|
| 1 Normalisation | repeated, since the critique and the fact check may introduce Markdown |
| 2 Validation | structure, coverage and patterns across the unit (only one interaction type, no diagram in the unit, systematically longer correct answers, concepts without a glossary entry) |
| 3 Degradation | displaying blocks that still contain errors are replaced by their description as text; interactions and structural errors are excluded from this |
| 4 Assembly | the unit receives the state `final` if no errors remain; otherwise it is assembled with the state `draft` |
