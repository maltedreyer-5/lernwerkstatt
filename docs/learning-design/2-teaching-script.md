# Phase 2: teaching script

The teaching script assigns each concept of the inventory a place of
introduction and its prerequisites, and describes the arc of the unit. The
later phases derive instructions for individual sections and lessons from it.

Implementation: `src/pipeline/teaching_script.py`. Prompt:
`teaching_script_prompt`.

## Input

- the result of the gap analysis (concepts, classes, chapters);
- from the learner profile: context, target level and prior knowledge.

## Procedure

The strong model produces three results.

1. Guiding question: the question the unit answers, in one sentence.
2. Arc: one sentence per chapter that states what the learner can do after
   the chapter.
3. Concept graph with the following fields for each concept:

| Field | Content |
|---|---|
| `introduction` | the lesson in which the concept is introduced; exactly one per concept |
| `requires` | direct prerequisites |
| `resumption` | lessons in which the concept is applied without being explained again |
| `contribution` | one sentence on the role of the concept in the arc |

The prompt requires that no concept depends on a concept that is introduced
in a later lesson.

## Validation

The program checks the concept graph for:

- concepts of the inventory that are missing from the graph;
- prerequisites whose declared place of introduction lies after the place of
  introduction of the dependent concept;
- cycles in the dependencies.

Findings are recorded as warnings. Production continues in all cases.

## Derived instructions

### Section instructions

For each script section in phase 4, the program generates an instruction from
the graph. It lists the concepts introduced before (transitive closure of the
dependencies), the concept to be introduced, and the concepts introduced
later, which the section is not to anticipate. Sections that only resume a
concept receive an instruction to apply it without explaining it again.

### Lesson instructions

Phase 4 creates script sections per concept and lessons per lesson of the
detail plan. A lesson without a concept of its own (synthesis lesson) receives
an instruction to relate the previously introduced concepts to each other.

### Order and graph

The program computes a topological order of the concepts. Concepts in cycles
are placed at the end. The graph is also rendered as a Mermaid diagram.

## Checkpoint

The guiding question, the arc and a table with the columns concept,
introduced in and builds on are shown together with the gap analysis. Changes
in the table are used for all derived instructions. The teaching script is
written to `01b-teaching-script.md`.

## Material coverage

If material has been uploaded and an embedder is configured, the program
determines for each concept whether the material contains corresponding
passages (`src/pipeline/material_coverage.py`). The procedure has three steps:

1. Lexical search for the technical terms of the concept name in the full
   text and in the keywords of the material sections.
2. Semantic search with several queries: concept name, rationale and
   learning objectives. The results are merged.
3. Assessment of the hits by the reranker. A concept counts as evidenced if a
   hit exceeds a fixed relevance threshold. Without a reranker, assignments
   are marked as unchecked.

The result lists, per concept, the evidence found, and lists material
sections that are not assigned to any concept. The evidence is passed to the
script sections of the respective concept. The report is written to
`01c-material-coverage.md`.
