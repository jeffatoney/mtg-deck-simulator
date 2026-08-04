# MTG Deck Simulator Project Status

> **Last synchronized:** 2026-08-04 02:25 PT  
> **Repository:** `jeffatoney/mtg-deck-simulator`  
> **Phase B merge:** PR #37 merged into `main` at `4d1df5a68744864906e337d8ded17d12d7724d37`  
> **Active Phase C branch:** `phase-c/pilot-authorization`  
> **Phase C task:** issue #48  
> **Phase C execution status:** **LOCKED — NOT AUTHORIZED**

This dashboard separates completed Phase B certification from the new Phase C authorization process. No pilot or full-study game is authorized by the creation of the Phase C branch, issue, configuration, or draft pull request.

## Overview

| Phase | Status | Evidence or control |
|---|---|---|
| Phase A | **Complete and current** | Standing verifier and durable certification pass |
| Phase B | **Complete, merged, and durably certified** | PR #37 merged; 0 capability blockers; 12/12 transcripts approved; durable certification pass |
| Phase C pilot build | **Planning / locked** | Issue #48 and `phase-c/pilot-authorization` |
| Phase C 500/200 execution | **Not authorized** | `execution_allowed: false` in the frozen pilot configuration |
| Full 20,000/5,000 study | **Not authorized** | Requires a separate post-pilot decision |

## Completed Closeout

- Phase B exact-deck coverage reduced to zero unsupported or unverified capabilities.
- Strategic-model blockers reduced to zero.
- All 12 golden transcripts were corrected, executed, digest-bound, and owner-approved.
- Phase B verifier became a blocking CI gate.
- Durable Phase B certification was generated from CI evidence and committed.
- Issues #43, #44, and #45 were closed as completed.
- The `Protect main` active ruleset was verified from owner-provided GitHub screenshots.
- Issue #46 was closed after verifying required pull requests, required `checks`, up-to-date branches, conversation resolution, deletion restriction, and force-push blocking.
- PR #37 was changed from draft to ready and merged through the protected `main` branch.

## Certified Phase B Evidence

| Item | Value |
|---|---|
| Certified exact head | `47179414ee0de4b06e9353d4c2d40f2434069a93` |
| Certified CI | Run 712 / `30890042832` — SUCCESS |
| Full repository suite | 282 passed |
| Phase B mapped suite | 185 passed, 0 failed, 0 skipped, 0 xfailed |
| Unsupported capabilities | 0 |
| Strategic-model blockers | 0 |
| Transcript approvals | 12 of 12 |
| Approval-document SHA-256 | `242a43347f3d73405872b43820048497cf06101b4b02a637b009f0143200c53d` |
| Durable Phase B certification | PASS |
| Phase B result artifact | ID `8884688219`; ZIP SHA-256 `8a1f12a1fa435f8d1566833f7b9803f9823d7686c1511a8dd793301f9181fe44` |
| Phase B certification artifact | ID `8884688696`; ZIP SHA-256 `7f2031bce4bf17b91bde47994efdb62e301b4ae9d17670c638db6f8d9b1977ea` |
| Merge commit | `4d1df5a68744864906e337d8ded17d12d7724d37` |

The connected GitHub tool does not expose push-triggered workflow runs on `main`; independent confirmation of the post-merge `main` run remains a prerequisite inside issue #48 before any execution approval.

## Current Phase C Focus

The current work is authorization infrastructure only:

1. Freeze the exact 500-standard / 200-exploratory pilot configuration.
2. Build or verify a clean-engine production pilot runner.
3. Add dry-run, negative, replay, manifest, seed, and aggregation tests.
4. Add a manually locked workflow that cannot run while authorization is pending.
5. Pass protected-PR CI and preserve Phase A and Phase B certification-current gates.
6. Review the exact implementation commit, workflow digest, config digest, seed assignment, artifact schema, and stop conditions.
7. Record a separate explicit owner approval before changing `execution_allowed` to true.
8. Execute the pilot once and review it before considering the full study.

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
- Future information and post-result optimization are prohibited.
- Exploratory search must remain bounded and rules-validated.

Binding files:

- `docs/spec/phase-c/PHASE_C_PILOT_CONFIG.json`
- `docs/spec/phase-c/PHASE_C_PILOT_AUTHORIZATION.md`

## Current Blockers to Execution

| Blocker | State | Resolution |
|---|---|---|
| Post-merge `main` CI not independently visible through the connector | Pending confirmation | Verify the push-triggered run in GitHub Actions or provide its run ID |
| Clean-engine pilot runner | Not yet reviewed | Implement or verify through the Phase C PR |
| Phase C dry-run and negative evidence | Not yet present | Add and pass exact tests without running pilot games |
| Active workflow authorization gate | Not yet reviewed | Add an exact-token, digest-bound, fail-closed workflow |
| Owner authorization | Not granted | Approve the exact final commit, configuration digest, and workflow digest |
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
- Branch protection is active and issue #46 is complete.
- Phase C is a separate branch, issue, configuration, review, and approval process.
- Creation of Phase C documentation is not execution authorization.
- The confirmation token is `AUTHORIZE_PHASE_C_500_STANDARD_200_EXPLORATORY`.
- The full 20,000/5,000 study cannot be authorized by the pilot approval record.

## Next Required Actions

1. Open and review the Phase C authorization PR.
2. Confirm post-merge CI on `main`.
3. Implement the clean-engine pilot runner and inactive/manual-lock workflow.
4. Pass all dry-run and negative gates.
5. Present the final exact digests for owner review.
6. Do not run games until the explicit Phase C authorization is recorded.

## Repository Health

| Item | Current state |
|---|---|
| `main` protection | Active `Protect main` ruleset |
| Phase B PR | #37 merged |
| Phase B issues | #43–#46 closed as completed |
| Project synchronization | Phase C status maintained through issue #48 and this dashboard |
| Active work branch | `phase-c/pilot-authorization` |
| Pilot execution | Locked |
| Full study | Locked |
