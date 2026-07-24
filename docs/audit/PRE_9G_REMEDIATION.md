# Pre-9G remediation audit

## Evidence policy

The preliminary local runs discussed during PR #28 and the first revision of PR #29 were not saved as immutable artifacts. This document therefore does not preserve exact pass counts, failure counts, or timings from those unsaved runs as repository evidence. Only results reproducible from the final pull-request commit and its GitHub Actions run should be treated as verified.

## Legacy expectation corrected

- `tests/test_phase9f1_executable_adapters.py::test_bounce_filter_and_entry_tapped` exercised Cascade Bluffs through a legacy action that did not record the selected `{U/R}` input. The frozen Oracle text has a separate `{T}: Add {C}.` ability and a filter ability of `{U/R}, {T}: Add {U}{U}, {U}{R}, or {R}{R}.` The validator now normalizes a legacy action only when exactly one input color is available; generated policy actions always record both the selected input and the two-mana output.

## Review remediation summary

- Commander replacement is applied from state-based actions through the existing `move_to_graveyard_or_command_zone` path, preserving commander cast counts and replacement bookkeeping.
- Combat damage returns immediately after the legal state-based-action checkpoint when the game reaches a terminal table win, before Breeches unknown-card records or later combat bookkeeping are appended.
- Executable adapter evidence is checked against the complete set of collected pytest node IDs. A valid file with a nonexistent function or parametrized case now fails closed.
- Commit target validation is part of `validate_action`, so illegal stack and permanent targets are rejected before the card leaves hand or mana is paid.
- Split-spell stack metadata records only the chosen face's type while the spell is on the stack.
- Sentinel Totem and Soul-Guide Lantern resolve as artifact permanents with their modeled activated abilities available.
- Psychosis Crawler's power and toughness are refreshed from the controller's current hand size before state-based actions and after event-recorded hand changes. It is not treated as a static 0/0.
- Cascade Bluffs has a no-input colorless action and explicit filter branches for each payable input (`U` or `R`) and output (`UU`, `UR`, or `RR`). The selected input is paid and recorded.

## Regression evidence

The focused follow-up tests are in:

- `tests/test_phase9f5_followup_review.py::test_psychosis_crawler_uses_dynamic_hand_size_and_zero_toughness_sba`
- `tests/test_phase9f5_followup_review.py::test_cascade_bluffs_generates_explicit_input_output_branches`
- `tests/test_phase9f5_followup_review.py::test_cascade_bluffs_spends_selected_input_and_records_it`
- `tests/test_phase9f5_followup_review.py::test_cascade_bluffs_colorless_mode_needs_no_input_and_filter_needs_choice`
- `tests/test_phase9f5_followup_review.py::test_executable_coverage_validates_complete_collected_pytest_node_id`

## Reproducible verification commands

The final PR commit must pass:

```text
uv sync --frozen --all-extras
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest -q -ra
uv run python scripts/check_manifest.py
uv run mtg-sim validate-sources
uv run mtg-sim validate-coverage
uv run mtg-sim validate-executable-coverage
uv run mtg-sim validate-prepolicy-readiness
uv run mtg-sim verify-rules --output artifacts/rules/phase9f5-final/
uv run mtg-sim pilot --config configs/pilot.toml --dry-run
uv run mtg-sim pilot --config configs/real-executor-smoke.toml --smoke
```

The final GitHub Actions run attached to the PR head is the authoritative record for its tested commit, commands, and outcomes. Earlier local or intermediate CI results are not presented as final evidence here.

The production pilot remains locked and was not run during this remediation.
