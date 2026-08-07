# Phase C Pilot Authorization Contract

## Status

**LOCKED — NOT AUTHORIZED TO EXECUTE**

This document defines the preparation, review, activation, execution, and audit process for the Phase C 500/200 pilot. Its presence, the existence of an executable runner, a green implementation commit, or a completed dry run does not authorize any simulation game.

Binding machine-readable files:

- `docs/spec/phase-c/PHASE_C_PILOT_CONFIG.json`
- `docs/spec/phase-c/PHASE_C_PILOT_APPROVAL.json`
- `.github/workflows/phase-c-pilot.yml`

The parent authorization task is issue #48. Technical runner completion is tracked in issue #50 and its focused child issues. The explicit owner decision is issue #51.

## Phase B handoff

Phase B was merged through PR #37 at merge commit:

`4d1df5a68744864906e337d8ded17d12d7724d37`

Phase C may add orchestration, policy execution, measurement, search, replay, artifact production, and authorization controls, but every covered Phase A or Phase B change invalidates the prior durable certification until an exact-head GitHub Actions candidate is generated, committed unmodified, and rechecked.

## Two-identity authorization model

Phase C separates the reviewed implementation identity from the later activation identity.

### 1. Reviewed implementation

Before any owner approval, one exact implementation commit must be green and reviewed. The owner package binds:

- full 40-character implementation commit Git object ID;
- full 40-character implementation tree Git object ID;
- SHA-256 of the locked pilot configuration at that implementation commit;
- SHA-256 of the reviewed Phase C workflow at that implementation commit;
- 500 standard and 200 exploratory games;
- 10 standard and 10 exploratory shards;
- exploratory production decision-layer depth of exactly 1;
- exact deterministic standard environment, paired subset/assignment, and exploratory search-seed digests;
- the confirmation-token SHA-256;
- exact-head Phase A and Phase B durable certifications and CI evidence.

The implementation configuration remains `execution_allowed: false` and `LOCKED_PENDING_OWNER_APPROVAL`.

### 2. Governance-only activation descendant

If the owner approves the implementation package, a later activation commit may change only the allowlisted governance files:

- `docs/spec/phase-c/PHASE_C_PILOT_CONFIG.json`
- `docs/spec/phase-c/PHASE_C_PILOT_APPROVAL.json`

The activation commit is **not** stored inside its own tree. Instead, the workflow receives the activation commit as an input and proves that it:

- is a descendant of the exact reviewed implementation commit;
- preserves the exact reviewed implementation tree for all non-governance content;
- changes no file outside the activation allowlist;
- preserves all non-authorization pilot configuration fields;
- preserves the implementation commit/tree, locked-config digest, workflow digest, counts, shard counts, production depth, and token digest in the approval record;
- changes the authorization fields only to the owner-approved values.

Any unexpected activation diff fails closed.

## Frozen pilot scope

The first possible execution authorization is limited to:

- exact 98-card library and Malcolm/Breeches command zone;
- three opponents;
- controlled player draws on Turn 1;
- league 7 / free 7 / 6 / 5 / 4 mulligan, never below four, refilling a kept sub-seven hand to seven;
- end after controlled Turn 10 or terminal state;
- checkpoints on Turns 5, 6, 8, and 10, with Turn 8 primary;
- opponent interaction, blocking, and opponent wins not modeled;
- Malcolm may connect and Glint-Horn may attack when legal;
- unknown Breeches cards excluded from deterministic resources;
- standard policy `anchor_balanced` with its frozen evaluator and learning-plan bindings;
- 500 standard games in 10 deterministic 50-game shards;
- 200 exploratory games in 10 deterministic 20-game shards;
- one audited production decision layer for the exploratory adapter, while preserving the existing upper bounds and reporting actual depth and nodes honestly;
- future information prohibited;
- post-result optimization and policy mutation prohibited;
- separate standard and exploratory reporting and aggregation.

This contract never authorizes the 20,000-standard / 5,000-exploratory full study. That requires a separate post-pilot decision.

## Technical build gate

Before owner review, the exact implementation commit must prove without executing the 500/200 pilot:

