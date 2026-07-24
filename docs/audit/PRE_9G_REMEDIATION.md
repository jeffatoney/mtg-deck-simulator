# Pre-9G remediation audit

This audit resolves PR #29 review findings without relying on unverifiable baseline counts. Any earlier pre-change pytest output was an unsaved preliminary local run and is not repository evidence. The production pilot command `uv run mtg-sim pilot --config configs/pilot.toml` remains locked and was not run.

## Review findings resolved

1. P1: Psychosis Crawler now uses hand-size-derived power and toughness for state-based actions and combat-relevant value access.
2. P2: Cascade Bluffs filter actions now record the selected {U/R} input separately from the selected UU/UR/RR output.
3. P2: Executable adapter evidence now validates complete collected pytest node IDs, including parametrized case identifiers, and records verified node IDs in the coverage report.
4. P2: Unverifiable exact baseline pass/fail/timing claims were removed rather than reconstructed.

## Regression test node IDs

- `tests/test_phase9f4_creatures_combos_coverage.py::test_psychosis_crawler_dynamic_hand_size_characteristics_and_life_loss`
- `tests/test_phase9f1_executable_adapters.py::test_cascade_bluffs_filter_variants_record_input_and_output`
- `tests/test_phase9f1_executable_adapters.py::test_cascade_bluffs_replay_preserves_exact_filter_choice`
- `tests/test_phase9f1_executable_adapters.py::test_executable_coverage_requires_complete_collected_pytest_nodes`

## Current verified results

Commands were run from the PR branch working tree and logs were saved under `artifacts/validation/phase9f5-final/`.

- `uv sync --frozen --all-extras`: passed; checked 34 packages.
- `uv run ruff format --check .`: passed; 41 files already formatted.
- `uv run ruff check .`: passed; all checks passed.
- `uv run mypy src`: passed; no issues found in 19 source files.
- `uv run pytest -q -ra`: passed; 278 passed.
- `uv run python scripts/check_manifest.py`: passed; 31 frozen files and 16 required paths.
- `uv run mtg-sim validate-sources`: passed.
- `uv run mtg-sim validate-coverage`: passed; 98 library cards and 2 commanders covered, 0 blocked, 0 missing, 0 silent fallbacks.
- `uv run mtg-sim validate-executable-coverage`: passed; 80 expected unique cards, 80 executable, 0 blocked.
- `uv run mtg-sim validate-prepolicy-readiness`: passed; sources, coverage, and executable evidence valid.
- `uv run mtg-sim verify-rules --output artifacts/rules/phase9f5-final/`: passed; report path printed in validation log.
- `uv run mtg-sim pilot --config configs/pilot.toml --dry-run`: passed; dry-run manifest path printed in validation log.
- `uv run mtg-sim pilot --config configs/real-executor-smoke.toml --smoke`: passed; smoke artifacts path printed in validation log.

## Final status

Final commit SHA is the PR branch tip containing this document and is reported in the PR/final response after commit creation. Remaining unresolved P1/P2 findings: none.
