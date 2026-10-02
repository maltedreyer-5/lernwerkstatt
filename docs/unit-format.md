# Unit format

A learning unit is one JSON document, `content/unit.json` in the job folder.
It is the editable source: the delivered HTML file is assembled from it, and
it can be edited by hand and assembled again:

```bash
python -m src.unit.validator path/to/unit.json      # exit 0 = no errors
python -m src.unit.assembler path/to/unit.json out/  # writes out/<id>.html
```

The formal definition is the JSON Schema in
`src/unit/schema/unit.schema.json`. The validator (`src/unit/validator.py`)
applies stricter rules on top of it: references between lessons and
modules, didactic minimums, simulator trial runs and Mermaid syntax. An
example is in `examples/example-unit.json`.

## Top level

| Field | Type | Meaning |
|---|---|---|
| `format_version` | integer | version of this format; currently `1`. Absent means 1. |
| `id` * | string | slug: lower-case letters, digits, hyphens |
| `title` * | string | |
| `description` | string | one or two sentences |
| `language` | string | `de`, `en`, `fr`, `es` or `it`; decides the language of the unit's controls |
| `duration_minutes` | integer | estimated learning time |
| `depth_profile` | `compact` \| `detailed` | how much developing prose a lesson carries |
| `state` | `draft` \| `final` | `final` only after the final gate passed |
| `concepts` | array | the concept inventory: `id`, `name`, `concept_class` (`V` `K` `D` `R`) |
| `learning_objectives` | array of strings | |
| `prerequisites` | array of strings | |
| `provenance` | object | `models`, `sources`, `note`; shown at the end of the unit |
| `lessons` * | array | see below |
| `modules` | array | chapters: `id`, `title`, `lessons` (lesson IDs), `exercises` (blocks) |
| `glossary` | array | `term`, `definition`, `short` (the hover text), `lesson` |
| `final_test` | object | `title`, `questions` (as in a quiz block) |

\* required

A lesson belongs to one module: in several modules it is an error; in none
it is a warning, and the lesson appears under "More lessons". A module's
`exercises` are its application part, shown after its lessons.

## Lessons

| Field | Type | Meaning |
|---|---|---|
| `id` * | string | unique; `start`, `test`, `glossary` and `ex-*` are reserved |
| `title` * | string | |
| `learning_objectives` | array of strings | |
| `concepts` | array of concept IDs | which concepts the lesson covers |
| `blocks` * | array | the content, in reading order |

## Blocks

Every block has a `type`. Fields marked \* are required.

HTML fields allow `p strong em ul ol li a code br h3 h4 sub sup` and MathML;
everything else is removed. Text fields (titles, quiz questions and options,
table cells, flashcards, descriptions) are plain text and are displayed
escaped.

### Levels

Block types are grouped into levels. The step rule: use the lowest level
that is sufficient.

| Level | Types | What runs |
|---|---|---|
| 1 | `text` `note` `table` `accordion` `code` `quiz` `cloze` `matching` `flashcards` `formula` and the application-part types | nothing; data rendered by the shell |
| 2 | `chart` `diagram` | declarative specifications rendered by Chart.js, Vega-Lite or Mermaid |
| 3 | `simulator` | a pure function written by the model, run in a sandbox |
| 4 | `widget` | a complete HTML document in a sandboxed iframe; always reported, to be justified in the detail plan |

### Text and structure

| Type | Fields |
|---|---|
| `text` | `html`* — running text; use `<h3>`/`<h4>` to structure it, they become search anchors |
| `note` | `html`*, `variant`: `key_point` \| `info` \| `warning` |
| `table` | `header`* (array), `rows`* (arrays with as many cells as `header`), `caption` |
| `accordion` | `items`*: `[{title, html}]` — optional material |
| `code` | `content`*, `language` |
| `formula` | `latex`*, `description`* (the formula in words), `display`: `inline` \| `block`. `html` is set at build time. |

### Self-checks

| Type | Fields |
|---|---|
| `quiz` | `questions`*: `[{question, multiple, options: [{text, correct, feedback}]}]`. With `multiple: false` exactly one option is correct. Every option needs feedback. |
| `cloze` | `html`* with placeholders `{{1}}`, `{{2}}` …; `gaps`*: `{"1": {"answers": [...], "note": "…"}}`. The solution must not appear in the visible text of the same block. |
| `matching` | `pairs`*: `[{left, right}]` with unique `left` values; `task`. Several pairs may share a `right` value (categorisation). |
| `flashcards` | `cards`*: `[{front, back}]` |

### Displays

| Type | Fields |
|---|---|
| `chart` | `engine`*: `chartjs` \| `vegalite`; `spec`* (a Chart.js configuration or a Vega-Lite specification with inline data); `description`* (key message, more than 20 characters); `height`. Vega-Lite `params` with `bind` make it interactive. |
| `diagram` | `code`* (Mermaid source), `description`*, `engine`: `mermaid`. The type is chosen from a catalogue of twelve Mermaid diagram types by learning purpose (see `src/unit/diagram_types.py`). |
| `simulator` | `code`*: `function model(p){ return {x: [...], series: [{name, values: [...]}]}; }`; `parameters`*: `[{name, label, min, max, step, value, unit}]`; `description`*; `explanation` (an exploration task); `output`: `{kind: line \| bar \| table, x_label, y_label}`; `title` |
| `widget` | `html`* (a complete document starting with `<!DOCTYPE`), `description`*, `title`, `height`. No external resources. |

A simulator function must be pure: no `document`, `window`, `fetch`,
`localStorage` or timers, under 50 ms per run, `values` as long as `x`. With
`kind: line` it returns a curve over a range, not the single value of the
current slider position. The validator runs it with the defaults and with
each slider at its stops, and reports sliders without effect, series that
are zero throughout and non-finite values.

### Application part

These types appear in a module's `exercises` and carry `concepts` (concept
IDs).

| Type | Fields |
|---|---|
| `prediction` | `question`*, `resolution`*, `options` (as in a quiz; without options it asks for a free-text commitment) |
| `task` | `task`*, `sample_solution`*, `title`, `hints` (array). The integrating case task is a `task` whose title starts with "Case task:". |
| `error_analysis` | `material`* (faulty code or text, shown preformatted), `question`*, `sample_solution`*, `title` |

## Model output and older field names

Model answers are parsed into this format. A model that answers with the
German field names of the format's earlier, unpublished version (`titel`,
`lektionen`, `bloecke`, `typ` …) is mapped to the English names on the way
in (`src/llm/legacy_keys.py`). Units written by LernWerkstatt use only the
English names.
