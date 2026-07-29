# Legacy Engine Quarantine

**Status:** Active when the engine-preparation pull request is merged.

## Purpose

The repository already contains a legacy implementation under `src/mtg_sim/`. It preserves useful source-validation work, deck coverage records, historical tests, and examples, but it is not the rules authority or the production path for the clean Phase A engine.

Keeping it temporarily avoids destructive cleanup before the replacement engine has independent evidence. Quarantine means isolation, not endorsement.

## Quarantined path

```text
src/mtg_sim/
```

Existing tests, configurations, reports, and commands that execute this package are also legacy evidence unless a Phase A contract explicitly reclassifies them after independent review.

## Allowed during Phase A

- Read legacy code to identify prior scenarios, source paths, and known failure modes.
- Port a scenario as a new production-path test after validating it against the Comprehensive Rules and frozen Oracle data.
- Keep existing legacy checks running while the clean engine is built, provided they are not reported as clean-engine acceptance evidence.
- Compare legacy and clean outputs diagnostically, provided the legacy result is never treated as ground truth.

## Forbidden during Phase A

- `src/mtg_kernel/` or `src/mtg_cards/` importing any `mtg_sim` module.
- The clean engine wrapping, subclassing, delegating to, or monkey-patching the legacy `GameExecutor`.
- Reusing a legacy event log in place of real objects, actions, choices, stack entries, triggers, or zone transitions.
- Calling a legacy pilot or smoke run proof that the clean engine passes.
- Copying card-name branches into the new kernel.
- Silently using legacy remembered card text instead of the frozen Oracle record.
- Editing legacy output artifacts so they appear to have been produced by the clean engine.

## Evidence labels

Every reported command or artifact must identify one of these paths:

```text
CLEAN_ENGINE_PRODUCTION_PATH
LEGACY_REFERENCE_PATH
SOURCE_VALIDATION_ONLY
```

Only `CLEAN_ENGINE_PRODUCTION_PATH` evidence can satisfy the Phase A completion gate.

## Removal gate

Do not delete or rename the legacy package merely to make the repository look clean. Removal becomes appropriate only after:

1. the clean Phase A engine passes its complete gate;
2. the complete 98-card library is migrated in Phase B;
3. required source validation and reporting functions have clean replacements;
4. no active workflow or documented command depends on the legacy package;
5. retained historical artifacts remain readable without executing legacy code;
6. the owner approves the exact removal list.

Until then, quarantine is safer than deletion.
