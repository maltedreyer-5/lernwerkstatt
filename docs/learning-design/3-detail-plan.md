# Phase 3: detail plan

The detail plan divides a chapter into lessons and specifies for each lesson
the learning objectives, the content, the planned blocks (media plan) and the
check criteria.

Implementation: `src/pipeline/learning_pipeline.py` (detail plan phase and
`_detail_plan_findings`). Prompt: `detail_plan_prompt`.

## Input

- the chapter with its concepts and their classes;
- from the learner profile: context, target level, prior knowledge and known
  concepts;
- the depth profile;
- a short version of the diagram catalogue.

## Output

The strong model creates one plan per chapter; the chapters are processed in
parallel. Each plan is written to `02-detail-plan-c<n>.json`. The following
example uses the actual field names; its content is illustrative.

```json
{
  "lessons": [
    {
      "id": "desired-state",
      "title": "Desired and actual state",
      "concepts": ["k1"],
      "learning_objectives": ["Can explain how Kubernetes corrects deviations from the desired state"],
      "content_points": ["Reconciliation loop: observe, compare, act", "Behaviour after deleting a pod"],
      "media_plan": [
        "prediction (behaviour after deleting a pod)",
        "text with h3 structure",
        "diagram:stateDiagram-v2 (states of a pod and transitions)",
        "text",
        "quiz (misconception: kubectl starts containers directly)",
        "note:key_point"
      ],
      "display_rationale": "state changes with returns to earlier states",
      "check_criteria": [
        "addresses the misconception that a command starts containers directly",
        "the prediction precedes the explanation",
        "the diagram shows the return after a deviation"
      ]
    }
  ],
  "application_part": [
    {"type": "prediction", "concepts": ["k1"], "short_description": "Behaviour with replicas: 3 after a node failure"},
    {"type": "error_analysis", "concepts": ["k2"], "short_description": "Imperative script that creates duplicates when run again"}
  ],
  "case_task": {"concepts": ["k1", "k2"], "short_description": "Conversion of a Docker Compose setup into declarative manifests"}
}
```

| Field | Content |
|---|---|
| `concepts` | concepts covered by the lesson; used by the program as the authoritative assignment |
| `learning_objectives` | learning objectives in the form "Can …" |
| `content_points` | required content |
| `media_plan` | planned blocks in reading order |
| `display_rationale` | reason for the chosen display, or for its absence in a lesson with a V concept |
| `check_criteria` | verifiable criteria used in the critique of the lesson |
| `application_part`, `case_task` | tasks of the application part of the chapter |

## Rules for the media plan

The prompt specifies a two-step selection. First, the form of display is
determined by the type of content; second, the simplest block of that form is
chosen.

| Type of content | Form of display |
|---|---|
| process, dependency, decision path, responsibilities | diagram; the type is chosen from the diagram catalogue |
| comparison of three or more features or cases | table |
| quantities, shares, developments, orders of magnitude | chart |
| parameter dependency intended for exploration | chart with parameters; a simulator if a chart is insufficient |
| set of terms to be memorised | flashcards or accordion |
| mathematical relation | formula |

Interactions are assigned according to the learning purpose:

| Learning purpose | Interaction |
|---|---|
| recall of terms | flashcards |
| distinction between similar concepts | matching |
| reconstruction of a sequence or wording | cloze |
| correction of a misconception | quiz |
| formation of an expectation before an explanation | prediction |
| exploration of a parameter dependency | simulator |

Further rules of the prompt:

- interactions are distributed within the lesson, at least about one per 400
  words of reading text;
- the unit contains at least five different forms of display and interaction;
- each lesson with a V concept contains a non-textual display or a reason for
  its absence;
- a display contains information that the text does not present in the same
  way;
- each V concept appears in at least one task of the application part.

The diagram catalogue (`src/unit/diagram_types.py`) describes twelve Mermaid
diagram types with their didactic use, typical misuse and variable elements.
The detail plan prompt receives the didactic description; the syntax is
provided in phase 4.

## Density check

After the plan has been created, the program checks it without a model.

| Check | Rule |
|---|---|
| interactions per lesson | at least two in the detailed profile, at least one in the compact profile |
| display in lessons with a V concept | a non-textual display or a `display_rationale` |
| variety within the chapter | at least three different interaction forms if the chapter has at least two lessons and at least three interactions |

If findings occur, the model creates the plan again with the findings as
input. The program compares both versions by the same criteria and keeps the
one with fewer findings. Remaining findings are logged.

If more than 30 % of the media plan entries cannot be assigned to a block
type, the check is skipped. Entries in other languages are assigned through
the same translation table that is used for the block contract.

If no plan can be created for a chapter, an emergency plan with one lesson
per concept is used.

## Use in later phases

| Phase | Use |
|---|---|
| 4, script | the lesson plan is part of each script section's input; the sections contain the content of the planned interactions |
| 4, blocks | the media plan determines the blocks of the lesson; the block contract passed to the model is limited to the planned block types |
| 4, coverage | concept assignments are taken from the plan; a concept without a lesson is assigned to the first lesson of its chapter |
| 5, critique | the check criteria are part of the critique criteria |
| 5, application part | `application_part` and `case_task` determine the tasks |
