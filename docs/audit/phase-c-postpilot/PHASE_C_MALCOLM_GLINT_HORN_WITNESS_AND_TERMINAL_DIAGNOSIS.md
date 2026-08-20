# Phase C Malcolm/Glint-Horn Witness and Terminal Diagnosis

**Date:** 2026-08-17  
**PR:** #100  
**Branch:** `hardening/public-policy-noninterference`  
**Starting head:** `8d97868fbcfb04204fb2b4cb05f4ff0137207b78` (`36ea80efc670f9e9c25955a3fa7080f72617699a`)  
**Diagnostic source:** `e6b1134ef5a0d64dca8503740948ca2cec76df57` (`b44c92b7e491eb4c12fbe76529807973506fe9dd`)

## Verdict

Stage 3 confirms finite production table-win witnesses for all three positive Malcolm/Glint-Horn first-access states. The Phase C pilot checkpoint measurement is aligned with the written table-win-access contract because the actual `GameMeasurement.checkpoint_table_win_access` predicate requires both `legally_executable` and `full_table_kill`. The legal-only `PhaseCTechnicalGame.combo_checkpoint_access` field is a separate technical diagnostic and must not be substituted for the measurement field.

The current seed-391 `ACTIVE` result is internally consistent with repaired STANDARD policy behavior. A finite table-win witness exists, but STANDARD does not select that line. The standing `TERMINAL` expectation is classified `SEED_391_TERMINAL_EXPECTATION_STALE_AFTER_ACTION_SURFACE_REPAIR`. No test expectation is changed in Stage 3.

Stage 3 also identifies a separate Malcolm/Glint tracker field inconsistency: in both seed-391 first-access states, untapped Treasure resources make the line legally executable and fully lethal, while `sufficient_mana` remains false and the snapshot retains `INSUFFICIENT_MANA_OR_DISCARD`. This supporting-field defect does not invalidate the production witnesses or the checkpoint table-win predicate for the tested states.

## Exact state

The live PR initially matched the handoff exactly at `8d97868fbcfb04204fb2b4cb05f4ff0137207b78` / `36ea80efc670f9e9c25955a3fa7080f72617699a`. The branch moved during Stage 3 only through diagnostic/test commits and temporary probes. Every intervening change was inspected. None changed `combo_access.py`, measurement records or aggregation, attempt detection, the Phase C runner, STANDARD selection, terminal handling, Glint-Horn execution, public-action semantics, replay, or Stage 1/2 evidence. Temporary probes were removed. The clean diagnostic tree is `b44c92b7e491eb4c12fbe76529807973506fe9dd`.

PR #100 remains open, draft, and unmerged against `150671a8e7a78e5fa14b6b3aca2308f6af647df3`. PR #99 remains separate, open/draft/unmerged, and was not modified or integrated. Issue #52 remains open.

Final Stage 3 tree changes are limited to the permanent witness-contract test plus this report, its JSON companion, and the evidence index. No historical pilot artifact was modified.

## Prior findings preserved

- Stage 1 remains `BROKER_STAGE_ENUMERATION_DEFECT`.
- Stage 2 remains `BROKER_COST_CHOICE_REPAIR_CONFIRMED`.
- The executor was not changed by the broker repair.
- Private discard object IDs remain broker-private and fail closed at the public action boundary.
- `docs/audit/phase-c-postpilot/evidence/pr100-corrected-behavior-971f5567.zip` remains immutable historical evidence only, SHA-256 `7e314f859d1e774b232f1d3daeed146441553e8f31c9aa0615a428d37a8aad8a`.
- `docs/audit/phase-c-postpilot/evidence/pr100-glint-horn-repaired-behavior-4d15c185.zip` remains the repaired behavioral authority, SHA-256 `5f1706e2a9f1ef906938f6eef972c0f7258226f5b2e5dcb0ed008febb62eb996`.
- `.github/workflows/phase-c-diagnostic.yml` remains permanent repository infrastructure. No temporary workflow or Stage 3 probe remains in the final tree.

