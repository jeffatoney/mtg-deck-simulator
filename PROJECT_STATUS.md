# Phase B Project Status

> **Last verified:** 2026-08-03 10:47 PT  
> **Repository:** `jeffatoney/mtg-deck-simulator`  
> **Pull request:** #37 — draft  
> **Branch:** `engine/phase-b-full-deck-policy`  
> **Latest evaluated implementation head:** `de8b834ca7c29aabf680e20717df61315819611a`

This file is the executive mirror of the issue-backed GitHub Project task records. Update the task record and this dashboard together whenever work is created, completed, blocked, reopened, reprioritized, or moved to human review. Completion requires exact verification evidence; implementation presence alone is not completion. Dashboard-only commits may follow the evaluated implementation head without changing the recorded engineering verdict.

## Overview

**Phase B core milestone progress:** `[██████░░░░] 57%` — **4 of 7 core milestones verified complete**

- Verified complete: Slice 1 framework, Slice 2 framework, Slice 3 framework, and exact-head CI restoration.
- In progress: exact-deck runtime coverage and strategic-loop adjudication.
- Human review required: 12 mandatory golden-transcript approvals.
- Blocked: final Phase B verifier PASS and durable Phase B certification.
- Phase B candidate verdict: **FAIL**.
- Pilot-lock gate: **PASS**.

The progress percentage measures the seven core project milestones tracked in issues #39–#45. It is not a card-coverage percentage and does not imply certification readiness.

## Phase Summary Table

| Phase or milestone | Status | Verification basis | Task record |
|---|---|---|---|
| Phase A clean-engine foundation | **Current and passing** | Head `de8b834ca7c29aabf680e20717df61315819611a`; Phase A verifier 27/27 PASS; durable certification-current gate PASS | PR #35 / #38 |
| Phase B Slice 1 — deck construction and coverage framework | **Verified complete** | Head `8f7727026b0fee20a7f1ff242f9ee2cb73f8a16b`; CI `30685183470` PASS | #39 |
| Phase B Slice 2 — policy configuration and shared broker | **Verified complete** | Head `6964f231e22b7a116e10a4c4e988552e8d861608`; CI `30693534094` PASS; 123 tests | #40 |
| Phase B Slice 3 framework — search, measurement, replay, manifests, verifier tooling | **Verified complete for framework scope** | Head `2b4a25514c440cd96a147a488e2a6ab13679f6e6`; CI `30696609808` PASS; 144 repository tests; 47 Phase B tests | #41 |
| Restore current exact-head CI | **Verified complete** | Head `0bb6606cfa57097c698ce820efb5d56175259c06`; workflow run `30804677571` SUCCESS | #42 |
| Complete exact-deck runtime coverage | **In progress** | 38 unsupported/unverified capabilities remain; one strategic model blocker remains | #43 |
| Approve and execute 12 mandatory transcripts | **Human review required** | 12 files and digests exist; approval record is not owner-anchored | #44 |
| Phase B verifier PASS and durable certification | **Blocked** | Requires #43 and #44 to close on one exact commit | #45 |
| Phase C pilot | Not authorized | Pilot-lock gate passes; no pilot authorization or result is claimed | — |

## Current Sprint or Focus

1. Continue bounded Oracle-backed runtime batches against the 38 verified remaining capability blockers.
2. Prioritize shared primitives that can clear both an unsupported effect and its corresponding unverified card.
3. Resolve `UNSUPPORTED_STRATEGIC_LOOP:DUALCASTER_TWINFLAME` without treating the combo as an assumed strategic truth.
4. Obtain explicit owner review of the 12 golden-transcript candidates and exact digests.
5. Rerun the Phase B verifier after each bounded implementation batch and after transcript approval.

## Completed This Session

- Implemented the shared `LOOK_SELECT_REST_BOTTOM` production primitive with resolution-time opaque-handle card selection.
- Added explicit ordering for unselected cards placed on the library bottom.
- Added direct exact-deck execution evidence for Impulse and Sleight of Hand.
- Added an atomic negative test proving illegal provider output restores the library, hand, and stack.
- Added the exact runtime-batch-fifteen nodes to `B-COVERAGE-001` and updated the literal anti-overclaim regression before crediting either card.
- Registered `LOOK_SELECT_REST_BOTTOM` in the fail-closed runtime support registry after the first complete verifier exposed the missing registration.
- Renewed durable Phase A certification from exact CI-produced candidates after covered-kernel changes.
- Verified 233 repository tests, 136 mapped Phase B tests, and 27 Phase A verifier tests with no test failures.
- Reduced exact-deck blockers from 42 to 38 in this batch, and from the accepted Slice 3 baseline of 149 to 38.
- Updated issues #43–#45 and this dashboard together; no task was marked complete.

## Current Blockers

| Blocker | Current evidence | Required resolution | Task |
|---|---|---|---|
| Exact-deck runtime coverage incomplete | 17 unverified cards, 13 unsupported effects, and 8 unsupported automatic abilities; 38 total | Reach zero unsupported capabilities and 100 reviewed `IMPLEMENTED` physical cards | #43 |
| Strategic combo model unresolved | `UNSUPPORTED_STRATEGIC_LOOP:DUALCASTER_TWINFLAME` | Add reviewed, fail-closed loop adjudication outside the rules kernel | #43 |
| Transcript approval not owner-anchored | 12 candidate files and digests exist, but the approval record is not owner-anchored | Owner explicitly reviews and approves or rejects each exact digest | #44 |
| Durable Phase B certification unavailable | Phase B verifier status is FAIL | Pass verifier, generate immutable artifact, and commit current durable certification | #45 |

