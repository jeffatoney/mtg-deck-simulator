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
- Sentinel Totem and Soul-Guide Lantern resolve as artifact permanents with their modeled activated abilities available. Soul-Guide Lantern keeps its mandatory targeted ETB trigger: when modeled graveyard cards exist, exactly one card target must be chosen; when none exist, the no-legal-choice rule removes the trigger instead of creating an optional no-target event. The optional no-target review suggestion was not implemented because the frozen Oracle text says "exile target card from a graveyard" and is governed by CR 115.1d and CR 603.3d, not an "up to one" template.
- Psychosis Crawler's power and toughness are refreshed from the controller's current hand size before state-based actions and after event-recorded hand changes. It is not treated as a static 0/0.
- Cascade Bluffs has a no-input colorless action and explicit filter branches for each payable input (`U` or `R`) and output (`UU`, `UR`, or `RR`). The selected input is paid and recorded.
- Commit routes permanent targets through explicit zone handling: ordinary owned nontoken permanents move second from the top of their owner's modeled library, Malcolm and Breeches use the command-zone replacement choice or move second from the top if replacement is declined, token copies cease to exist without entering a library or command zone, illegal targets are not moved on resolution, and opponent-owned permanents remain illegal until opponent libraries are modeled.
- Cleanup removes all marked damage from surviving permanents during each cleanup step, after pre-cleanup state-based actions can remove lethally damaged creatures and again for repeated cleanup steps.

## Regression evidence

The focused follow-up tests are in:

- `tests/test_phase9f5_final_review.py::test_commit_owned_permanent_goes_second_from_top_and_replays_zone_result`
- `tests/test_phase9f5_final_review.py::test_commit_malcolm_and_breeches_token_copies_cease_without_library_or_command_zone`
- `tests/test_phase9f5_final_review.py::test_commit_commanders_use_replacement_or_decline_second_from_top`
- `tests/test_phase9f5_final_review.py::test_commit_rejects_opponent_permanent_and_illegal_resolution_does_not_move`
- `tests/test_phase9f5_final_review.py::test_cleanup_clears_damage_and_prevents_carryover_but_not_lethal_sba`
- `tests/test_phase9f5_final_review.py::test_cleanup_clears_every_survivor_and_repeated_cleanup_damage`
- `tests/test_phase9f5_final_review.py::test_soul_guide_lantern_mandatory_targeting_and_replay`
- `tests/test_phase9f5_final_review.py::test_soul_guide_lantern_generates_each_target_and_empty_graveyard_removes_trigger`
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
