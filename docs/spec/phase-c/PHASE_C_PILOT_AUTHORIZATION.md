# Phase C Pilot Authorization Contract

## Status

**LOCKED — NOT AUTHORIZED TO EXECUTE**

This document defines the process for preparing, reviewing, authorizing, running, and auditing the Phase C pilot. Its presence does not authorize any simulation game.

The binding machine-readable configuration is:

`docs/spec/phase-c/PHASE_C_PILOT_CONFIG.json`

The tracked authorization task is issue #48.

## Phase B handoff

Phase B was merged through PR #37 at merge commit:

`4d1df5a68744864906e337d8ded17d12d7724d37`

The durable Phase B certification covers content commit:

`e1d7796fec0171eff076e30c0df657f6c3329f51`

The Phase C runner must preserve the certified Phase B behavior. It may add run orchestration, dry-run validation, immutable artifact production, and Phase C audit controls, but it may not silently change the rules engine, exact deck, evaluator, policy bundle, transcript anchor, or Phase B evidence.

## Authorized scope after future approval

The first possible execution authorization is limited to:

- 500 standard games;
- 200 exploratory games;
- separately assigned seed namespaces;
- separate reporting and aggregation for the two modes;
- simulation through the end of controlled Turn 10;
- checkpoints on Turns 5, 6, 8, and 10;
- Turn 8 as the primary checkpoint.

No approval under this contract may authorize the 20,000 standard / 5,000 exploratory study. That study requires a separate decision after pilot review.

## Frozen game model

- Exact 98-card library.
- Commanders: Malcolm, Keen-Eyed Navigator and Breeches, Brazen Plunderer.
- Three opponents.
- Controlled player draws on Turn 1.
- League mulligan candidates: 7, free 7, 6, 5, and 4.
- Never mulligan below four.
- A kept hand below seven is refilled to seven.
- Rejected hands return to the library and are shuffled before the next candidate hand.
- Opponent interaction is not modeled.
- Blocking is not modeled.
- Malcolm may connect and Glint-Horn may attack when legal.
- Opponent wins are not modeled.
- Unknown Breeches cards do not become deterministic resources.
- Objective: maximize legal deterministic table-win access.

## Information and policy constraints

- Future information is prohibited.
- Post-result policy optimization is prohibited.
- Exploratory search must remain bounded and rules-validated.
- Standard and exploratory games must consume the same production legal-action broker.
- The exploratory result must be reported separately and must not retroactively alter the standard policy or pilot configuration.
- Legacy `mtg_sim` execution is prohibited.

## Phase C build gate

Before owner authorization, the Phase C implementation PR must prove all of the following without running the 500/200 pilot:

1. A clean-engine pilot command or runner exists.
2. The runner loads the exact frozen configuration.
3. Standard and exploratory seed assignments are deterministic and disjoint.
4. Requested counts cannot differ from 500 and 200 under the pilot authorization mode.
5. Standard and exploratory results cannot be combined before separate mode summaries are produced.
6. Every game receives an immutable manifest entry and replay transcript.
7. Hidden-future fields are rejected before execution.
8. Post-result optimization and policy mutation are rejected.
9. The runner refuses execution while `execution_allowed` is false.
10. The runner requires the exact confirmation token and a digest-bound owner approval record.
11. Phase A and Phase B gates pass immediately before any game execution.
12. The workflow cannot invoke the 20,000/5,000 study configuration.
13. Dry-run and negative tests pass in protected PR CI.

## Required workflow controls

The eventual active workflow must:

- use `workflow_dispatch` only;
- require the exact confirmation token `AUTHORIZE_PHASE_C_500_STANDARD_200_EXPLORATORY`;
- check out the exact authorized commit;
- require a clean tree;
- verify the source, Oracle, deck, rules, evaluator, transcript-approval, Phase A certification, Phase B certification, and pilot-config digests;
- run formatting, lint, strict typing, the full test suite, Phase A verification, and Phase B verification;
- run a no-game dry-run before the pilot;
- execute exactly 500 standard and 200 exploratory games once;
- upload immutable manifests, raw measurements, summaries, replays, logs, and digests;
- fail closed on any stop condition.

## Pilot audit and result review

After execution, the Phase C audit must verify:

- exact requested game counts;
- disjoint deterministic seed assignments;
- no duplicate or missing game indices;
- no standard/exploratory mixing;
- complete checkpoint and failure-label records;
- replay success for a predetermined sample from each mode;
- stable aggregation under the tested worker configurations;
- no hidden-future or post-result optimization path;
- artifact SHA-256 values and immutable manifest integrity;
- the exact commit and config digest used by every game.

The pilot verdict must distinguish:

- rules or execution defects;
- measurement defects;
- policy limitations;
- deck findings;
- exploratory-only findings;
- conditions that would block the full study.

## Mandatory stop conditions

Execution must stop immediately if any of the following occurs:

- Phase A or Phase B gate failure;
- source, Oracle, rules, deck, evaluator, policy, transcript, certification, or pilot-config drift;
- unsupported exact-deck capability;
- strategic-model blocker;
- legacy import or execution;
- hidden-future access;
- post-result policy optimization;
- game-count or seed mismatch;
- missing replay or manifest evidence;
- state-hash or aggregation mismatch;
- attempt to launch the full study.

## Owner authorization record

The following fields must remain blank until the implementation PR, exact workflow, pilot-config digest, tests, and dry-run evidence have been reviewed:

- Approved by: **PENDING**
- Approved at: **PENDING**
- Authorized implementation commit: **PENDING**
- Authorized pilot-config SHA-256: **PENDING**
- Authorized workflow SHA-256: **PENDING**
- Approval statement: **PENDING**

Only an explicit statement approving those exact values may change the machine configuration from locked to executable.

## Full-study decision

The 20,000 standard / 5,000 exploratory study remains locked after the pilot completes. A separate post-pilot decision must review the audit, failures, replay evidence, measurement quality, policy stability, and pilot findings before any full-study authorization is created.
