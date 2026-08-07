# MTG Deck Simulator Project Status

> **Last synchronized:** 2026-08-06 18:10 PT
> **Repository:** `jeffatoney/mtg-deck-simulator`
> **Phase B merge:** PR #37 merged into `main` at `4d1df5a68744864906e337d8ded17d12d7724d37`
> **Active Phase C branch:** `phase-c/pilot-authorization`
> **Active Phase C draft PR:** #49
> **Phase C execution status:** **LOCKED — NOT AUTHORIZED**

This dashboard distinguishes technical implementation readiness from execution authorization. No pilot or full-study game is authorized by code, tests, a dry run, CI, certification renewal, or an owner-review package. `execution_allowed` remains false until a separate explicit owner decision under issue #51.

## Overview

| Phase | Status | Evidence or control |
|---|---|---|
| Phase A foundation | **Implemented; renewal required for covered Phase C changes** | Standing verifier remains the authority; exact-head durable certification must be renewed from CI candidate |
| Phase B deck/policy foundation | **Merged; renewal required for covered Phase C changes** | PR #37 merged with zero exact-deck blockers and 12 approved transcripts; Phase C covered changes require exact-head recertification |
| Phase C production runner | **Technical implementation candidate complete locally; exact-head CI pending** | Real Turn-10 policy/replay path, combat, exploratory expansion, combo detection, replay/rollback, and immutable artifacts have executable tests |
| Phase C authorization controls | **Implemented and locked; exact-head CI pending** | Reviewed implementation identity separated from later governance-only activation identity |
| Phase C 500/200 execution | **Not authorized** | `execution_allowed: false`; owner approval record pending; zero pilot games run |
| Full 20,000/5,000 study | **Not authorized** | Separate post-pilot owner decision required; zero full-study games run |

## Phase B handoff

- PR #37 merged through protected `main` at `4d1df5a68744864906e337d8ded17d12d7724d37`.
- At Phase B closeout, unsupported exact-deck capabilities were zero, strategic-model blockers were zero, all 12 golden transcripts were approved, the mapped suite was 185/185, and durable Phase B certification passed.
- Phase C now touches covered engine, policy, run, workflow, and certification surfaces. Those changes do not reopen the completed Phase B design work, but they do require new exact-head durable Phase A and Phase B certification records before owner review.

## Current Phase C technical candidate

The implementation candidate now includes:

1. Exact clean-engine 98-card library plus Malcolm/Breeches command-zone construction.
2. Replayable league 7 / free 7 / 6 / 5 / 4 draw-back-to-seven mulligan and Turn-1 draw.
3. Rules-owned progression through controlled Turn 10, including cleanup repetition and terminal short-circuiting.
4. Shared-ActionBroker legal combat with no blockers, opponent assignment, tapping, commander damage, and trigger timing.
5. Deterministic public-only `LOOK_SELECT` and `TUTOR_THIRD_FROM_TOP` strategic choices with recorded evaluator provenance and replayed choices.
6. Correct exact-X action enumeration for X spells rather than probing impossible target combinations at X=0.
7. Six frozen combo-access detectors with early/cumulative access, payable/protected legality, actual first attempt, tutor exclusivity, attack restrictions, and false-positive denial.
8. One audited exploratory production decision layer through the same broker/executor, with the existing hard upper bounds preserved and actual depth/node reporting.
9. Replay-safe atomic rollback that avoids recursively deep-copying replay history.
10. Cleanup policy bookkeeping derived without consuming engine identity or RNG.
11. Derived Phase C readiness blockers: readiness comes from executable production smokes rather than a hand-maintained tuple that can be emptied.
12. Strict Git-object-ID versus SHA-256 domain separation.
13. Implementation-commit/tree owner binding plus a later governance-only activation descendant with an allowlisted diff.
14. Deterministic 500/200 seed plan frozen into 10×50 standard and 10×20 exploratory shards.
15. Immutable raw technical-game, replay, measurement, per-game, shard-summary, shard-manifest, and final aggregate records with cross-file digest checks.
16. Hardened durable-certification provenance: covered hashes must come from the recorded certified commit/tree and GitHub Actions run, not hand-patched current content.
17. The temporary one-day exact-source export has been removed from ordinary CI in the candidate.

## Frozen pilot definition

