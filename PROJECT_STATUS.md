# MTG Deck Simulator Project Status

> **Last synchronized:** 2026-08-04 14:20 PT  
> **Repository:** `jeffatoney/mtg-deck-simulator`  
> **Phase B merge:** PR #37 merged into `main` at `4d1df5a68744864906e337d8ded17d12d7724d37`  
> **Active Phase C branch:** `phase-c/pilot-authorization`  
> **Phase C task:** issue #48  
> **Phase C execution status:** **LOCKED — NOT AUTHORIZED**

This dashboard separates completed Phase B certification from the Phase C authorization process. No pilot or full-study game is authorized by the creation of the Phase C branch, issue, configuration, draft pull request, control-plane code, or manual workflow.

## Overview

| Phase | Status | Evidence or control |
|---|---|---|
| Phase A | **Complete and current** | Standing verifier and durable certification pass |
| Phase B | **Complete, merged, and durably certified** | PR #37 merged; 0 capability blockers; 12/12 transcripts approved; durable certification pass |
| Phase C pilot control plane | **Implemented, locked, under CI review** | Deterministic seed plan, pending machine approval record, no-game dry run, fail-closed manual workflow |
| Phase C production game driver | **Not complete** | Explicit readiness blockers remain under issue #50 |
| Phase C 500/200 execution | **Not authorized** | `execution_allowed: false`; owner approval record pending |
| Full 20,000/5,000 study | **Not authorized** | Requires a separate post-pilot decision |

## Completed Closeout

- Phase B exact-deck coverage reduced to zero unsupported or unverified capabilities.
- Strategic-model blockers reduced to zero.
- All 12 golden transcripts were corrected, executed, digest-bound, and owner-approved.
- Phase B verifier became a blocking CI gate.
- Durable Phase B certification was generated from CI evidence and committed.
- Issues #43, #44, and #45 were closed as completed.
- `Protect main` is active and authoritative for `main`.
- The redundant `Protect main for Phase A` ruleset was disabled by the owner; issue #53 is closed.
- PR #37 was merged through the protected `main` branch.

## Certified Phase B Evidence

| Item | Value |
|---|---|
| Certified exact head | `47179414ee0de4b06e9353d4c2d40f2434069a93` |
| Certified CI | Run 712 / `30890042832` — SUCCESS |
| Full repository suite at Phase B closeout | 282 passed |
| Phase B mapped suite | 185 passed, 0 failed, 0 skipped, 0 xfailed |
| Unsupported capabilities | 0 |
| Strategic-model blockers | 0 |
| Transcript approvals | 12 of 12 |
| Approval-document SHA-256 | `242a43347f3d73405872b43820048497cf06101b4b02a637b009f0143200c53d` |
| Durable Phase B certification | PASS |
| Merge commit | `4d1df5a68744864906e337d8ded17d12d7724d37` |

## Current Phase C Focus

The current work remains authorization infrastructure and clean production-runner engineering:

1. **Complete:** frozen 500-standard / 200-exploratory configuration.
2. **Complete:** deterministic, disjoint 500/200 seed-plan contract.
3. **Complete:** machine-readable owner approval record, still pending.
4. **Complete:** no-game dry-run command that creates no result artifact.
5. **Complete:** manually dispatched workflow with exact token, commit, config digest, workflow digest, and Phase A/B gates.
6. **In progress:** controlled-turn production driver.
7. **In progress:** legal combat action path for Malcolm and Glint-Horn under the frozen no-blocking model.
8. **In progress:** production-state exploratory expansion through the shared broker.
9. **In progress:** complete combo-access detectors for every measured package.
10. **Pending:** final owner review and exact digest-bound authorization.

## Frozen Pilot Configuration

- Exact 98-card library.
- Commanders Malcolm, Keen-Eyed Navigator and Breeches, Brazen Plunderer.
- Three opponents.
- Controlled player draws on Turn 1.
- League mulligan: 7, free 7, 6, 5, 4; never below four; refill to seven.
- Simulate through the end of controlled Turn 10.
- Checkpoints: Turns 5, 6, 8, and 10; Turn 8 primary.
- Opponent interaction, blocking, and opponent wins are not modeled.
- Malcolm may connect and Glint-Horn may attack when legal.
- Unknown Breeches cards do not become deterministic resources.
- Objective: maximize legal deterministic table-win access.
- Standard pilot: 500 games.
- Exploratory pilot: 200 games, reported separately.
- Standard policy: `anchor_balanced` with exact config/evaluator/learning-plan bindings.
- Future information and post-result optimization are prohibited.
- Exploratory search must remain bounded and rules-validated.

Binding files:

- `docs/spec/phase-c/PHASE_C_PILOT_CONFIG.json`
- `docs/spec/phase-c/PHASE_C_PILOT_AUTHORIZATION.md`
- `docs/spec/phase-c/PHASE_C_PILOT_APPROVAL.json`
- `.github/workflows/phase-c-pilot.yml`

## Current Blockers to Execution

| Blocker | State | Resolution |
|---|---|---|
| Controlled-turn driver | Not implemented | Add production orchestration through Turn 10 |
| Combat action path | Not implemented | Add legal declare-attackers and unblocked-combat execution |
| Exploratory production expansion | Not implemented | Clone and expand only through the shared broker and hidden-safe observation |
| Combo-access detectors | Incomplete | Replace unsupported-package records with legal detectors for every measured package |
| Owner authorization | Not granted | Approve the final exact commit, configuration digest, workflow digest, and machine approval record |
| Full study authorization | Prohibited | Review the completed pilot under a separate decision |

## Quality and Safety Requirements

Every Phase C change must preserve:

- frozen identity integrity;
- Phase A authority and durable certification;
- Phase B verifier and durable certification;
- exact-deck coverage with zero unsupported capabilities;
- 12 approved transcript digests;
- hidden-future denial;
- no post-result optimization;
- no legacy `mtg_sim` import or execution;
- deterministic, disjoint seed assignments;
- immutable manifests and replay transcripts;
- separate standard and exploratory reporting;
- fail-closed game counts and authorization.

## Decisions Made

- Phase B is closed and merged; it is not reopened by Phase C planning.
- `Protect main` is the sole active authoritative ruleset; the old Phase A ruleset is disabled.
- Phase C is a separate branch, issue, configuration, review, and approval process.
- Creation of Phase C code or workflow is not execution authorization.
- The confirmation token is `AUTHORIZE_PHASE_C_500_STANDARD_200_EXPLORATORY`.
- The full 20,000/5,000 study cannot be authorized by the pilot approval record.
- The dry run must disclose incomplete engine paths rather than fabricate readiness.

## Next Required Actions

1. Finish issue #50’s controlled-turn, combat, exploratory expansion, and combo-detection implementation.
2. Pass all Phase C negative, dry-run, replay, manifest, and same-commit gates.
3. Renew affected Phase A and Phase B durable certifications.
4. Present the final exact commit and file digests for owner review under issue #51.
5. Do not run games until explicit authorization is recorded.

## Repository Health

| Item | Current state |
|---|---|
| `main` protection | Active `Protect main`; redundant old ruleset disabled |
| Phase B PR | #37 merged |
| Phase B issues | #43–#46 closed as completed |
| Governance issue | #53 closed as completed |
| Active work branch | `phase-c/pilot-authorization` |
| Active draft PR | #49 |
| Phase C parent | #48 — locked |
| Phase C runner build | #50 — in progress |
| Pilot execution | Locked; 0 games executed |
| Full study | Locked; 0 games executed |
