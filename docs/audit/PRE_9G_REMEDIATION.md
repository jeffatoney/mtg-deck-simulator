# Pre-9G remediation audit

## Original CI pytest failures

The branch available in this workspace did not reproduce the reported CI run #61 failures: before any code changes, `uv run pytest -q -ra` completed with `274 passed in 40.42s`, and `uv run pytest -vv --maxfail=0` completed with `274 passed in 39.53s`. Therefore there were no local failing node IDs or tracebacks to capture from the current repository state.

## Legacy expectation corrected

- `tests/test_phase9f1_executable_adapters.py::test_bounce_filter_and_entry_tapped` previously exercised Cascade Bluffs as though its filter mode produced a single `U` after paying `R`. The frozen Oracle text for Cascade Bluffs has a separate `{T}: Add {C}.` ability and a filter ability of `{U/R}, {T}: Add {U}{U}, {U}{R}, or {R}{R}.` The test now asserts the filter activation requests a two-mana output (`UR`) and has a separate regression test for the colorless mode from an empty mana pool.

## Review remediation summary

- Commander replacement is now applied from state-based actions by using the existing `move_to_graveyard_or_command_zone` path, preserving commander cast counts and replacement bookkeeping.
- Combat damage now returns immediately after the legal state-based-action checkpoint if the game reaches terminal table-win, before Breeches exiles unknown cards or later combat bookkeeping is appended.
- Executable adapter evidence now uses pytest node IDs instead of generated SEM-* identifiers, and validation rejects generated semantic IDs or nonexistent evidence files.
- Commit target validation is part of `validate_action`, so illegal stack/permanent targets are rejected before the card leaves hand or mana is paid.
- Split spell stack metadata records only the chosen face's type while on the stack.
- Sentinel Totem and Soul-Guide Lantern now resolve as artifact permanents with their modeled activated abilities available.
- Cascade Bluffs now supports the colorless mana ability without input and filter outputs that pay exactly one `U` or `R` to produce a legal two-mana combination.