1. Exact clean-engine deck construction and the production league mulligan path.
2. Rules-owned Turn-1 draw, turn/phase/step progression, cleanup repetition, terminal short-circuiting, and controlled Turn-10 stop.
3. Full command recording and exact same-process plus fresh-process production replay.
4. Legal no-blocker combat through the shared ActionBroker and production executor, including attacker eligibility, opponent assignment, tapping, combat damage, commander damage, relevant trigger timing, and explicit optional-trigger choices.
5. Deterministic `LOOK_SELECT` and `TUTOR_THIRD_FROM_TOP` strategic choices from public candidates only, with exact counts, evaluator provenance, opaque handles, stable tie-breaking, and replay without rerunning policy.
6. Correct X-spell action enumeration with exact public X values and exact-X target counts.
7. Production combo-access tracking for all frozen packages, including early access, cumulative Turns 5/6/8/10, legal/payable/protected distinctions, actual first attempt, tutor exclusivity, attack restrictions, and false-positive rejection.
8. One-layer exploratory successor expansion through the same broker/executor and hidden-safe observation boundary, with deterministic diagnostics and actual depth/node reporting.
9. Atomic rollback that does not recursively copy replay history and restores failed state/replay exactly.
10. Cleanup-policy bookkeeping that consumes no engine identity or RNG and reproduces successor identities on replay.
11. Immutable per-game technical records, replay records, measurements, shard manifests, mode summaries, the primary paired Turn-8 aggregate, and the source-bound secondary earliest-access timing artifact with cross-file digest validation.
12. Exact deterministic 500/200 seed assignments with no duplicates, omissions, mixed modes, shard gaps, or environment/search RNG-domain mixing; exploratory environment seeds are exactly the frozen paired subset of standard environments.
13. Strict 40-character Git object-ID validation for commits/trees and SHA-256 validation for content digests, with identity-domain mixing rejected.
14. Certification provenance that proves each durable Phase A/B record belongs to its exact certified commit/tree and GitHub Actions run; hand-patched covered hashes cannot substitute for a CI-produced candidate.
15. The no-game dry run derives readiness from executable production checks and creates no pilot result.
16. The runner refuses before output creation while the configuration or owner approval remains locked.

## Required exact-head CI

The final implementation head must run:

- frozen dependency installation;
- identity, authority, clean-engine, legacy-isolation, formatting, lint, strict typing, and manifest gates;
- the exact-deck policy-driven Turn-10/fresh-replay smoke;
- the full test suite;
- Phase A verifier and CI-produced certification candidate;
- Phase B verifier using the exact Phase A candidate and its own CI-produced certification candidate;
- exact candidate validation;
- durable tracked certification-current gates;
- no-game Phase C dry run.

A technical CI run may intentionally remain red only because the tracked durable certification files still contain the prior records. The exact CI-produced Phase A and Phase B candidates from that run must then be committed **unmodified**, after which exact-head CI must pass again. No hand-authored certification digest update is authoritative.

## Required activation workflow controls

The eventual active workflow must:

- be `workflow_dispatch` only;
- require the exact confirmation token `AUTHORIZE_PHASE_C_500_STANDARD_200_EXPLORATORY`;
- run only from `main`;
- check out the exact activation commit and require a clean tree;
- verify implementation ancestry, implementation tree, governance-only activation diff, locked-config digest, workflow digest, counts, shards, depth, and owner approval;
- rerun identity, authority, clean-engine, legacy-isolation, formatting, lint, strict typing, the Turn-10 production smoke, full tests, manifest integrity, Phase A verifier/certification, Phase B verifier/certification, and the no-game dry run immediately before future execution;
- execute exactly the frozen 10 standard and 10 exploratory shards only after preflight passes;
- write no shard output before authorization validation succeeds;
- upload immutable shard artifacts;
- aggregate only after every exact shard succeeds;
- reject duplicate, missing, overlapping, mixed-mode, wrong-seed, wrong-identity, replay, measurement, summary, manifest, or digest evidence;
- build the secondary earliest-access timing artifact only from the already validated immutable shard set and primary aggregate;
- upload the primary aggregate and source-bound secondary timing artifact together;
- fail closed on every stop condition.

