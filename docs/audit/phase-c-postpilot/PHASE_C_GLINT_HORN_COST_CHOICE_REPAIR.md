# Phase C Glint-Horn Cost-Choice Repair

## Status

Classification: **BROKER_COST_CHOICE_REPAIR_CONFIRMED**. Stage 2 repairs the legal action surface and remeasures only the four frozen diagnostics. It does not authorize a pilot or certify PR #100.

## Exact repair

Starting head `cbfbcd437a91f0c4481cba2173a8a6e8cd6553e8` / tree `683243839e72a4c676cdd37310afc919775e762d` was repaired by `4d15c18592a8df1a6ba23df034c3b68701088315` / tree `f1ac2c11f1b0e989e13d3e7d72480779cfb7f4c8`. The executor is unchanged. `ActionBroker` now binds explicit battlefield discard costs before the normal executor probe. Private `discard_ids` stays in execution arguments; public actions expose only visible card semantics. `PublicActionKey` fails closed on `discard_ids`.

The implementation is generally correct for battlefield activated discard costs represented by `cost["discard"]`; the exact-deck proof is Glint-Horn. No claim is made for unrelated non-mana cost types.

## Information boundary, legality, and replay

Single-candidate, multiple-semantic-candidate, duplicate-equivalence, hidden-only mutation, broker execution, same-process replay, and fresh replay tests pass. Duplicate semantic choices collapse to one public equivalence class before opaque representative resolution. The executor still rejects omitted `discard_ids`. All four Stage 1 negative controls pass.

## Repaired-head frozen diagnostics

These facts are independently recomputed from the repaired-head raw decision arrays. The historical pre-repair archive remains immutable and is not evidence for the repaired action surface.

| Run | Decisions | Distinct-key ties | Selector disagreements | Glint candidates | Glint ACTIVATE | Selected loot | Attacking turns | Attempt | Malcolm/Glint checkpoints | Terminal / turns |
|---|---:|---:|---:|---:|---:|---:|---|---|---|---|
| legacy-101 | 154 | 48 | 32 | 13 | 7 | 2 | [10] | 10 / malcolm_glint_horn | {'10': True, '5': False, '6': False, '8': False} | ACTIVE / 10 |
| repaired-101 | 154 | 32 | 20 | 0 | 0 | 0 | [] | None / None | {'10': False, '5': False, '6': False, '8': False} | ACTIVE / 10 |
| legacy-391730338978874520 | 274 | 98 | 61 | 55 | 53 | 9 | [6, 7, 8, 9, 10] | 6 / malcolm_glint_horn | {'10': True, '5': False, '6': True, '8': True} | ACTIVE / 10 |
| repaired-391730338978874520 | 220 | 63 | 46 | 1 | 0 | 0 | [5, 6, 7, 8, 9, 10] | None / None | {'10': True, '5': True, '6': True, '8': True} | ACTIVE / 10 |

First divergences: seed 101 public key `9`, post-state `0`, public-state digest `0`; seed 391730338978874520 public key `9`, post-state `9`, public-state digest `9`.

Durable archive `docs/audit/phase-c-postpilot/evidence/pr100-glint-horn-repaired-behavior-4d15c185.zip`, SHA-256 `5f1706e2a9f1ef906938f6eef972c0f7258226f5b2e5dcb0ed008febb62eb996`. Its four raw members reproduce the first nondurable run byte-for-byte and all four have exact fresh replay equality.

## Seed-391 terminal regression

`uv run pytest -q tests/phase_c/test_phase_c_terminal_cleanup.py -vv` still fails because the repaired trajectory is `ACTIVE` while the frozen expectation remains `TERMINAL`. The expectation was not modified. The broker repair alone did not restore the terminal outcome.

## Attempt semantics and access witness

Attempt measurement code and `combo_access.py` are unchanged. The table reports current implementation behavior only. An owner methodology decision remains required for attempt semantics, and production-valid finite access-witness validation remains a separate blocker.

## Validation

At exact repair commit, ruff format/check, mypy, Glint-Horn focused tests, information-boundary tests/checker, broker tests, and Glint transcript pass. Full pytest is `426 passed, 1 failed`; the sole failure is the preserved seed-391 terminal regression. Validation source workflow run: `32016837499`.

## Governance

Corrected pilot authorized: `false`. Replacement 500/200 pilot authorized: `false`. Full study authorized: `false`. Historical pilot artifacts modified: `false`. PR #100 certified: `false`. PR #100 ready for review: `false`. PR #100 merged: `false`. PR #99 modified or integrated: `false`.

Remaining blockers: SEED_391_TERMINAL_REGRESSION_REMAINS, ACCESS_WITNESS_VALIDATION_REQUIRED, ATTEMPT_DEFINITION_OWNER_DECISION_REQUIRED.