## Quality Dashboard

**Latest evaluated workflow:** run `30838101155` / run number 545 — **SUCCESS**  
**Phase B candidate verdict inside that workflow:** **FAIL**

| Gate | Evaluated-head status | Evidence |
|---|---|---|
| Dependency installation | PASS | Frozen environment installed |
| Frozen identity lock | PASS | Approved SHA-256 matched |
| Phase A authority classification | PASS | Clean production-path authority checks passed |
| Phase B authority and coverage checks | PASS | Required authority mappings and complete-deck coverage checks executed |
| Phase B evaluator and learning boundary | PASS | 77 classified effect kinds; 14 policy bundles; separation rules passed |
| Clean engine and support-package boundary | PASS | 64 Python files scanned; no forbidden findings |
| Legacy package import prohibition | PASS | `mtg_sim` not importable |
| Ruff formatting | PASS | 159 files already formatted |
| Ruff lint | PASS | All checks passed |
| Strict mypy | PASS | 64 source files, no issues |
| Standing Phase A verifier | PASS | 27 passed, 0 failed, 0 skipped, 0 xfailed |
| Full pytest suite | PASS | 233 passed |
| Manifest integrity | PASS | 34 frozen files and 18 required paths |
| Durable Phase A certification current | PASS | Certified covered-content digest verified |
| Phase B mapped tests | PASS | 136 passed, 0 failed, 0 skipped, 0 xfailed |
| Phase B requirement mapping | PASS | Complete |
| Strategic evaluator | PASS | Frozen evaluator and learning-plan identities verified |
| Pilot-lock gate | PASS | Verifier reports `pilot_lock: PASS` |
| Golden transcripts | **FAIL** | Approval record is not owner-anchored |
| Exact-deck capability coverage | **FAIL** | 38 unsupported/unverified capabilities |
| Strategic model | **FAIL** | One unresolved Dualcaster/Twinflame loop |
| Durable Phase B certification | BLOCKED | Phase B candidate is not PASS |

## Risks

- **Human approval dependency:** automation cannot approve transcript content or digests on the owner’s behalf. See #44.
- **Candidate-versus-golden confusion:** the 12 transcript files are candidates only; they do not count as approved evidence until the owner anchor exists and the gate executes them.
- **Large change surface:** the Phase B branch has a large commit and file footprint, increasing regression and review risk.
- **Repository protection:** branch protection or a repository ruleset is required but not currently verified as enabled. See #46.
- **Project integration limitation:** the available GitHub connection maintains issue-backed task records and repository files but cannot directly mutate GitHub Projects fields or board placement. See #47.

## Decisions Made

- The owner-approved single-owner exception remains in force; it does not permit automation to approve golden transcripts on the owner’s behalf.
- Coverage credit is granted only after direct production-path execution tests exist and the anti-overclaim regression is updated to the same reviewed evidence set.
- Existing production behavior may receive exact-deck credit only when its full card path is exercised and mapped into the Phase B verifier.
- Resolution-time strategic choices use opaque handles, are checked against exact legal sets and counts, and fail closed on invalid provider output.
- Library-bottom ordering is an explicit resolution-time choice and is recorded for replay rather than inferred by the rules kernel.
- A green workflow does not establish Phase B acceptance when the candidate verifier reports FAIL.
- General test success does not convert unapproved transcript candidates into golden-transcript evidence.
- The Phase B verifier remains fail-closed until transcript approval, exact-deck coverage, and strategic-loop adjudication all pass on one exact commit.
- GitHub issue records are the detailed task records; this file is the executive mirror. They must change together.

## Next Recommended Tasks

1. Continue the next bounded runtime batch from the 38-item capability list under #43.
2. Implement a shared primitive for one of the unsupported effect families with a matching unverified card, then add direct exact-deck tests before crediting it.
3. Resolve the Dualcaster/Twinflame strategic-loop blocker.
4. Record approval or requested correction individually for each transcript ID and digest in #44.
5. Rerun the Phase B verifier after each bounded batch and after transcript approval.
6. Close #45 only after golden transcripts report PASS, capability count is zero, strategic blockers are zero, and durable Phase B certification is current.
7. Enable and verify repository protection under #46.

## Repo Health

| Item | Current state |
|---|---|
| Repository | `jeffatoney/mtg-deck-simulator` |
| Active PR | #37 — `Phase B: migrate full deck and policy framework` |
| PR state | Open, draft, mergeable at last metadata check |
| Base | `main` at `b5743b54fa26e3e20c175fddb6401b390c828b8c` |
| Latest evaluated implementation head | `de8b834ca7c29aabf680e20717df61315819611a` |
| Latest evaluated workflow | Run 545 / `30838101155` — SUCCESS |
| Phase B verifier | FAIL — transcripts, 38 capabilities, and one strategic blocker |
| Phase B artifact | ID `8865663812`; ZIP SHA-256 `d0914414eea7172779793fd0d18f619bb1b79ec74e585caeb0c2f7964e0cf4da` |
| Durable Phase B certification | Not generated |
| Pilot authorization | Not present |
| Full-study authorization | Not present |
| Task synchronization | Issues #43–#45 and this dashboard synchronized in this run |
| Repository protection | Open risk #46 |
