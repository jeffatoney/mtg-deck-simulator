# Phase B Project Status

> **Last verified:** 2026-08-03 18:06 PT  
> **Repository:** `jeffatoney/mtg-deck-simulator`  
> **Pull request:** #37 — draft  
> **Branch:** `engine/phase-b-full-deck-policy`  
> **Latest evaluated implementation head:** `1e6f87705473642f5bf27f35357cbf9f8633b881`

This file is the executive mirror of the issue-backed GitHub task records. Update the task record and this dashboard together whenever work is created, completed, blocked, reopened, reprioritized, or moved to human review. Completion requires exact verification evidence; implementation presence alone is not completion. Dashboard-only commits may follow the evaluated implementation head without changing the recorded engineering verdict.

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
| Phase A clean-engine foundation | **Current and passing** | Evaluated head `1e6f87705473642f5bf27f35357cbf9f8633b881`; Phase A verifier 27/27 PASS; durable certification-current gate PASS | PR #35 / #38 |
| Phase B Slice 1 — deck construction and coverage framework | **Verified complete** | Head `8f7727026b0fee20a7f1ff242f9ee2cb73f8a16b`; CI `30685183470` PASS | #39 |
| Phase B Slice 2 — policy configuration and shared broker | **Verified complete** | Head `6964f231e22b7a116e10a4c4e988552e8d861608`; CI `30693534094` PASS; 123 tests | #40 |
| Phase B Slice 3 framework — search, measurement, replay, manifests, verifier tooling | **Verified complete for framework scope** | Head `2b4a25514c440cd96a147a488e2a6ab13679f6e6`; CI `30696609808` PASS; 144 repository tests; 47 Phase B tests | #41 |
| Restore current exact-head CI | **Verified complete** | Head `0bb6606cfa57097c698ce820efb5d56175259c06`; workflow run `30804677571` SUCCESS | #42 |
| Complete exact-deck runtime coverage | **In progress** | 11 unsupported/unverified capabilities remain; one strategic model blocker remains | #43 |
| Approve and execute 12 mandatory transcripts | **Human review required** | 12 files and digests exist; approval record is not owner-anchored | #44 |
| Phase B verifier PASS and durable certification | **Blocked** | Requires #43 and #44 to close on one exact commit | #45 |
| Phase C pilot | Not authorized | Pilot-lock gate passes; no pilot authorization or result is claimed | — |

## Current Focus

1. Continue bounded Oracle-backed runtime batches against the 11 verified remaining capability blockers.
2. Prioritize shared primitives that clear both an unsupported effect and its corresponding unverified card.
3. Resolve `UNSUPPORTED_STRATEGIC_LOOP:DUALCASTER_TWINFLAME` without treating the combo as an assumed strategic truth.
4. Obtain explicit owner review of the 12 golden-transcript candidates and exact digests.
5. Rerun the Phase B verifier after each bounded implementation batch and after transcript approval.

## Completed Since the Prior User Update

### Runtime batch twenty-four — Chart a Course

- Implemented the shared `DRAW_THEN_DISCARD_UNLESS_ATTACKED` production primitive without card-name branching in the kernel.
- Used the retained exact-deck attack marker through cleanup to determine whether the controller must discard.
- Drew two cards, required an explicit strategic discard selection when the controller had not attacked, and skipped the discard after an attack marker.
- Added direct production-path tests for the no-attack discard path, the attacked no-discard path, and atomic fail-closed behavior when a required discard provider is absent.
- Added all three new nodes to `B-COVERAGE-001` and credited Chart a Course only after the direct tests and anti-overclaim regression passed.
- Applied the exact CI-produced Ruff artifact after run 600 identified formatting changes.
- Run 601 passed formatting, lint, strict mypy, the Phase A verifier, 255 repository tests, and manifest integrity, then exposed the expected stale durable Phase A certification after the covered-kernel change.
- Renewed durable Phase A certification from the exact run-601 CI candidate.
- Run 605 passed all standing workflow gates and produced the immutable Phase B result.
- Reduced exact-deck blockers from 13 to 11 and increased mapped Phase B tests from 155 to 158.
- Updated issues #43, #44, and #45 with the same exact evidence. No task was marked complete.

## Current Blockers

| Blocker | Current evidence | Required resolution | Task |
|---|---|---|---|
| Exact-deck runtime coverage incomplete | 5 unverified cards, 4 unsupported effects, and 2 unsupported automatic abilities; 11 total | Reach zero unsupported capabilities and 100 reviewed `IMPLEMENTED` physical cards | #43 |
| Strategic combo model unresolved | `UNSUPPORTED_STRATEGIC_LOOP:DUALCASTER_TWINFLAME` | Add reviewed, fail-closed loop adjudication outside the rules kernel | #43 |
| Transcript approval not owner-anchored | 12 candidate files and digests exist, but the approval record is not owner-anchored | Owner explicitly reviews and approves or rejects each exact digest | #44 |
| Durable Phase B certification unavailable | Phase B verifier status is FAIL | Pass verifier, generate immutable artifact, and commit current durable certification | #45 |

### Remaining exact-deck capability families

- Unsupported automatic abilities: Niv-Mizzet, the Firemind; Path of Ancestry.
- Unsupported effects: `DEMOLITION_FIELD`, `AMASS_AND_HEXPROOF`, `ADD_COMMANDER_COLOR_AND_MARK`, and `PRISMARI_COMMAND`.
- Unverified cards: Demolition Field, Lazotep Plating, Niv-Mizzet, the Firemind, Path of Ancestry, and Prismari Command.

## Quality Dashboard