## Repaired archive revalidation

The repaired archive hash, member set, and all four member hashes were independently recomputed from raw trace bytes rather than copied from the Stage 2 summary. Results:

| Run | Decisions | Ties | Selector disagreements | Glint candidates | Glint ACTIVATE | Selected loot | Attacking turns | Attempt | Terminal |
|---|---:|---:|---:|---:|---:|---:|---|---|---|
| Legacy 101 | 154 | 48 | 32 | 13 | 7 | 2 | 10 | 10 | ACTIVE |
| Repaired 101 | 154 | 32 | 20 | 0 | 0 | 0 | none | none | ACTIVE |
| Legacy 391730338978874520 | 274 | 98 | 61 | 55 | 53 | 9 | 6-10 | 6 | ACTIVE |
| Repaired 391730338978874520 | 220 | 63 | 46 | 1 | 0 | 0 | 5-10 | none | ACTIVE |

First repaired-head divergences also recompute exactly: seed 101 public key 9, post-state 0, public-state digest 0; seed 391 public key 9, post-state 9, public-state digest 9. Fresh replay agrees for all four traces.

## Exact first-access states

### Repaired seed 391730338978874520, Turn 5

The first legal snapshot is in `COMBAT_DAMAGE` with P0 priority and a Malcolm Pirate-damage trigger on the stack. Glint-Horn is tapped, attacking, has haste, and entered this turn. Malcolm and Siren Stormtamer are also attacking. P0 has one untapped Treasure, W in the pool, seven discardable cards, library size 85, and opponents at 36/37/38. The public broker menu contains Treasure activations for B/G/R/U/W plus PASS. STANDARD selects Treasure->W; the production witness selects Treasure->R.

Tracker: pieces assembled true; `sufficient_mana=false`; `legally_executable=true`; `full_table_kill=true`; conditional false; blocker `INSUFFICIENT_MANA_OR_DISCARD`. The contradiction is the Treasure-resource supporting-field defect described below.

### Legacy seed 391730338978874520, Turn 6

The first legal snapshot is also `COMBAT_DAMAGE` with P0 priority and a Malcolm trigger on the stack. Glint-Horn is tapped and attacking with haste. P0 has one untapped Treasure, B in the pool, six discardable cards, library size 82, and opponents at 34/37/39. The public menu is the same five Treasure colors plus PASS. The legacy handle-based selector chooses Treasure->U; the production witness chooses Treasure->R.

Tracker again reports `sufficient_mana=false`, `legally_executable=true`, `full_table_kill=true`, conditional false, and `INSUFFICIENT_MANA_OR_DISCARD`.

### Legacy seed 101, Turn 10

The first legal snapshot is earlier in the sequential line: `PRECOMBAT_MAIN`, empty stack, P0 priority, Glint-Horn still in hand. Malcolm is on the battlefield and attack-eligible. P0 has RRRUU in the pool plus one untapped Island, four discardable cards, library size 75, and opponents at 38/38/37. The broker has eight public classes: two Curiosity casts, Faithless Looting flashback, Glint-Horn cast, Island->U, Muddle transmute, Psychosis Crawler cast, and PASS. The legacy selector chooses Island->U. The production witness begins by casting Glint-Horn.

Tracker: pieces assembled, sufficient mana, legal executable, and full table kill are all true; conditional false; blockers empty.

### Repaired seed 101 negative control

No Malcolm/Glint-Horn legal-access state exists through Turn 10. All four checkpoints are false, no Glint candidate appears in 154 repaired decisions, no attempt is recorded, terminal status is ACTIVE, and fresh replay matches the final state. At the last Turn-10 postcombat policy decision, PASS is the only public action.

## Production witnesses

