# Learning design

This section describes how LernWerkstatt plans a learning unit, from the gap
analysis to the critique of the finished lessons. For the technical structure
(modules, task executor, repair layers) see [architecture.md](../architecture.md);
for the didactic criteria see [didactics-criteria.md](../didactics-criteria.md).

## Phases

The planning consists of five phases. Each phase receives the results of the
preceding one as input.

| Phase | Result | Document |
|---|---|---|
| 1 Gap analysis | concept inventory with treatment classes, chapters, learning time, format | [1-gap-analysis.md](1-gap-analysis.md) |
| 2 Teaching script | place of introduction and prerequisites of each concept, guiding question, arc | [2-teaching-script.md](2-teaching-script.md) |
| 3 Detail plan | lessons per chapter with learning objectives, media plan and check criteria | [3-detail-plan.md](3-detail-plan.md) |
| 4 Script and blocks | chapter script; lessons as sequences of blocks | [4-script-and-blocks.md](4-script-and-blocks.md) |
| 5 Enrichment and critique | additional blocks, application part, final test, review results | [5-enrichment-and-critique.md](5-enrichment-and-critique.md) |

## Division of work

Decisions about content are made by a language model. Each such decision is
requested with stated rules and in a fixed JSON structure.

Computations and checks are carried out by the program: learning time,
format, depth profile, the order of concepts, the density of a plan and the
structure of each block. If a check produces findings, the model receives the
findings and produces the result once more. The program keeps the version
with fewer findings.

Teaching staff review the results of phases 1 and 2 at a checkpoint before
production starts. They can change treatment classes, remove concepts and
change places of introduction. After production, individual chapters can be
produced again with an instruction.

## Model roles

Two models are configured (see
[configuration](../configuration.md#the-two-models)). The tasks are assigned
as follows:

| Strong model | Fast model |
|---|---|
| gap analysis | learner profile |
| teaching script | cross-context |
| detail plans | script sections of K and D concepts |
| script sections of V concepts | transformation into blocks |
| chapter assembly | chapter summaries |
| application part, final test | quality checks of individual tasks |
| enrichment, critique, block patches | |
| fact check, redundancy check | |

## Files in the job folder

| File | Phase |
|---|---|
| `00-learner-profile.md` | input to phase 1 |
| `01-outline-plan.md` | 1 |
| `01b-teaching-script.md` | 2 |
| `01c-material-coverage.md` | after 2, if material and an embedder are available |
| `02-detail-plan-c<n>.json` | 3, one file per chapter |
| `03-script-c<n>.html` | 4, one file per chapter |
| `04-fact-check.md` | 5, if material and an embedder are available |
| `99-technical-report.md` | usage and content figures, including the critique scores |

## Prompts

The prompts are defined in `src/prompts/learning.py`: `learner_profile_prompt`,
`gap_prompt`, `teaching_script_prompt`, `detail_plan_prompt`, `cross_prompt`,
`script_prompt`, `chapter_finalize_prompt`, `transform_prompt`,
`enrichment_prompt`, `tasks_prompt`, `final_test_prompt`, `critic_prompt`,
`block_patch_prompt`, `fact_check_prompt` and `redundancy_prompt`. Each prompt
that generates content ends with a rule that sets the language of the unit.
