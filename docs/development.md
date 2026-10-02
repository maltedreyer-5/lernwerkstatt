# Development

## Setting up

```bash
python3.12 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
npm ci
node scripts/copy_vendor.mjs
python -m playwright install chromium     # for the browser tests
```

`requirements-dev.txt` adds pytest, pyflakes, jsonschema and Playwright to
the runtime dependencies.

## Tests

```bash
bash run_tests.sh                 # every test file, one line each
python -m pytest tests -q         # the same tests through pytest
python tests/test_e2e_mock.py     # a single file
```

The tests need no LLM endpoint and no network. `tests/mock_llm.py` answers
every kind of prompt deterministically, so the whole pipeline runs end to
end, including the DAG executor, quality checks, the repair loop, critic
and fact-check revisions, resumption and rework.

`run_tests.sh` uses `python3` unless `PYTHON` is set (for instance
`PYTHON=.venv/bin/python bash run_tests.sh`). Tests that need an optional
package or tool (Gradio, openai, jsonschema, Playwright with Chromium,
Node.js) skip the parts they cannot run, print a line starting with
`  ---`, and the runner counts those. A skipped part is never reported as
passed.

What the suite covers, roughly:

| Area | Files |
|---|---|
| unit layer: validation, assembly, schema | `test_unit_layer`, `test_schema`, `test_field_coverage` |
| normalisation, terminology, diagram types | `test_format_and_terminology`, `test_sankey_translit` |
| cases found in real runs | `test_regression_findings`, `test_integration_findings` |
| the whole chain up to the delivered file | `test_full_chain`, `test_renderer_runs`, `test_localisation`, `test_shell_browser`, `test_shell_consistency`, `test_slug_parity` |
| pipeline end to end with the mock LLM | `test_e2e_mock`, `test_e2e_robust`, `test_unit_language`, `test_degradation_paths` |
| the wizard in a browser, against an OpenAI-compatible test server | `test_wizard_e2e` |
| jobs, state, queue, pickup codes, uploads | `test_jobs_and_state`, `test_pickup_code`, `test_upload_cleanup` |
| sandboxes | `test_sim_sandbox` |
| LLM, embedder and reranker clients, parsing | `test_llm_http`, `test_inventory_http`, `test_llm_json_thinking`, `test_legacy_keys`, `test_template_placeholders` |
| interface | `test_ui_build`, `test_ui_structure`, `test_i18n_catalog` |
| configuration | `test_configuration`, `test_interfaces`, `test_env_documented` |

`test_wizard_e2e` is the only test that takes the path a user takes: it
starts the application against `tests/mock_openai_server.py` (chat,
embeddings and a reranker, answered by the mock LLM) and drives the wizard
in Chromium from the first step to the delivered unit, then loads and
deletes the job with its pickup code. The server is also useful on its own
for trying the interface without a model:
`python tests/mock_openai_server.py 8899`, then point `LLM1_BASE_URL` (and
`EMBEDDER_BASE_URL`) at `http://127.0.0.1:8899/v1` and
`RERANKER_BASE_URL` at `http://127.0.0.1:8899/rerank`.

`test_ui_build` builds the Gradio interface against a mock, so it also runs
without Gradio installed; it checks that every event handler exists, is
callable, takes as many inputs as it is wired with, and returns as many
values as it has outputs.

## Static check

```bash
python scripts/check_static.py
```

Runs pyflakes over `src`, `scripts`, `tests` and `app.py` and fails on
every finding that breaks at run time: undefined names, duplicate dictionary
keys (which in the language catalogs means a translation silently replaced
by another), unused and shadowed imports.

## JavaScript lint and third-party notices

```bash
node scripts/lint_js.mjs              # ESLint on the shell and the Node scripts
node scripts/third_party_notices.mjs  # regenerate THIRD_PARTY_NOTICES.md
```

The lint applies only rules that catch errors (undefined and shadowed
names, duplicate keys, unreachable code), because the shell's script runs
inside every generated unit, where a mistake breaks silently. Regenerate the
notices after any change to `package-lock.json`; CI fails if the file is out
of date.

## Measuring with real models

```bash
python scripts/benchmark.py          # against the models in .env
python scripts/benchmark.py --mock   # dry run of the harness
```

Five reference concepts, each through script → transformation → validation
→ at most one repair. Exit code 0 means every case is free of errors. Run it
after changing prompts, the block contract, or models.

`python scripts/check_services.py` reports what each configured endpoint
answers, before a run fails for an unrelated reason.

## Prompts

All prompts are in `src/prompts/learning.py` (and the inventory prompt in
`src/prompts/inventorize.py`). They are written in English; the language of
the generated content is set by a language rule appended to every
generation prompt.

When changing a prompt:

- Field names in JSON examples must be the ones the parser reads; the unit
  format is described in [unit-format.md](unit-format.md).
- Protocol values (field names, block type names, class letters, section
  markers such as `=== GLOSSAR ===`) are never translated, also not by the
  language rule.
- The mock LLM recognises prompts by fixed phrases. If a test reports an
  unexpected prompt, the phrase in `tests/mock_llm.py` has to follow.
- Run the benchmark against real models before release. The tests show
  that the chain works; only the benchmark shows that models understand the
  prompt.

## Adding an interface language

Interface texts are written in English in the code and translated through
a catalog per language.

1. Copy `src/i18n/de.py` to `src/i18n/<code>.py` and translate the values.
   Keep the keys (the English texts) and every `{placeholder}` unchanged.
2. Add the code to `LANGUAGES` and its name to `LANGUAGE_NAMES` in
   `src/i18n/__init__.py`.
3. Run `python tests/test_i18n_catalog.py`. It lists every text used in the
   code that is missing from a catalog, every placeholder that differs, and
   every entry no longer used.

In the code, use `tr("English text {name}", lang, name=value)` for texts
shown at once, `Msg("English text {name}", {"name": value})` for texts
produced in the background and shown later, and `N_("…")` for labels kept in
tables. Validator messages take the template and its parameters directly:
`b.W(path, "English text {name}", name=value)`.

## Adding a language for generated units

The controls of a delivered unit come from `src/unit/i18n.py`, which has
its own table because units support more languages than the interface.

1. Add the code to `LANGUAGES` and a `(code, name)` pair to `CHOICES`.
2. Add a translation for every key in `TEXTS`.
3. Add the language to `LANGUAGE_NAMES` in `src/prompts/learning.py`, so the
   language rule names it.
4. Run `python tests/test_localisation.py`: it assembles a unit per language
   and checks that no German control text remains and the script still runs.

## Changing the unit format

The schema (`src/unit/schema/unit.schema.json`), the validator, the
normalisation field lists, the shell's renderers and the block contract in
the prompts all describe the same format. `test_schema` checks the example
and a generated unit against the schema, `test_field_coverage` that every
field the shell renders is normalised, and `test_shell_consistency` that the
shell's script and markup use the same class names, IDs and data
attributes. Increase `format_version` (and `UNIT_FORMAT_VERSION` in
`learning_pipeline.py`) for changes that older readers cannot handle.