All three positive states are classified `FINITE_PRODUCTION_TABLE_WIN_WITNESS_CONFIRMED`. The aggregate classification is `PRODUCTION_TABLE_WIN_WITNESSES_CONFIRMED`.

For repaired seed 391 and legacy seed 391, the sequential witness starts by activating the existing Treasure for R. That action is legal through the production broker even though `glint-horn:loot` is not yet in the original menu. Glint-Horn loot then becomes a legal public action. The broker selects the action by public semantics, resolves its opaque execution handle only after public selection, and privately binds a legal discard. Production resolution deals one to each living opponent, Malcolm creates Treasure for each opponent damaged, the loot ability draws a card, and the process repeats. The opponent-life maxima bound the loops at 38 and 39 iterations respectively.

For legacy seed 101, the witness starts by casting Glint-Horn, resolves it through production priority, advances legally to combat, declares an attack containing Glint-Horn and Malcolm through the broker, applies the frozen no-blocker model, resolves combat/Malcolm resources, then repeats the same broker-probed loot engine until terminal. At most 38 loot-damage iterations are required after the setup.

The permanent regression uses only the production `GameExecutor`, `ActionBroker`, public semantic action boundary, production turn/combat progression, trigger resolution, and production replay. It asserts the next controlled-player action exists in the broker menu before execution. It does not consult future information, hidden opponent cards, favorable opponent choices, or a measurement-only legality shortcut. Same-process and fresh-process replay are asserted on the terminal witness transcripts.

## Tracker resource-field finding

Classification: `MALCOLM_GLINT_HORN_RESOURCE_FIELD_INCONSISTENCY`.

In `_malcolm_glint_horn`, `sufficient_mana` is derived from a floating-mana payment sequence, but later legal/full-kill predicates also count untapped Treasure resources. That is why both seed-391 first-access states can truthfully have a production Treasure->R first step and a finite table kill while the snapshot still says `sufficient_mana=false` with an insufficient-mana blocker. Population magnitude is unmeasured. Stage 3 does not change `combo_access.py`.

## Measurement-contract audit

The written authority separates component assembly, sufficient mana, legal executability, actual attempt, resolution, full-table kill, and conditional kill/takeover. Phase C pre-registers **legal deterministic table-win access** at Turns 5/6/8/10, with Turn 8 primary.

The implementation has two different checkpoint surfaces:

1. `ComboAccessTracker.earliest_legal_turn()` and `cumulative_checkpoint_access()` use `legally_executable` only and populate the technical-game diagnostic surface.
2. `_build_game_measurement()` computes `GameMeasurement.checkpoint_table_win_access` from `record.turn <= checkpoint AND record.legally_executable AND record.full_table_kill`. Aggregation and pilot reporting consume this measurement field.

The locked historical STANDARD aggregate therefore records 82/500 = **16.4%** by Turn 8 and 113/500 = **22.6%** by Turn 10 from the legal-and-full-table-kill predicate. The paired primary artifact names the metric `LEGAL_DETERMINISTIC_TABLE_WIN_ACCESS`.

Classification: `TABLE_WIN_ACCESS_CONTRACT_ALIGNED`. The legal-only technical checkpoint must not be substituted for the pilot measurement. No historical table-win percentage erratum is required and no historical percentage is changed. Witness confirmation for these three states does not establish population-wide witness validity.

## Seed-391 terminal regression

The standing test still expects `TERMINAL`; the repaired STANDARD trajectory is `ACTIVE`. The expectation was introduced in commit `b089d396b88172fb2681a2b2a235d14d8b9afcd3` while hardening cleanup termination, binding the test to the then-current deterministic trajectory.

The repaired Turn-5 state has a finite full-table-win witness. STANDARD does not follow it: at first access it selects Treasure->W rather than the witness's Treasure->R, and across the repaired trajectory it selects no Glint-Horn loot activation. The game remains ACTIVE through Turn 10 and fresh replay agrees. No production execution or terminal-engine defect is needed to explain that result.

