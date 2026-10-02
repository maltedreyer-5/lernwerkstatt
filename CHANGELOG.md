# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
uses [Semantic Versioning](https://semver.org/).

For this project, the public interface covered by semantic versioning is:
the unit format (`unit.json`, with its `format_version`), the environment
variables, the command-line options of the scripts in `scripts/`, and the
layout of the work directory. A change that breaks one of them increases
the major version.

## [1.0.0] — unreleased

First public release.

### Added

- Five-step wizard (job, briefing, plan review, production, result) in
  English and German, with a per-session language switch.
- Derivation of scope from the gap between prior knowledge and goal: concept
  inventory with treatment classes, learning time, format and depth profile;
  an editable checkpoint before production; a prioritisation proposal when a
  time budget is exceeded.
- Teaching script that fixes where each concept is introduced; material
  coverage; detail plans with a deterministic density check.
- Production on the server, independent of the browser window; queue for
  parallel jobs; resumption and deletion with a pickup code.
- 17 block types, including Chart.js and Vega-Lite charts, twelve Mermaid
  diagram types, formulas as HTML or MathML, sandboxed simulators and
  widgets, and an application part per chapter.
- Normalisation, validation, block-level repair, degradation of displays
  that cannot be repaired, and a final gate with a marked draft as fallback.
- Critic pass, redundancy pass, and a fact check against uploaded material
  with an optional embedder and reranker.
- Terminology control against coined terms.
- Single-file HTML units in German, English, French, Spanish and Italian,
  with embedded libraries, offline use, search, glossary with hover
  explanations and progress kept in the learner's browser.
- Check report, technical report with usage figures, Word handout.
- Docker image, Compose and nginx examples, start-up diagnosis, service
  check, maintenance script and a benchmark for real models.

[1.0.0]: https://github.com/maltedreyer-5/lernwerkstatt/releases/tag/v1.0.0