**Latest evaluated workflow:** run `30867585001` / run number 605 — **SUCCESS**  
**Phase B candidate verdict inside that workflow:** **FAIL**

| Gate | Evaluated-head status | Evidence |
|---|---|---|
| Dependency installation | PASS | Frozen environment installed |
| Frozen identity lock | PASS | Approved SHA-256 matched |
| Phase A authority classification | PASS | Clean production-path authority checks passed |
| Phase B authority and coverage checks | PASS | Required authority mappings and complete-deck coverage checks executed |
| Phase B evaluator and learning boundary | PASS | 77 classified effect kinds; 14 policy bundles; separation rules passed |
| Clean engine and support-package boundary | PASS | 66 Python files scanned; no forbidden findings |
| Legacy package import prohibition | PASS | `mtg_sim` not importable |
| Ruff formatting | PASS | 170 files already formatted |
| Ruff lint | PASS | All checks passed |
| Strict mypy | PASS | 66 source files, no issues |
| Standing Phase A verifier | PASS | 27 passed, 0 failed, 0 skipped, 0 xfailed |
| Full pytest suite | PASS | 255 passed |
| Manifest integrity | PASS | 34 frozen files and 18 required paths verified |
| Durable Phase A certification current | PASS | CI-produced run-601 record matches covered content |
| Phase B mapped tests | PASS | 158 passed, 0 failed, 0 skipped, 0 xfailed |
| Phase B requirement mapping | PASS | Complete |
| Strategic evaluator | PASS | Frozen evaluator and learning-plan identities verified |
| Pilot-lock gate | PASS | Verifier reports `pilot_lock: PASS` |
| Golden transcripts | **FAIL** | Approval record is not owner-anchored; 0 of 12 approved |
| Exact-deck capability coverage | **FAIL** | 11 unsupported/unverified capabilities |
| Strategic model | **FAIL** | One unresolved Dualcaster/Twinflame loop |
| Durable Phase B certification | BLOCKED | Phase B candidate is not PASS |

## Evidence Record

- Evaluated implementation head: `1e6f87705473642f5bf27f35357cbf9f8633b881`.
- CI workflow: run 605 / `30867585001` — SUCCESS.
- Phase B result artifact: `phase-b-result-1e6f87705473642f5bf27f35357cbf9f8633b881`.
- Artifact ID: `8876698014`.
- Artifact ZIP SHA-256: `416dac3d3433b71f2d43d48ea2ffbf9bcda461baaa9bcc4588c689a5b8387798`.
- Phase B result status: FAIL.
- Phase B certification candidate: not generated.
- Durable Phase B certification: not available.

## Risks

- **Human approval dependency:** automation cannot approve transcript content or digests on the owner's behalf. See #44.
- **Candidate-versus-golden confusion:** the 12 transcript files are candidates only; they do not count as approved evidence until the owner anchor exists and the gate executes them.
- **Large change surface:** the Phase B branch has a large commit and file footprint, increasing regression and review risk.
- **Repository protection:** branch protection or a repository ruleset is required but not currently verified as enabled. See #46.
- **Project integration limitation:** the available GitHub connection maintains issue-backed task records and repository files but cannot directly mutate GitHub Projects fields or board placement. See #47.

## Decisions Maintained

- The owner-approved single-owner exception remains in force; it does not permit automation to approve golden transcripts on the owner's behalf.
- Coverage credit is granted only after direct production-path execution tests exist and the anti-overclaim regression is updated to the same reviewed evidence set.
- Conditional discard effects require an explicit player-anchored selection when a discard is required; missing required decisions fail closed and atomically.
- A green workflow does not establish Phase B acceptance when the candidate verifier reports FAIL.
- General test success does not convert unapproved transcript candidates into golden-transcript evidence.
- The Phase B verifier remains fail-closed until transcript approval, exact-deck coverage, and strategic-loop adjudication all pass on one exact commit.
- GitHub issue records are the detailed task records; this file is the executive mirror. They must change together.

## Next Recommended Tasks

1. Continue the next bounded runtime batch from the 11-item capability list under #43.
2. Implement a shared primitive for one unsupported effect family with its matching unverified card, then add direct exact-deck tests before crediting it.
3. Resolve the Dualcaster/Twinflame strategic-loop blocker.
4. Record approval or requested correction individually for each transcript ID and digest in #44.
5. Close #45 only after golden transcripts report PASS, capability count is zero, strategic blockers are zero, and durable Phase B certification is current.
6. Enable and verify repository protection under #46.

## Repo Health

| Item | Current state |
|---|---|
| Repository | `jeffatoney/mtg-deck-simulator` |
| Active PR | #37 — `Phase B: migrate full deck and policy framework` |
| PR state | Open, draft, mergeable, and unmerged at last metadata check |
| Base | `main` at `b5743b54fa26e3e20c175fddb6401b390c828b8c` |
| Latest evaluated implementation head | `1e6f87705473642f5bf27f35357cbf9f8633b881` |
| Latest evaluated workflow | Run 605 / `30867585001` — SUCCESS |
| Phase B verifier | FAIL — transcripts, 11 capabilities, and one strategic blocker |
| Phase B artifact | ID `8876698014`; ZIP SHA-256 `416dac3d3433b71f2d43d48ea2ffbf9bcda461baaa9bcc4588c689a5b8387798` |
| Durable Phase B certification | Not generated |
| Pilot authorization | Not present |
| Full-study authorization | Not present |
| Task synchronization | Issues #43–#45 and this dashboard synchronized; #44 remains open for human review |
| Repository protection | Open risk #46 |
