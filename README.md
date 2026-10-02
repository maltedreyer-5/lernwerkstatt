# LernWerkstatt

LernWerkstatt generates interactive learning units with a large language
model. You describe what a learner already knows and what they want to
learn, optionally upload material, and get a single, self-contained HTML
file: lessons with running text, diagrams, charts, formulas, simulators and
self-checks, a glossary, an application part per chapter and a final test.
The file works offline and needs no server.

It is built for universities and similar institutions that want to produce
topic-specific learning material on their own infrastructure, with their
own models.

[Deutsche Kurzfassung](README.de.md)

## How it works

The scope of a unit is **derived** from the gap between prior knowledge and
goal, not set by the user. A gap analysis builds a concept inventory and
gives each concept a treatment class: full, compact, delta, or glossary
only. The classes add up to the learning time, which decides the format,
from a short impulse to a book. You review and edit the inventory at a
checkpoint before anything is produced.

Production then runs chapter by chapter on the server:

- a teaching script fixes where each concept is introduced, so sections
  neither repeat each other nor anticipate later ones;
- scripts are turned into blocks, then normalised, validated and repaired;
- a critic, a redundancy pass and, with uploaded material, a fact check go
  over the result;
- displays that cannot be repaired are replaced by their description
  instead of failing the unit.

Details: [architecture](docs/architecture.md).

## Typical uses

- **An introduction to a new field** that answers the learner's actual
  question instead of reproducing a curriculum.
- **Teaching material from existing documents**: a standard, a book
  chapter, lecture slides. Terminology comes from the material, statements
  are checked against it.
- **Self-study for an exam**, with flashcards for terms, matching for what
  is easily confused, and a final test; the file also works without a
  network.
- **Quantitative relationships** to explore with simulators and interactive
  charts instead of reading about them.
- **The same material in several languages.**

## Features

- Five-step wizard in English and German. Production continues when the
  window is closed; a job can be resumed or deleted with its pickup code.
- Units in German, English, French, Spanish or Italian.
- 17 block types, from text and tables to quizzes, cloze texts,
  flashcards, Chart.js and Vega-Lite charts, Mermaid diagrams, formulas
  (HTML and MathML) and simulators that run in a sandbox.
- Two model roles (strong and fast) on any OpenAI-compatible endpoint, with
  reasoning control for Qwen3, Kimi K2, GLM and Gemma 4.
- Optional embedder and reranker: uploaded material becomes evidence for the
  authors, a coverage report and a fact check.
- Terminology control against coined terms.
- A check report and a technical report (usage and content figures) per
  unit, and a Word handout of the scripts.
- Accessible output: native, keyboard-operable controls, ARIA labelling,
  required alternative texts for every graphic, formulas as MathML that
  screen readers can read.

## Quick start

Requirements: Docker and an OpenAI-compatible LLM endpoint.

```bash
git clone https://github.com/maltedreyer-5/lernwerkstatt.git
cd lernwerkstatt
cp .env.example .env      # set LLM1_BASE_URL, LLM1_API_KEY, LLM1_MODEL
docker compose -f deploy/docker-compose.example.yml up -d --build
```

Open <http://127.0.0.1:7860/lernwerkstatt/>.

The interface has no user accounts. Before you make it reachable from a
network, put it behind a reverse proxy with access control.

## Documentation

| | |
|---|---|
| [Installation](docs/installation.md) | Docker, reverse proxy, local installation, updates |
| [Configuration](docs/configuration.md) | every setting, models and reasoning, embedder and reranker |
| [Operations](docs/operations.md) | security model, stored data, deleting jobs, maintenance |
| [Architecture](docs/architecture.md) | pipeline, checks and repairs, modules |
| [Unit format](docs/unit-format.md) | `unit.json` and the block types |
| [Didactics criteria](docs/didactics-criteria.md) | the criteria and where each is enforced |
| [Development](docs/development.md) | tests, prompts, adding languages |

## Status and limits

- The pipeline checks everything that can be checked deterministically:
  format, structure, references, concept coverage, simulator behaviour,
  diagram syntax, language mixing. It does **not** prove that the content is
  correct. Have units reviewed before they are used for teaching; every unit
  says that it was generated with AI assistance.
- The quality of the units depends on the models. `scripts/benchmark.py`
  measures how well your models follow the format; run it when you change
  models.
- The test suite runs without a model, against a deterministic mock.
- The interface is meant for a trusted group of users behind access control
  ([security model](docs/operations.md#security-model)).

## Contributing and security

See [CONTRIBUTING.md](CONTRIBUTING.md). Please report vulnerabilities as
described in [SECURITY.md](SECURITY.md), not in public issues.

## License

MIT, see [LICENSE](LICENSE). Generated units embed Chart.js and Mermaid
(MIT) and Vega, Vega-Lite and Vega-Embed (BSD-3-Clause); their license
notices are kept in every unit. [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)
lists every embedded library with the packages it bundles.