- Standard games: 500, 10 shards of 50.
- Exploratory games: 200, 10 shards of 20.
- Deterministic disjoint standard/exploratory seed namespaces and exact seed digests.
- Controlled horizon: through end of Turn 10.
- Checkpoints: Turns 5, 6, 8, 10; Turn 8 primary.
- Opponent interaction: none modeled.
- Blocking: none modeled.
- Opponent wins: none modeled.
- Malcolm may connect and Glint-Horn may attack when legal.
- Unknown Breeches cards are excluded from deterministic resources.
- Standard policy: `anchor_balanced` with exact evaluator and learning-plan binding.
- Future information: prohibited.
- Post-result optimization/policy mutation: prohibited.
- Exploratory production decision-layer depth: exactly 1 for this pilot definition; existing hard branch/depth/node/beam/belief caps remain upper bounds and actual depth/nodes must be reported honestly.

Binding files:

- `docs/spec/phase-c/PHASE_C_PILOT_CONFIG.json`
- `docs/spec/phase-c/PHASE_C_PILOT_AUTHORIZATION.md`
- `docs/spec/phase-c/PHASE_C_PILOT_APPROVAL.json`
- `.github/workflows/phase-c-pilot.yml`

## Remaining gates before owner review

| Gate | Current state | Required next action |
|---|---|---|
| Local focused Phase C/Phase B/certification regressions | Passing | Preserve through publication and CI |
| Real policy-driven Turn-10/fresh replay smoke | Passing in isolated exact-source execution | Run as a mandatory CI step on pushed head |
| Formatting / lint / strict mypy | Awaiting GitHub CI | Must pass on exact pushed head |
| Full repository pytest | Awaiting GitHub CI | Must pass on exact pushed head |
| Phase A durable certification | Renewal pending | Generate exact-head CI candidate, commit it unmodified, rerun CI |
| Phase B durable certification | Renewal pending | Generate exact-head CI candidate, commit it unmodified, rerun CI |
| Second-pass exact-head review | Pending | Review final diff/tests/CI and repair any issue found |
| Owner authorization under #51 | **Not requested yet** | Request only after every technical/CI/certification gate is green |

## Active focused issues

Technical work remains tracked under #50 and #54–#63. Additional defects discovered by the real production path are tracked separately:

- #67 — deterministic `TUTOR_THIRD_FROM_TOP` choice support.
- #68 — durable Phase A/B certification provenance binding.
- #69 — X-spell enumeration and optional-trigger replay choices.
- #70 — cross-binding raw technical games, replay, measurements, and shard manifests.

Issues are closed only after their acceptance criteria are satisfied on the exact pushed/certified head.

## Authorization model

The owner does not approve the activation commit in advance. The owner approves the exact green **implementation commit/tree** and its locked configuration/workflow/count/shard/depth/token/seed evidence. A later activation commit may change only the allowlisted Phase C config and approval files. The activation workflow proves ancestry and the governance-only diff before any output is created.

The machine owner record remains pending, and the pilot config remains:

- `execution_allowed: false`;
- `status: LOCKED_PENDING_OWNER_APPROVAL`.

## Next required actions

1. Publish the technical candidate to existing branch `phase-c/pilot-authorization` and existing draft PR #49.
2. Run exact-head GitHub CI and repair any formatting, typing, test, verifier, readiness, or provenance failure.
3. Retrieve the exact Phase A and Phase B CI-produced certification candidates from that run.
4. Commit those candidates unmodified in a separate certification-renewal commit.
5. Rerun exact-head CI and continue repairing until all blocking gates are green.
6. Conduct a second-pass diff/test/audit review and close only acceptance-complete technical issues.
7. Present a digest-bound `OWNER DECISION REQUIRED` package under issue #51.
8. Do not run the pilot or full study until the owner explicitly approves the final package and a governance-only activation commit is created.

## Repository health

| Item | Current state |
|---|---|
| `main` protection | Active `Protect main`; redundant Phase A ruleset disabled |
| Phase B PR | #37 merged |
| Active Phase C PR | #49 draft |
| Recovery PRs | #64, #65, #66 preserved until consolidation is verified; none should be merged as final Phase C completion |
| Phase C runner issue | #50 in progress until exact-head CI/certification closeout |
| Pilot execution | Locked; 0 games executed |
| Full study | Locked; 0 games executed |
