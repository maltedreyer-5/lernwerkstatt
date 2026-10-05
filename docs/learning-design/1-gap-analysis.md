# Phase 1: gap analysis

The gap analysis determines which concepts the unit covers, how extensively
each concept is treated, and from this the learning time and the format of
the unit.

Implementation: `src/pipeline/gap_analysis.py`. Prompts:
`learner_profile_prompt`, `gap_prompt`.

## Input: learner profile

The user describes prior knowledge and learning goal. Optional inputs are a
time budget and uploaded material. The fast model converts this description
into a learner profile with the following fields:

| Field | Content |
|---|---|
| `known_concepts`, `unknown_concepts` | concepts named as known or unknown |
| `target_level` | intended level |
| `context` | target group or setting, one or two sentences |
| `open_questions` | questions required for planning; empty if none |

Open questions are presented to the user in the briefing step and answered
before the gap analysis. The language of the unit is taken from the user's
selection.

If material has been uploaded, the profile additionally contains an excerpt
of each document consisting of its beginning, all headings and its end.

## Procedure

The strong model receives the learner profile and a description of the
available material and produces four results.

1. Kind of gap: `paradigm_shift` (a new mental model is required),
   `extension` (new concepts within a known model) or `version_delta`.
2. Interference risk: `high`, `medium` or `low`, with a rationale. The risk
   describes the extent to which prior knowledge can lead to wrong
   assumptions.
3. Concept inventory: each new concept with an identifier (`k1`, `k2`, …), a
   name, a treatment class and a one-sentence rationale. Concepts named as
   known are not included.
4. Chapters of two to four concepts, ordered by prerequisites, with learning
   objectives.

### Treatment classes

| Class | Treatment | Criterion stated in the prompt |
|---|---|---|
| V | derivation, activation, practice | new concept, high interference, relevant to application |
| K | explanation with an example and a short check | required to reach the learning goal |
| D | difference and pitfall | typical for version differences |
| R | glossary or table entry | reference knowledge |

### Scope rule

The prompt instructs the model to limit the inventory to the stated learning
goal. Concepts that the person wants to understand receive class V. Concepts
required for this receive class K. Further concepts of the subject receive
class D or are omitted. For a question about the purpose of something, the
underlying mechanism is assigned at most class K. As a final step the model
checks whether the learning goal can be reached with the inventory and
whether a smaller inventory would suffice.

## Validation

The program rejects the result if any of the following conditions holds:

- the kind of gap, the interference risk or a class is not a defined value;
- a concept identifier occurs twice, or a concept lacks an identifier or a
  name;
- a chapter refers to an undefined concept;
- a concept of class V, K or D is not assigned to a chapter;
- the inventory or the chapter list is empty.

Values that the model has written in the language of the unit (for example
"hoch" for `high`) are mapped to the defined values beforehand, provided the
mapping is unambiguous.

## Learning time, format and depth profile

Each class has a fixed time value:

| V | K | D | R |
|---|---|---|---|
| 25 min | 8 min | 4 min | 0 min |

The sum of these values is the learning time. Format and depth profile are
determined from it:

| Learning time | Format | Depth profile |
|---|---|---|
| up to 45 min | impulse | compact |
| 46 to 150 min | learning unit | detailed |
| above 150 min | book | detailed |

Example: two V concepts, one K, one D and one R concept result in
2 × 25 + 8 + 4 = 62 minutes, format learning unit, depth profile detailed.

The depth profile determines the text length in phase 4 and the minimum
number of interactions per lesson in phases 3 and 5.

## Time budget

If a time budget has been specified and the learning time exceeds it, the
program generates a proposal for downgrading concepts. It proceeds from the
last concept of the inventory towards the first and first changes V to K,
then K to D, until the budget is reached. If the budget cannot be reached in
this way, the proposal states that concepts have to be removed or the budget
increased. The proposal is not applied automatically.

## Checkpoint

The derivation is displayed in one line, for example: kind paradigm shift,
interference high, 5 concepts (2×V, 1×K, 1×D, 1×R), approx. 62 minutes,
format learning unit, 2 chapters. Below it, the chapter plan and the concept
inventory are shown as an editable table. Classes can be changed and concepts
removed with `DELETE`; learning time, format and depth profile are then
recalculated. If a chapter no longer contains a concept, a notice is
displayed. Production starts after approval.

In the express mode, the questions and the checkpoint are skipped. The
derivation is written to `01-outline-plan.md` in both modes.

## Use in later phases

| Class | Use |
|---|---|
| V | script section by the strong model; the lesson contains a non-textual display or a stated reason for its absence; at least one task in the application part |
| K, D | script section by the fast model, shorter text |
| V, K, D | assignment to at least one lesson is required for the final validation; a concept without a lesson is assigned to the first lesson of its chapter |
| R | no lesson; entry in the glossary |
