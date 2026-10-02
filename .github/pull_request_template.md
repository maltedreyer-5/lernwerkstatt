## What changes

<!-- For users, for operators, for the unit format. -->

## Checks

- [ ] `bash run_tests.sh`, `python scripts/check_static.py` and
      `node scripts/lint_js.mjs` pass
- [ ] a bug fix comes with a test that fails without it
- [ ] new interface texts are in `src/i18n/de.py`; new unit texts in all
      five languages in `src/unit/i18n.py`
- [ ] new settings are in `.env.example` and `docs/configuration.md`
- [ ] after a prompt change: `scripts/benchmark.py` against real models
      (result below)
- [ ] CHANGELOG.md updated for anything users or operators would notice
