#!/usr/bin/env bash
# Check before every deployment. Runs without network access and without
# installed third-party libraries; the UI tests mock whatever is missing.
set -u
failed=0
skipped=0
# Interpreter: PYTHON=... overrides, e.g. a virtual environment. Tests that
# need an optional package (gradio, openai, jsonschema, playwright) skip
# themselves when it is missing and say so in their output.
PY="${PYTHON:-python3}"
for t in test_ui_build test_ui_structure test_configuration test_field_coverage test_localisation test_renderer_runs test_full_chain test_regression_findings test_integration_findings test_llm_json_thinking test_format_and_terminology \
         test_unit_layer test_jobs_and_state test_slug_parity test_e2e_mock test_e2e_robust \
         test_interfaces test_env_documented test_template_placeholders test_legacy_keys test_unit_language test_inventory_http test_degradation_paths test_shell_consistency test_i18n_catalog test_sim_sandbox test_pickup_code test_sankey_translit test_llm_http test_upload_cleanup test_schema test_shell_browser test_wizard_e2e; do
  printf '%-32s ' "$t"
  if out=$(timeout 300 "$PY" "tests/$t.py" 2>&1); then
    # Skipped parts print a line starting with "  ---"; show how many, so a
    # skipped check is never mistaken for a passed one.
    n_skip=$(printf '%s\n' "$out" | grep -c '^  ---' || true)
    if [ "$n_skip" -gt 0 ]; then
      echo "${out##*$'\n'}   [$n_skip part(s) skipped]"
      skipped=$((skipped+n_skip))
    else
      echo "${out##*$'\n'}"
    fi
  else
    echo "FAILED"; echo "$out" | tail -12 | sed 's/^/    /'
    failed=$((failed+1))
  fi
done
[ $skipped -gt 0 ] && echo "── $skipped part(s) skipped: optional package or tool missing, see above ──"
[ $failed -eq 0 ] && echo "── all passed ──" || echo "── $failed test file(s) failed ──"
exit $failed
