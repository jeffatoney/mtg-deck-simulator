# Malcolm and Breeches Rules-Validated Simulator

This repository is the source of truth for a reproducible, deck-scoped Magic: The Gathering Commander simulator for the exact Malcolm and Breeches deck under `docs/source/`.

## Current status

`IDENTITY_MODEL_V2.0.0` is frozen and binding for the clean-engine build. The approved document, approval record, and lock manifest are:

- `docs/spec/identity/IDENTITY_MODEL_V2.0.0.md`
- `docs/spec/identity/IDENTITY_MODEL_V2.0.0_APPROVAL_RECORD.json`
- `docs/spec/identity/IDENTITY_MODEL_V2.0.0_LOCK_MANIFEST.txt`

The current development task is **Phase A: build the clean rules kernel and representative production-card slice**. Do not resume the older numbered prompt sequence.

## Start here

Read these files in order before changing engine code:

1. `AGENTS.md`
2. `docs/source/MagicCompRules_2026-06-19.txt`
3. The frozen Oracle snapshot under `docs/source/oracle/`
4. `docs/spec/LEAGUE_MULLIGAN.md`
5. The three frozen identity files listed above
6. `docs/spec/ENGINE_BUILD_PHASE_A.md`
7. `prompts/recovery/PHASE_A_ENGINE_BUILD.md`

## Clean-engine boundary

New engine work belongs in:

- `src/mtg_kernel/` — card-agnostic rules, state, actions, zones, stack, priority, triggers, turn processing, replay, and observations
- `src/mtg_cards/` — structured Oracle-backed card specifications and primitive compositions

The existing `src/mtg_sim/` implementation is legacy reference code during the transition. The clean packages may not import it, delegate rules execution to it, or use its event logs as substitutes for rules objects. See `docs/architecture/LEGACY_QUARANTINE.md`.

## Safety gates

- Unsupported rules behavior, cards, or scenarios fail closed.
- Production and full-study simulations remain locked.
- No pilot result is valid until the clean engine passes its Phase A gate, the complete deck is migrated, and the pilot is explicitly authorized.
- The frozen identity document must continue to match its approved SHA-256 digest.
- Real named cards must load complete records from the frozen Oracle snapshot; abbreviated behavior uses clearly named fictional fixtures.

## Repository checks

```bash
uv sync --frozen --all-extras
uv run python scripts/check_identity_lock.py
uv run python scripts/check_clean_engine_boundary.py
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest -q
uv run python scripts/check_manifest.py
uv run mtg-sim validate-sources
```

Phase A will add its own production-path acceptance command and artifacts. Do not treat the legacy smoke executor or legacy pilot command as proof that the clean engine works.

## Counts terminology

Keep these quantities separate:

- **Base seeds/scenarios:** random environments used for paired comparisons.
- **Policy-evaluation runs:** repeated executions of policies on the same base seeds.
- **Canonical standard games:** the 500 designated pilot outcomes after a preliminary policy is locked.
- **Exploratory games:** the 200 bounded-search outcomes paired with canonical Standard Games 1–200.

The policy-discovery process will produce more than 500 executions. Report the complete execution count; never label all policy evaluations as only “500 games.”
