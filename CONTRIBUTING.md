# Contributing

Thank you for helping. Bug reports, fixes, new languages and improvements
to prompts and documentation are welcome.

## Before you start

For anything larger than a small fix, please open an issue first and
describe what you want to change. That avoids work on something that does
not fit.

## Setting up

See [docs/development.md](docs/development.md#setting-up).

## Checks

All of these must pass before a pull request is merged; CI runs them:

```bash
bash run_tests.sh                  # tests, without network or LLM
python scripts/check_static.py     # pyflakes: undefined names, duplicate keys
node scripts/lint_js.mjs           # ESLint on the shell and the Node probes
```

A bug fix comes with a test that fails without it.

## Conventions

- **Code, comments, docstrings, log messages and documentation are in
  English.** Comments explain why, not what.
- **Interface texts** are written in English in the code with `tr(…)`,
  `Msg(…)` or `N_(…)` and translated in `src/i18n/de.py`;
  `tests/test_i18n_catalog.py` lists what is missing. See
  [adding an interface language](docs/development.md#adding-an-interface-language).
- **Texts in delivered units** go into `src/unit/i18n.py`, in all five
  languages.
- **Prompts**: field names and protocol values in prompts must match what
  the parser reads. Run `scripts/benchmark.py` against real models after a
  prompt change and mention the result in the pull request.
- **The unit format** is public: changes need the schema, the validator,
  the shell and the documentation together (see
  [changing the unit format](docs/development.md#changing-the-unit-format)).
- **New settings** go into `.env.example` and `docs/configuration.md`;
  `tests/test_env_documented.py` checks the first.
- No secrets, internal host names or real learner data in code, tests or
  examples.

## Pull requests

Keep a pull request to one concern. Describe what changes for users and
for operators, and add an entry under "Unreleased" in
[CHANGELOG.md](CHANGELOG.md) for anything they would notice.

By contributing you agree that your contribution is licensed under the
[MIT License](LICENSE).

## Conduct

Please follow the [code of conduct](CODE_OF_CONDUCT.md).