## Mandatory stop conditions

Execution must stop immediately for any:

- Phase A or Phase B verifier/certification failure;
- identity, source, Oracle, deck, rules, evaluator, policy, transcript, workflow, approval, or pilot-config drift;
- wrong implementation ancestry/tree or non-allowlisted activation diff;
- unsupported exact-deck capability or strategic-model blocker;
- legacy import/execution;
- hidden-future access;
- post-result policy optimization or policy mutation;
- game-count, shard, index, or seed mismatch;
- standard/exploratory mixing;
- replay, state-hash, technical-game, measurement, summary, shard-manifest, aggregate, or paired-timing source-binding mismatch;
- attempt to launch the full study.

## Owner authorization record

Until issue #51 is explicitly decided, the machine approval remains:

- status: `PENDING_OWNER_APPROVAL`;
- approved by: `null`;
- approved at: `null`;
- approval statement: `null`;
- implementation commit: `null`;
- implementation tree: `null`;
- locked pilot-config SHA-256: `null`;
- workflow SHA-256: `null`;
- `execution_allowed: false` in the pilot config.

The owner decision package must present the exact final values and explain the one-layer exploratory study definition. The assistant, Codex, CI, or repository automation may not self-approve those fields.

## Pilot audit and post-pilot review

If the owner later authorizes and the pilot executes, the audit must verify exact counts, shards, deterministic seeds, immutable cross-bound artifacts, replay success, actual exploratory depth/nodes, stable aggregation, no hidden-future or post-result optimization path, and exact implementation/activation identities.

The post-pilot verdict must separately identify rules/execution defects, measurement defects, policy limitations, deck findings, exploratory-only findings, and any condition that would block a full study. The 20,000/5,000 study remains locked until a separate post-pilot owner decision.

## Pre-registered metric language and paired exploratory comparison

The pilot measures **legal deterministic table-win access under a no-interaction opponent model**. Findings must be described as "table-win access by Turn N" or "combo access by Turn N" and must not be described as win rate, wins by Turn N, or real-table performance. Every results summary must include: *These figures measure combo assembly speed against opponents who take no actions. They are not win rates and do not predict performance against interactive opponents.*

The 200 exploratory executions are not an independent draw sample. They reuse a frozen 200-game subset of the 500 standard **environment seeds**, exactly 20 from each 50-game standard shard. STANDARD and EXPLORATORY runs for a pair initialize from the same environment seed. Exploratory search randomness is derived from a separate frozen search-seed namespace and never perturbs environment RNG.

The **primary exploratory comparison** is paired Turn-8 legal deterministic table-win access. The aggregate reports `BOTH_ACCESS`, `STANDARD_ONLY_ACCESS`, `EXPLORATORY_ONLY_ACCESS`, and `NEITHER_ACCESS`; the paired access-rate difference `(EXPLORATORY_ONLY - STANDARD_ONLY) / 200`; a two-sided exact McNemar test on discordant pairs; and a 95% deterministic paired-bootstrap percentile interval using 10,000 pre-registered resamples. The four raw cells and discordant-pair count must be reported alongside any p-value or interval. A null or inconclusive primary result is not evidence that the baseline policy is optimal.

The **secondary exploratory comparison** is earliest legal deterministic table-win access timing through Turn 10. It is descriptive and explicitly censored. For the same 200 pairs, report: both arms accessed by Turn 10, STANDARD-only access by Turn 10, EXPLORATORY-only access by Turn 10, and neither arm accessed by Turn 10. A numeric exploratory-minus-standard turn shift is calculated only for pairs where both arms have an observed access turn. Pairs with one or both arms censored are reported as counts and are excluded from the numeric turn-shift mean. No Turn-11 value or other synthetic access turn is imputed.

The pilot pre-commits **no numeric action threshold** for the secondary timing result, including no 0.25-turn threshold. Issue #52 must use the observed primary discordance, access differences, censored timing categories, paired both-access turn shifts, and actual exploratory depth/node evidence to determine whether and how a later 20,000/5,000 study should be sized or authorized. First-decision divergence, branch count, node count, and actual one-layer depth remain diagnostics and do not independently decide retention of the exploratory arm.
