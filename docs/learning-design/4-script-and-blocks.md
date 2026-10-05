# Phase 4: script and blocks

Each chapter is produced in two runs. Run A produces the chapter script, run
B the lessons as sequences of blocks. Run A of the next chapter is executed
in parallel with run B of the current chapter. The runs B are executed in
the order of the chapters.

Implementation: `src/pipeline/learning_pipeline.py`. Prompts: `cross_prompt`,
`script_prompt`, `chapter_finalize_prompt`, `transform_prompt`.

## Run A: chapter script

### Cross-context

The fast model produces a working basis for the chapter from the summaries
of the previous chapters and the fixed terminology. It contains the binding
terms with their meaning, the concepts already explained (to be referenced)
and notation conventions. Term candidates that have not yet been checked are
excluded.

### Script sections

One section is produced per concept; the sections are generated in parallel.
Sections for V concepts are produced by the strong model, sections for K and
D concepts by the fast model. The input of a section consists of:

- the learner profile, including the prior knowledge as entered;
- the concept with its class and the lesson plan;
- the instruction from the teaching script;
- the cross-context;
- evidence from the material, if available.

The prompt contains the following rules:

| Rule | Content |
|---|---|
| prior knowledge | new content is related to the stated prior knowledge; known content is not explained again |
| level | technical terms outside the concept inventory are explained briefly on first use or omitted; symbols and quantities are introduced only where required, with an everyday equivalent |
| misconception | at least one typical misconception is addressed |
| interactions | the section contains the complete content of the planned interactions (questions, distractors, feedback, simulation logic, chart data) |
| terminology | only terms from the binding terminology, the concept inventory or the material; paraphrase where no established term exists |
| format | HTML; no Markdown, no LaTeX |

Text length by depth profile:

| Profile | Text length |
|---|---|
| detailed | on average across the chapter 800–1500 words per V concept, 250–500 per K concept, 80–200 per D concept; an `<h3>` subheading every three to five paragraphs |
| compact | short texts; key statement first; one example per concept |

Each section is checked by the fast model against criteria for prose. With a
score below 3 the section is produced once more, with the feedback as input.
The criteria for the finished lesson are applied in phase 5.

### Assembly

The strong model assembles the sections into a chapter script in the order of
the lesson plan, adds transitions and unifies the terminology. Explanations
that occur in several sections are reduced to the most detailed version; the
other occurrences are replaced by references. Statements that occur only once
are retained. The script is followed by a glossary section with one line per
newly introduced term (term, short form, definition, lesson).

### Processing after assembly

1. Markdown and LaTeX remnants are converted to HTML.
2. The terminology check examines terms that the text defines; terms not
   covered by the inventory, the material or a check are replaced (see
   [architecture](../architecture.md#terminology-control)).
3. A short summary of the chapter is created as input for the next chapter.

The script is written to `03-script-c<n>.html`.

## Run B: lessons

### Transformation

One task is executed per lesson, on the fast model with reasoning switched
off. The input consists of:

- the lesson plan including the media plan;
- the chapter script in full length; above `MAX_SCRIPT_CONTEXT` (default
  60,000 characters) a structural summary marked as such is used instead;
- for a synthesis lesson, its instruction from the teaching script;
- the block contract for the block types contained in the media plan.

The prompt contains the following rules:

| Rule | Content |
|---|---|
| media plan | all planned displays and interactions are produced |
| script text | the text is taken over completely in text blocks with `<h3>` subheadings; passages represented by a planned display are not repeated as text |
| content | no additional facts |
| self-check | at least one self-check with feedback for every option |

### Processing of the result

| Step | Processing |
|---|---|
| 1 Parsing | five parsing strategies; for a truncated answer, all blocks up to the last complete one are kept; German field names are mapped to the format |
| 2 Names | unknown block types are assigned by their content; alternative field names are mapped (`beschriftung` → `description`) |
| 3 Normalisation | Markdown to HTML; simple formulas to HTML, two-dimensional formulas to MathML; Mermaid labels quoted where required; HTML reduced to permitted tags |
| 4 Concepts | concept assignments are taken from the detail plan |
| 5 Validation | required fields and field contracts, format remnants, trial run of each simulator in Node.js, Mermaid syntax, characters of other scripts (an error at this stage) |
| 6 Repair | blocks referred to by findings are produced again individually; without such references, the complete lesson is produced again and the new version is used only if it has fewer findings and retains its content; certain warnings are included (a cloze gap answerable from the surrounding text, quiz options without feedback, controls without labels) |
| 7 Truncation | missing blocks are requested separately; if this fails, the lesson is produced again with a larger output budget |
| 8 Storage | each completed lesson is saved immediately |

The enrichment and the application part follow after the lessons of the
chapter; see [phase 5](5-enrichment-and-critique.md).
