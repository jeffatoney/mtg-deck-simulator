# Phase B Project Status

> **Last verified:** 2026-08-03 10:23 PT  
> **Repository:** `jeffatoney/mtg-deck-simulator`  
> **Pull request:** #37 — draft  
> **Branch:** `engine/phase-b-full-deck-policy`  
> **Latest evaluated implementation head:** `86404efb6de25f598bb6fd2a951deea963aa35b3`

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
| Phase A clean-engine foundation | **Current and passing** | Head `86404efb6de25f598bb6fd2a951deea963aa35b3`; Phase A verifier 27/27 PASS; durable certification-current gate PASS | PR #35 / #38 |
| Phase B Slice 1 — deck construction and coverage framework | **Verified complete** | Head `8f7727026b0fee20a7f1ff242f9ee2cb73f8a16b`; CI `30685183470` PASS | #39 |
| Phase B Slice 2 — policy configuration and shared broker | **Verified complete** | Head `6964f231e22b7a116e10a4c4e988552e8d861608`; CI `30693534094` PASS; 123 tests | #40 |
| Phase B Slice 3 framework — search, measurement, replay, manifests, verifier tooling | **Verified complete for framework scope** | Head `2b4a25514c440cd96a147a488e2a6ab13679f6e6`; CI `30696609808` PASS; 144 repository tests; 47 Phase B tests | #41 |
| Restore current exact-head CI | **Verified complete** | Head `0bb6606cfa57097c698ce820efb5d56175259c06`; workflow run `30804677571` SUCCESS | #42 |
| Complete exact-deck runtime coverage | **In progress** | 42 unsupported/unverified capabilities remain; one strategic model blocker remains | #43 |
| Approve and execute 12 mandatory transcripts | **Human review required** | 12 files and digests exist; approval record is not owner-anchored | #44 |
| Phase B verifier PASS and durable certification | **Blocked** | Requires #43 and #44 to close on one exact commit | #45 |
| Phase C pilot | Not authorized | Pilot-lock gate passes; no pilot authorization or result is claimed | — |

## Current Sprint or Focus

1. Continue bounded Oracle-backed runtime batches against the 42 verified remaining capability blockers.
2. Prioritize shared primitives that can clear both an unsupported effect and its corresponding unverified card.
3. Resolve `UNSUPPORTED_STRATEGIC_LOOP:DUALCASTER_TWINFLAME` without treating the combo as an assumed strategic truth.
4. Obtain explicit owner review of the 12 golden-transcript candidates and exact digests.
5. Rerun the Phase B verifier after each bounded implementation batch and after transcript approval.

## Completed This Session

- Added a kernel-side resolution-time card-selection contract using opaque handles, explicit minimum/maximum bounds, provider metadata, replay support, and fail-closed legality checks.
- Added deterministic policy selections for discarding and untapping lands without moving policy logic into the rules kernel.
- Implemented `DRAW_DISCARD` and `DRAW_DISCARD_UNTAP_LANDS` on the shared production executor.
- Added direct exact-deck evidence for Faithless Looting in normal and flashback modes, including its post-draw discard decision and flashback exile destination.
- Added direct exact-deck evidence for Frantic Search drawing two, discarding two at resolution, and untapping up to three selected controlled lands.
- Added an atomic negative test proving an illegal provider handle rolls the resolution back without changing the library, hand, or stack.
- Added all three runtime-batch-fourteen tests to `B-COVERAGE-001` and updated the literal anti-overclaim regression before crediting either card.
- Applied the exact Ruff artifact exposed by intermediate CI and corrected the exact Faithless Looting mode names exposed by the first full test run.
- Renewed durable Phase A certification from the exact CI-produced candidate for covered kernel changes.
- Verified 230 repository tests, 133 mapped Phase B tests, and 27 Phase A verifier tests with no test failures.
- Reduced exact-deck blockers from 46 to 42 in this batch, and from 50 to 42 since the prior user-facing update.
- Kept issues #43–#45 and this dashboard open; no task was marked complete.

## Current Blockers

| Blocker | Current evidence | Required resolution | Task |
|---|---|---|---|
| Exact-deck runtime coverage incomplete | 19 unverified cards, 15 unsupported effects, and 8 unsupported automatic abilities; 42 total | Reach zero unsupported capabilities and 100 reviewed `IMPLEMENTED` physical cards | #43 |
| Strategic combo model unresolved | `UNSUPPORTED_STRATEGIC_LOOP:DUALCASTER_TWINFLAME` | Add reviewed, fail-closed loop adjudication outside the rules kernel | #43 |
| Transcript approval not owner-anchored | 12 candidate files and digests exist, but the approval record is not owner-anchored | Owner explicitly reviews and approves or rejects each exact digest | #44 |
| Durable Phase B certification unavailable | Phase B verifier status is FAIL | Pass verifier, generate immutable artifact, and commit current durable certification | #45 |

## Quality Dashboard

**Latest evaluated workflow:** run `30836425410` / run number 535 — **SUCCESS**  
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
| Ruff formatting | PASS | 158 files already formatted |
| Ruff lint | PASS | All checks passed |
| Strict mypy | PASS | 64 source files, no issues |
| Standing Phase A verifier | PASS | 27 passed, 0 failed, 0 skipped, 0 xfailed |
| Full pytest suite | PASS | 230 passed |
| Manifest integrity | PASS | 34 frozen files and 18 required paths |
| Durable Phase A certification current | PASS | Certified covered-content digest verified |
| Phase B mapped tests | PASS | 133 passed, 0 failed, 0 skipped, 0 xfailed |
| Phase B requirement mapping | PASS | Complete |
| Strategic evaluator | PASS | Frozen evaluator and learning-plan identities verified |
| Pilot-lock gate | PASS | Verifier reports `pilot_lock: PASS` |
| Golden transcripts | **FAIL** | Approval record is not owner-anchored |
| Exact-deck capability coverage | **FAIL** | 42 unsupported/unverified capabilities |
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
- A green workflow does not establish Phase B acceptance when the candidate verifier reports FAIL.
- General test success does not convert unapproved transcript candidates into golden-transcript evidence.
- The Phase B verifier remains fail-closed until transcript approval, exact-deck coverage, and strategic-loop adjudication all pass on one exact commit.
- GitHub issue records are the detailed task records; this file is the executive mirror. They must change together.

## Next Recommended Tasks

1. Continue the next bounded runtime batch from the 42-item capability list under #43.
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
| Latest evaluated implementation head | `86404efb6de25f598bb6fd2a951deea963aa35b3` |
| Latest evaluated workflow | Run 535 / `30836425410` — SUCCESS |
| Phase B verifier | FAIL — transcripts, 42 capabilities, and one strategic blocker |
| Phase B artifact | ID `8865036430`; ZIP SHA-256 `bde56a1f41506a35198609e570bfcaf741458bf5870d6de54e46cbe13cd30002` |
| Durable Phase B certification | Not generated |
| Pilot authorization | Not present |
| Full-study authorization | Not present |
| Task synchronization | Standing item #47 |
| Repository protection | Open risk #46 |