Classification: `SEED_391_TERMINAL_EXPECTATION_STALE_AFTER_ACTION_SURFACE_REPAIR`. Stage 3 does not change the expectation.

## Attempt semantics

The current capture examines the legal-access snapshot **before** the selected action executes, then counts only a package-piece commitment or Glint attack when that pre-action snapshot is already legal. That ordering explains why repaired seed 391 can establish access during Turn 5 yet remain never-attempted.

Observed timelines:

| Trace | Broad Malcolm commitment | Glint cast | Glint attack | First loot | Current attempt | Constructed witness first action |
|---|---|---|---|---|---|---|
| Legacy 101 | T3 | T10 | T10 | T10 | T10 | T10 cast Glint |
| Legacy 391 | T3 | T6 | T6 | T6 | T6 | T6 Treasure->R |
| Repaired 391 | T3 | T5 | T5 | none | none | T5 Treasure->R |

Owner methodology options remain open: first selected action in a complete witness; first resource commitment to the package; direct engine activation/equivalent; or preserve the current package-piece definition. The first option additionally needs a rule for witness minimality because an actual policy action such as Treasure->W can be a nonminimal prefix to a later winning line. Options 1-3 can change never-attempted and immediate/delayed counts and would require versioning/recomputation for historical comparability. Option 4 preserves current historical comparability.

Classification: `ATTEMPT_DEFINITION_OWNER_DECISION_REQUIRED`. Stage 3 chooses none.

## Classifications

- Repaired seed 391 Turn 5: `FINITE_PRODUCTION_TABLE_WIN_WITNESS_CONFIRMED`
- Legacy seed 391 Turn 6: `FINITE_PRODUCTION_TABLE_WIN_WITNESS_CONFIRMED`
- Legacy seed 101 Turn 10: `FINITE_PRODUCTION_TABLE_WIN_WITNESS_CONFIRMED`
- Aggregate witness: `PRODUCTION_TABLE_WIN_WITNESSES_CONFIRMED`
- Measurement contract: `TABLE_WIN_ACCESS_CONTRACT_ALIGNED`
- Seed-391 terminal: `SEED_391_TERMINAL_EXPECTATION_STALE_AFTER_ACTION_SURFACE_REPAIR`
- Attempt definition: `ATTEMPT_DEFINITION_OWNER_DECISION_REQUIRED`
- Supporting tracker fields: `MALCOLM_GLINT_HORN_RESOURCE_FIELD_INCONSISTENCY`

## Recommended Stage 4 boundary

Stage 4 should be narrow and separated by concern. First, make Malcolm/Glint `sufficient_mana` and blocker accounting use the same Treasure-aware resource model as the legal/full-kill predicate, with focused regressions. Second, if the owner accepts the terminal classification, update only the stale seed-391 regression expectation/fixture to the repaired STANDARD `ACTIVE` trajectory; do not change terminal handling or STANDARD scoring/order to force the old result. Third, implement any attempt-definition change only after the owner selects a methodology and version/recompute affected attempt summaries.

Stage 4 must not revisit the Stage 2 discard-cost repair, executor activation/trigger/terminal semantics, public-information boundary, table-win measurement schema/aggregation, historical raw archives/percentages, pilot authorization, certification, PR #99, or merge state.

## Validation

Starting exact-head CI run `32019736225` established the handoff baseline: `426 passed, 1 failed`, with only the seed-391 terminal cleanup assertion failing. Stage 3 final exact-head command results and normal PR CI run IDs are reported after publication/read-back. The intentional terminal assertion failure remains evidence and is not weakened.

## Governance

- corrected pilot authorized: false
- replacement 500/200 pilot authorized: false
- full study authorized: false
- historical pilot artifacts modified: false
- PR #100 certified: false
- PR #100 ready for review: false
- PR #100 merged: false
- PR #99 modified or integrated: false
