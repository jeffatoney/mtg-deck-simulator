# Stage 3 final PR #99 disposition supplement

Status: TECHNICAL_IMPLEMENTATION_AND_CERTIFICATION_COMPLETE_FINAL_CODEX_REVIEW_PENDING

Technical implementation is complete. Final Phase A and Phase B certifications are current. Promotion-head exact CI and auxiliary workflows are green. This documentation refresh records the final resource-execution provenance repair that followed the ROOT-A authority-boundary completion. This does not declare PR #104 Ready for Review, merge-ready, or merged. A fresh Codex review of the resulting exact final docs head remains required before closing review threads or a Ready-for-Review transition.

This document supplements, and does not rewrite, `INVENTORY.json`.

`INVENTORY.json` is the immutable first-substantive Stage 3 snapshot. Its original classifications and `PENDING_*` / `OWNER_DECISION_PENDING` statuses remain historical evidence of what was known before extraction and before the owner decision. Final outcomes are recorded here instead of mutating that snapshot.

## Frozen prototype and Stage 3 base

- Stage 3 base `main`: `8b69b0aa3c3896c26f9c0823fd102dfa9a87f41f`.
- Frozen prototype PR: #99, `Phase C: directed exploratory V2 redesign`.
- PR #99 base: `150671a8e7a78e5fa14b6b3aca2308f6af647df3`.
- PR #99 head: `4c9a404fc9308ecc281711b4b9b48eef6dfd441b`.
- PR #99 commit count: 34.
- PR #99 changed-file count: 37.
- Canonical committed PR #99 patch: `docs/audit/stage3-pr99-disposition/evidence/PR99_PROTOTYPE_FULL_INDEX.patch`.
- Canonical PR #99 patch SHA-256: `31dbf0dad6c8bc497ea8dcb2bd40694d28e9b90cd6b25cf1b24a4cb5aae88b16`.
- Canonical PR #99 patch size: 297677 bytes.
- PR #99 remains open, draft, unmerged, and unmodified.

## Durable prototype bytes correction

Final Codex review found that the prior digest-and-manifest-only preservation claim was insufficient under the repository evidence policy. The exact 297,677-byte canonical PR #99 patch is now committed at `docs/audit/stage3-pr99-disposition/evidence/PR99_PROTOTYPE_FULL_INDEX.patch`; its SHA-256 `31dbf0dad6c8bc497ea8dcb2bd40694d28e9b90cd6b25cf1b24a4cb5aae88b16` and size match the original preservation measurement. `docs/audit/EVIDENCE_INDEX.json` indexes the actual patch bytes.

The Stage 3 preservation workflow continues to verify live frozen PR #99 metadata and now reconstructs the canonical patch and byte-compares it with the committed durable artifact. The historical GitHub Actions measurement remains corroborating ephemeral evidence, not the sole preservation source. This correction changes no production, policy, test, certification, pilot, or study behavior. A new exact-head CI run and final reviewer pass remain required; final review is not complete.

## Final component dispositions

| Component | Original classification / status in `INVENTORY.json` | Final extraction status | Current destination / implementation | Evidence and tests | Certification effect | Owner decision |
| --- | --- | --- | --- | --- | --- | --- |
| Controlled counter-payment outcome model | `REIMPLEMENT_BEHIND_NEW_BOUNDARY` / `PENDING_REIMPLEMENTATION` for PR #99 ADR 0017 | `REIMPLEMENTED_BEHIND_NEW_BOUNDARY` | `COUNTER_PAYMENT_OWNER_DECISION.md`; `CounterPaymentRequest`, `CounterPaymentSelection`, and rules-side `PAY` / `DECLINE` legality | Stage 3 counter-payment acceptance suite proves both legal modeled outcomes, infeasible PAY exclusion, replay legality, explicit-controller choice, and opponent fail-closed behavior | Phase A and Phase B covered content changed and were re-certified | Required for the production preference only; resolved by the 2026-08-22 owner authorization |
| Counter-unless-pay runtime | `REIMPLEMENT_BEHIND_NEW_BOUNDARY` / `PENDING_REIMPLEMENTATION` for PR #99 runtime plumbing | `REIMPLEMENTED_BEHIND_NEW_BOUNDARY` | `src/mtg_kernel/phase_b_runtime_effects_interaction.py` now derives legal outcomes from the shared solver, exposes only semantic request facts, executes PAY after selection, records durable semantic evidence, and counters to the rules-correct destination on DECLINE | `tests/phase_c/test_stage3_counter_payment_boundary.py`; updated Phase B runtime tests; fresh replay equality | Phase A and Phase B renewed | No new rules choice was invented; the rules outcome model was already binding |
| Semantic strategic request, selection, and replay | `REIMPLEMENT_BEHIND_NEW_BOUNDARY` / `PENDING_REIMPLEMENTATION` for PR #99 strategic-choice shape | `REIMPLEMENTED_BEHIND_NEW_BOUNDARY` | `src/mtg_kernel/strategic_choices.py`; target semantics carry identity, mana value, card types, and effect kinds but no request-scoped target handle; replay validates recorded semantic owner, effect, target identity, payment amount, destination, and selected legal outcome without rerunning live policy | Tests reject solver-inconsistent legal outcome sets, illegal recorded PAY, target/destination mismatches, and verify fresh replay equality | Phase A and Phase B renewed | None beyond the resolved production preference |
| Rules-private resource execution binding | PR #99 full-executor payment planner was `SUPERSEDED` / `NOT_EXTRACTED` | `NEW_ARCHITECTURE_NEUTRAL_IMPLEMENTATION`; PR #99 planner remains `NOT_EXTRACTED` | `src/mtg_kernel/resource_execution.py` binds an already-proven canonical semantic allocation to current execution objects only after PAY is selected. It reruns the same shared solver to reject stale requests and fails closed if semantic allocation cannot bind. Object IDs and ability IDs remain rules-private | Stage 3 tests prove feasibility does not activate executor state before policy selection, semantic solver allocations bind to actual mana ability execution, floating mana works, and replay remains exact | Phase A and Phase B renewed | None. This is mechanical execution behind PR #101 resource authority, not a new feasibility model |
| Owner-authorized Modified A production criterion | PR #99 `src/mtg_policy/choices.py` was `PRESERVE_AS_PROTOTYPE_EVIDENCE`; the canonical PAY-versus-DECLINE criterion was `OWNER_DECISION_PENDING` | `OWNER_DECISION_RESOLVED_AND_REIMPLEMENTED`; PR #99 heuristic remains `NOT_EXTRACTED` | `src/mtg_policy/choices.py` implements `CONTEXTUAL_TARGET_VALUE_VS_PAYMENT_MANA_V1`: PAY iff `contextual_target_value > actual_required_payment × existing_mana_weight`; ties DECLINE. It is restricted to `contextual_combo_v1` and frozen `mana = 8`, and fails closed on evaluator or weight drift | Characterization tests cover below-threshold draw and interaction, above-threshold tutor and combo-engine targets, contextual combo progress, exact tie DECLINE, and Syncopate X values | Phase B renewed; Phase A also changed through the rules/runtime boundary | Resolved by `COUNTER_PAYMENT_OWNER_DECISION.md` on 2026-08-22 |
| Durable semantic evidence | PR #99 durable handle/plan-centered evidence was not acceptable behind PR #100 / PR #101 | `REIMPLEMENTED_SEMANTICALLY` | `counter-payment-choice-v4` records choice/effect kind, decision owner, public target semantics, actual payment, legal alternatives, shared solver result, destination, contextual evaluation, frozen mana valuation, zero DECLINE approximation, outcome, reason code, evaluator identity/digest, decision source, and resolution timing. No target object ID or mana-ability plan is persisted as policy identity | Acceptance and Phase B regression tests assert semantic fields, absence of durable target handle/object ID and executor payment plan, fresh policy recomputation, and replay | Phase A and Phase B renewed | The zero DECLINE incremental value is explicitly part of the authorized Stage 3 baseline, not a general strategic claim |
| Stage 3 and Phase B acceptance/regression tests | Candidate requirements in the frozen inventory | `PORTED_AS_ACCEPTANCE_TESTS_AND_UPDATED_REGRESSIONS` | `tests/phase_c/test_stage3_counter_payment_boundary.py`; `tests/phase_b/test_runtime_batch_twenty_one.py` | Covers rules feasibility, PAY/DECLINE, explicit choice, opponent fail-closed, no pre-selection executor activation, floating resources, rules-private execution binding, durable evidence, fresh recomputation, tie behavior, evaluator/weight freeze, Syncopate X, exile destination, and replay | Tests participate in current CI and certification gates | No outstanding owner decision |
| PR #99 full-executor deep-copy resolution mana planner | `SUPERSEDED` / `NOT_EXTRACTED` | `NOT_EXTRACTED` | None. Current authority remains `mtg_kernel.resource_payment` and `mtg_kernel.resource_sources`; Stage 3 added only the post-selection execution binding described above | Guarded by code review, boundary tests, and certification checks | None from prototype bytes | None |
| PR #99 one-deviation continuation / full-executor candidate projection | `PRESERVE_AS_PROTOTYPE_EVIDENCE` / `NOT_EXTRACTED` | `NOT_EXTRACTED` | Frozen PR #99 only | Stage 2 bridge benchmark remains the non-pilot regression tripwire; no projection code was imported | None | Future architecture only |
| PR #99 V2 scoring, projection, arms, and evaluator configs | `PRESERVE_AS_PROTOTYPE_EVIDENCE` / `NOT_EXTRACTED` | `NOT_EXTRACTED` | Frozen PR #99 only, including `exploratory_aggressive_v2`, `exploratory_alt_package_v2`, `exploratory_interaction_discovery_v2`, and `exploratory_v2_scoring` | No pilot or study execution; current policy/evaluator checks remain authoritative | None | No Stage 3 authorization to import these values |
| PR #99 V2 diagnostic / handle-centered decision evidence | `SUPERSEDED`, `PRESERVE_AS_PROTOTYPE_EVIDENCE`, or `REIMPLEMENT_BEHIND_NEW_BOUNDARY` depending on component; evidence schema explicitly `DEFERRED_FUTURE_BOUNDARY` | `NOT_EXTRACTED_OR_DEFERRED` | No Stage 3 production exploratory schema. Any future evidence identity must use PR #100 semantic/public identity and PR #101 resource outputs | Current repository evidence and information-boundary checks remain authoritative | None while deferred | Future owner/architecture work only |
| PR #99 branch-local Phase A/B certifications | `SUPERSEDED` / `NOT_EXTRACTED` | `NOT_EXTRACTED` | Never copied. Current durable Phase A/B records were regenerated from the Stage 3 source-behavior head and promoted from CI-produced artifacts | Exact byte and hash provenance recorded below | Current durable certifications renewed from post-PR #101 Stage 3 code | None |

## Authorized production baseline

The owner-authorized Modified A criterion is intentionally narrow:

```text
PAY iff contextual_target_value > actual_required_payment × existing_mana_weight
otherwise DECLINE
```

Binding details:

- Evaluator: `contextual_combo_v1` only.
- Existing frozen mana weight: `8` only.
- Actual rules-required payment is used, including Syncopate cast-time X.
- Comparison is strict; ties select `DECLINE`.
- Rules feasibility is supplied only by the shared PR #101 solver.
- `DECLINE` incremental value is the explicit Stage 3 approximation `0`.
- Counter destination is recorded as semantic evidence but is not given a new strategic score.
- The chooser fails closed if the evaluator ID or frozen mana weight changes.
- Replay consumes the recorded semantic outcome; fresh policy recomputation must reproduce it.
- Symmetric complete-outcome comparison is an intended successor and is not implemented in Stage 3.

No PR #99 `PUBLIC_TARGET_VALUE_VS_MANA_RETENTION_V1` scoring values or other V2 policy values were copied to create this criterion.

## Resource boundary outcome

The frozen PR #99 deep-copy/full-executor resource planner was not salvaged. It remains superseded by the PR #101 resource authority.

Stage 3 instead added `src/mtg_kernel/resource_execution.py` as a rules-private adapter with a narrower responsibility:

1. Accept a `ResourcePaymentResult` already produced by the authoritative shared solver.
2. Immediately rerun that same shared solver before execution to reject stale semantic allocations.
3. Bind canonical semantic source allocations to current rules execution objects only after the selected outcome requires payment.
4. Consume or reserve provenance that a source has already produced before activating that source again, and activate additional sources only for a remaining deficit.
5. Execute actual mana abilities during resolution without creating a new priority opportunity.
6. Spend the exact allocation chosen by the shared solver.
7. Fail closed if current execution state cannot bind the canonical semantic allocation.

This is execution of an already-proven allocation, not a second feasibility solver, planner, or resource valuation model.

## Durable evidence outcome

The production decision record is semantic and replayable. It deliberately excludes PR #99's request-scoped strategic target handles and full executor payment plans from durable policy identity.

Representative recorded fields include:

- `schema_version = counter-payment-choice-v4`.
- `choice_kind = COUNTER_PAYMENT`.
- `effect_kind` and `decision_owner`.
- Public target identity, mana value, card types, and effect kinds.
- `actual_required_payment`.
- `legal_modeled_alternatives` and `pay_legally_available`.
- Shared `resource_payment` evidence.
- `counter_destination`.
- Contextual target evaluation and evaluator ID/digest.
- Frozen mana-weight and payment-mana valuation in deterministic microunits.
- `decline_incremental_value_microunits = 0` for the authorized baseline.
- Selected semantic outcome and stable reason code.
- Decision source and `chosen_at = RESOLUTION`.

Fresh replay validates the recorded semantic outcome without invoking live policy. Fresh live policy recomputation from the same public semantic request is separately characterized to reproduce the selection.

## Historical CR6–CR9 source/test candidate

The following CR6–CR9 source/test candidate, CI #1304 candidates, promotion commit `654054adbe4eedd0383309b92beebb38977187e8`, and CI #1305 validation remain legitimate historical provenance. They are superseded as current Stage 3 authority by the consolidated-repair chain recorded below.

The historical CR6–CR9 source/test candidate was:

- Commit: `3fdb10c8c8d9ccfccfe534a59e86aaa3ec5627ba`.
- Tree: `f74b629bac7c17bdad83d68e71e19da9753eec8a`.
- Parent: `76c30a666d12791daab73f46955c3e1ad2503f81`.
- Subject: `Fix Stage 3 counter-payment review findings`.
- Commit scope: exactly 12 changed paths, 885 insertions, and 55 deletions.
- Preserved V3 patch: `/home/jeffa/stage3-pr104-cr7-cr9-working-v3.patch`, SHA-256 `eae81653c878329b7274ed7d57cc6d49bfd8a422d8022699e456096636935c67`, 53740 bytes.

### CR6 — stack spell effect relevance

CR6 corrected the P1 stack-spell effect-relevance defect. Protected-spell contextual valuation retains selected spell effects, excludes unselected spell modes and hand-only/non-spell capabilities such as Muddle the Mixture's Transmute, and retains legitimate post-resolution abilities of permanent spells. The runtime and valuation paths share the same hand-activation classification and use the kernel `PERMANENT_TYPES` authority. CR6 remained sensitive in the later independent audits.

Muddle the Mixture is the exact regression. Before CR6, its protected-spell effect kinds incorrectly included `COUNTER_IF` and `TRANSMUTE`, producing contextual value 27 and selecting `PAY` against Syncopate {3}, whose payment value was 24. After CR6, only `COUNTER_IF` contributes, contextual value is 9, and the correct result is `DECLINE`. The owner-authorized criterion did not change: `PAY` iff contextual target value is strictly greater than actual required payment times mana weight 8; ties remain `DECLINE`, and the evaluator remains `contextual_combo_v1`.

### CR7 — conditional resolution components

Un-kicked Into the Roil retains its printed composite `BOUNCE_AND_KICKER_DRAW` effect kind while the normalized resolution model marks the `DRAW` component inactive. Its un-kicked target value is 9, so a tax of {2}, valued at 16, produces `DECLINE`. When kicked, its target value is 21 and the result is `PAY` when payment is legally feasible.

CR7 did not change evaluator weights or configuration. Runtime resolution and protected-spell valuation consume the same normalized kicked rules fact. The normalized authority is the existing `current_characteristics["kicked"]` boolean. Truthy raw cast inputs accepted by the existing cast API normalize consistently instead of producing contradictory payment, resolution, or valuation results.

### CR8 — already-floating marked mana provenance

Public semantic resource classes distinguish ordinary and marked floating mana, including forms such as `floating:U` and `floating:U:marked`. Marker event IDs remain rules-private. The shared PR #101 solver remains the sole feasibility and canonical-allocation authority; execution binds exact marked provenance only after selection. No marker event ID crosses into policy evidence.

Canonical mixed, marked, activation-cost, and malformed-ledger invariants pass. CR8 adds no duplicate solver and does not expose execution identity through the policy boundary.

### CR9 — malformed explicit counter-payment choice

CR9 distinguishes absence of `counter_payment` from malformed presence. A malformed present value fails closed before provider fallback, the provider is not called, and mutation rolls back atomically. An absent key still invokes the policy/provider path. Valid explicit `PAY` and `DECLINE` choices remain supported.

CR6–CR9 correct the bounded Stage 3 implementation and evidence boundary. They do not establish or claim any new general strategic optimality.

## Independent final local V3 audit

The final independent local V3 audit was performed after the earlier V1 and V2 blockers. Its final classification was `READY_TO_COMMIT`.

- Start: `2026-08-31 23:46:12 PDT`.
- Finish: `2026-09-01 01:06:10 PDT`.
- Duration: 1 hour 19 minutes 58 seconds.
- Independent full `tests/phase_c`: 150 passed, 0 failed, 4787.63 seconds (`1:19:47`).
- Independent `tests/kernel`: 49 passed.
- Independent `tests/phase_b`: 239 passed.
- Phase A golden transcripts: 5 PASS.
- Phase B golden transcripts: 12 PASS.
- Ruff formatting, lint, mypy, clean-engine boundary, and authority gates: PASS.
- Witness expected and actual: `4c8cdf227e7f2ad924eccc6ef1ec903e447887915546a0512cd11e04af4d7845`.
- Governed policy, pilot, and configuration bytes remained unchanged.
- The pilot remained locked.

This was an independent local code audit, not a GitHub-native audit.

## Source-head CI #1304

GitHub Actions run `33492826686` (displayed CI #1304) ran on exact source head `3fdb10c8c8d9ccfccfe534a59e86aaa3ec5627ba`, tree `f74b629bac7c17bdad83d68e71e19da9753eec8a`. It started at `2026-09-01T09:33:18Z` and completed at `2026-09-01T10:45:09Z`, a duration of 1 hour 11 minutes 51 seconds.

The overall workflow conclusion was `FAILURE`, but every substantive technical gate passed:

- Frozen identity lock.
- Repository evidence integrity.
- Phase A authority.
- Phase B evaluator/learning boundary.
- Public policy information boundary.
- STANDARD noninterference.
- Clean-engine boundary.
- Legacy isolation.
- Formatting.
- Lint.
- Mypy.
- Phase C production/replay smoke.
- Phase A verifier.
- Phase A candidate build and validation.
- Full Tests.
- Manifest integrity.
- Phase B verifier.
- Phase B candidate build and validation.
- Phase C no-game dry run.

The only failing step was `Durable Phase A certification is current`, because the prior durable certification was expectedly stale after the source/test changes. Durable Phase B currentness was skipped after that failure. Both new candidates were nevertheless built, validated, and uploaded successfully.

Source-head auxiliary workflows also passed:

- Stage 2 Bridge STANDARD Benchmark #89: `SUCCESS`.
- Stage 3 PR99 Prototype Preservation #43: `SUCCESS`.

## Exact certification candidates

The Phase A candidate was:

- Artifact: `phase-a-certification-candidate-3fdb10c8c8d9ccfccfe534a59e86aaa3ec5627ba`.
- Artifact ID: `9796896951`.
- Exact promoted `CERTIFICATION.json` SHA-256: `b67769c81c5e23cee6114db1f4efbe6d97fab0a739242897bfc5e82d63e23e78`.
- Bytes: 5138.
- Certified content commit: `3fdb10c8c8d9ccfccfe534a59e86aaa3ec5627ba`.
- Certified repository tree: `f74b629bac7c17bdad83d68e71e19da9753eec8a`.
- Counts: 33 pass, 0 fail, 0 skip, 0 xfail.
- `clean_tree_before_run = true`, `legacy_evidence_used = false`, and `pilot_lock = PASS`.

The Phase B candidate was:

- Artifact: `phase-b-certification-candidate-3fdb10c8c8d9ccfccfe534a59e86aaa3ec5627ba`.
- Artifact ID: `9796895996`.
- Exact promoted `CERTIFICATION.json` SHA-256: `1431ed414e4e3889a8bed809f922ae776548709fa7dd12ba495b12a25083ea8e`.
- Bytes: 6563.
- Certified content commit: `3fdb10c8c8d9ccfccfe534a59e86aaa3ec5627ba`.
- Certified repository tree: `f74b629bac7c17bdad83d68e71e19da9753eec8a`.
- Counts: 239 pass, 0 fail, 0 skip, 0 xfail.
- Golden transcripts: 12 PASS.
- `clean_tree_before_run = true`, `legacy_evidence_used = false`, and `pilot_lock = PASS`.

Both candidates record `github_run_id = 33492826686`, `verification_environment = GITHUB_ACTIONS`, `status = PASS`, and the exact source/test candidate and tree above.

## Certification promotion

The two exact CI-produced candidates were promoted byte-for-byte, without local regeneration or manual transcription, in:

- Commit: `654054adbe4eedd0383309b92beebb38977187e8`.
- Tree: `85c877e55d7f61ab366510dfbd5e1db376cb4b5f`.
- Parent: `3fdb10c8c8d9ccfccfe534a59e86aaa3ec5627ba`.
- Subject: `Renew Stage 3 Phase A and B certifications`.
- Changed paths: `docs/audit/phase-a-certification/CERTIFICATION.json` and `docs/audit/phase-b-certification/CERTIFICATION.json`.
- Aggregate diff: 2 files changed, 19 insertions, and 19 deletions.

The certifications intentionally certify source/test candidate `3fdb10c8c8d9ccfccfe534a59e86aaa3ec5627ba`, not the later promotion commit.

## Promotion-head validation

Promotion-head GitHub Actions run `33530919978` (displayed CI #1305) ran on head `654054adbe4eedd0383309b92beebb38977187e8`, tree `85c877e55d7f61ab366510dfbd5e1db376cb4b5f`. It started at `2026-09-01T16:17:36Z` and completed at `2026-09-01T18:01:32Z`, a duration of 1 hour 43 minutes 56 seconds.

The workflow conclusion was `SUCCESS`. All Stage 3-relevant steps passed, including:

- Full Tests.
- Phase A verifier.
- Phase B verifier.
- Phase A candidate validation.
- Phase B candidate validation.
- Phase C no-game dry run.
- Durable Phase A certification is current.
- Durable Phase B certification is current.

Auxiliary exact-head workflows also passed:

- Stage 2 Bridge STANDARD Benchmark #90: `SUCCESS`.
- Stage 3 PR99 Prototype Preservation #44: `SUCCESS`.

The prior CR6-only source/certification chain remains legitimate historical provenance. The CR7–CR9 correction source candidate, CI #1304 candidates, promotion commit, and CI #1305 validation remain legitimate historical provenance and are themselves superseded as current authority by the consolidated-repair chain below.

Those SHA-256 values remain durable verification anchors for the historical CR6–CR9 promoted bytes. They are not the current durable certifications.

Certification candidate artifact bytes, durable SHA-256 anchors, and Git repository object identity are distinct provenance layers. Repository object identity does not replace the SHA-256 anchors or imply that artifact retention is permanent.

The CR6–CR9 durable records were the current post-PR #101 Stage 3 certifications until the consolidated repair renewed both Phase A and Phase B from later CI-produced candidates. They are not the obsolete certification files contained on frozen PR #99.

## Historical consolidated-repair authority

The following consolidated-repair chain was the current Stage 3 source, certification, and validation authority through R7 documentation head `686961ee06d7db7a679442a339e754a637589698` and CI #1312–#1314. It remains legitimate historical provenance. It is superseded as CURRENT authority by the final ROOT-A authority completion recorded below. Historical CR6–CR9 and earlier Stage 3 candidates also remain provenance only. Do not treat this section as though the earlier consolidated repair never happened.

### Independent consolidated audit

An independent consolidated Stage 3 audit pinned source `f84ff8a101e59be1742d4ffaf115f9f9e8cd8971`, tree `8726ab563960c65f4a0bde4a138ab780b715519d`, and completed Areas A–F.

Important outcomes:

- ROOT-A: explicit strategic decision-ownership authority was missing. Provider use compared identities such as `action.actor_id` instead of a bound controlled player, so a controlled-player provider could fail when an opponent cast a counter and could choose for an opponent in the inverse relationship.
- ROOT-B: pain-land / resource legality suppressed `ADD_CHOSEN_MANA_AND_DAMAGE_SELF` when life was at or below the damage amount. Damage from that mana ability is an effect, not a life-payment cost.
- ROOT-C: the resource-payment search memoized a remaining-payment problem without distinguishing production choices of a costed multi-mode source. Cascade Bluffs therefore could not reach every individually legal production mode.
- ROOT-G: existing exact-mana regressions did not prove that the authorized allocation was the allocation consumed when multiple legal units existed.
- ROOT-D: disposable probes could alias live replay / transcript structures; constructor synchronization could write through that alias even when ordinary state-equality tests passed.
- ROOT-E: inactive-component valuation subtracts by feature rather than component identity. That limitation is currently unreachable because the conditional-resolution registry has one entry.
- ROOT-F: this disposition document was stale relative to the later implementation chain.

Area C used an independent oracle of 5,635 resource cases. All 29 failures collapsed to the costed multi-mode search defect.

### Consolidated repair commits

Commit 1 recorded ROOT-A ownership and ROOT-D isolation:

- Commit: `342155019e7c404c6e006e0272e5296ea17c5c9f`.
- Tree: `5ac377693d933e6b41f9ce5a9d99d482cf5d6b2e`.
- Subject: `Fix Stage 3 strategic ownership and probe isolation`.
- Outcome: a frozen `StrategicChoiceBinding` states which player the provider may decide for. Implicit provider use is permitted only when the rules decision owner equals that bound player; otherwise the existing explicit fail-closed opponent path is required. Probes receive independent replay/transcript copies, and controlled-player binding plus `opponent_mana_profile` are threaded through required clone, probe, and replay paths. Ownership role-matrix and probe/transcript isolation regressions were added.

Commit 2 recorded ROOT-B, ROOT-C, ROOT-G, and the ROOT-E PATH B bound:

- Commit: `30914ee584490ebacd0611721e33409f62cdb416`.
- Tree: `15072fedd1b7f5fa6c03d698f420f892d87b9aab`.
- Subject: `Fix Stage 3 resource legality and payment search`.
- Outcome: pain-land colored production remains legally available when life is at or below the later damage amount; state-based loss still occurs only at the normal checkpoint after the resolving object completes. Costed multi-mode sources keep memoization, but activation is solved once per activation cost and each helpful production receives its own search branch. Cascade Bluffs exact-deck acceptance and exact-allocation consumption regressions were added. ROOT-E chose PATH B: an executable invariant now enforces the one-entry conditional-resolution registry required for current inactive-feature subtraction soundness. No evaluator weights changed. `contextual_combo_v1` did not change. The authorized PAY/DECLINE criterion did not change. Policy scoring was not broadened.

### Source-head verification

Source head `30914ee584490ebacd0611721e33409f62cdb416`, tree `15072fedd1b7f5fa6c03d698f420f892d87b9aab`, was verified locally before certification promotion:

- Format, Ruff, and mypy: PASS.
- `tests/kernel`: 67 passed.
- `tests/phase_b`: 241 passed.
- `tests/phase_c`: 171 passed.
- Ownership/provider targeted tests: 112 passed.
- Combo/valuation tests: 24 passed.
- Mutation sensitivity M1–M4: PASS.
- Governance boundaries: PASS.

Behavioral delta:

- Shivan Reef boundary legality: `EXPECTED_CORRECTION`.
- Cascade Bluffs colored filter feasibility: `EXPECTED_CORRECTION`.
- Unexpected regression: none.
- Unrelated drift: none.
- Contextual/evaluator weights unchanged.

### Source-head CI #1312

GitHub Actions run `34727955957` (displayed CI #1312) ran on exact source head `30914ee584490ebacd0611721e33409f62cdb416`, tree `15072fedd1b7f5fa6c03d698f420f892d87b9aab`.

Every substantive technical gate passed, including tests, Phase A verifier, Phase A candidate build and validation, Phase B verifier, Phase B candidate build and validation, and Phase C no-game dry run.

The only expected source-head failure was `Durable Phase A certification is current`, because the prior durable certification was stale after `src/mtg_kernel` changed. Durable Phase B currentness was the expected downstream skip. That was the certification-renewal gate, not a source failure.

Source-head auxiliary workflows also passed:

- Stage 2 Bridge STANDARD Benchmark #97, run `34727955915`: `SUCCESS`.
- Stage 3 PR99 Prototype Preservation #51, run `34727955914`: `SUCCESS`.

### Exact consolidated certification candidates

The Phase A candidate was:

- Artifact: `phase-a-certification-candidate-30914ee584490ebacd0611721e33409f62cdb416`.
- Artifact ID: `10309701365`.
- Exact promoted `CERTIFICATION.json` SHA-256: `5b96cbdb4e677a3597e22f6c7f6b7d826eab82a4f9654a8d9632b1d0c78ea4a5`.
- Bytes: 5138.
- Certified content commit: `30914ee584490ebacd0611721e33409f62cdb416`.
- Certified repository tree: `15072fedd1b7f5fa6c03d698f420f892d87b9aab`.
- Counts: 33 pass, 0 fail, 0 skip, 0 xfail.
- `github_run_id = 34727955957`, `status = PASS`, `clean_tree_before_run = true`, `legacy_evidence_used = false`, and `pilot_lock = PASS`.

The Phase B candidate was:

- Artifact: `phase-b-certification-candidate-30914ee584490ebacd0611721e33409f62cdb416`.
- Artifact ID: `10310020861`.
- Exact promoted `CERTIFICATION.json` SHA-256: `b9ea68849d168615a8ce394f5aec1553ff50386e3e9ad44a3896279ffe1fbe03`.
- Bytes: 6563.
- Certified content commit: `30914ee584490ebacd0611721e33409f62cdb416`.
- Certified repository tree: `15072fedd1b7f5fa6c03d698f420f892d87b9aab`.
- Counts: 241 pass, 0 fail, 0 skip, 0 xfail.
- Golden transcripts: 12.
- `github_run_id = 34727955957`, `status = PASS`, `clean_tree_before_run = true`, `legacy_evidence_used = false`, and `pilot_lock = PASS`.

### Certification promotion

The two exact CI-produced candidates were promoted byte-for-byte, without local regeneration or manual transcription, in:

- Commit: `e4e0cbf4e075149d83582dafa9d8225476c3fdba`.
- Tree: `1b8c651c11421ddcb14367e37858bfaa963af087`.
- Parent: `30914ee584490ebacd0611721e33409f62cdb416`.
- Subject: `Renew Stage 3 consolidated repair certifications`.
- Changed paths: `docs/audit/phase-a-certification/CERTIFICATION.json` and `docs/audit/phase-b-certification/CERTIFICATION.json`.

The certifications intentionally certify source/test candidate `30914ee584490ebacd0611721e33409f62cdb416`, not the later promotion commit.

Those SHA-256 values remain durable verification anchors for the historical consolidated-repair promoted bytes. They are not the current durable certifications.

### Promotion-head exact CI #1313

Promotion-head GitHub Actions run `34744608090` (displayed CI #1313) ran on exact head `e4e0cbf4e075149d83582dafa9d8225476c3fdba`. The workflow conclusion was `SUCCESS`.

Every substantive step passed, including identity lock, repository evidence integrity, Phase A authority classification, Phase B evaluator/learning boundary, public policy information boundary, public policy noninterference, clean engine/support boundary, legacy package non-importability, format, lint, type check, Phase C exact-deck Turn-10 policy/replay smoke, Phase A production verifier, Phase A candidate build/validation, tests, manifest integrity, Phase B verifier, Phase B candidate build/validation, Phase C no-game dry run, Durable Phase A certification current, and Durable Phase B certification current.

Auxiliary exact-head workflows also passed:

- Stage 2 Bridge STANDARD Benchmark #98, run `34744608100`: `SUCCESS`.
- Stage 3 PR99 Prototype Preservation #52, run `34744608080`: `SUCCESS`.

The post-consolidated-repair durable records superseded the historical CR6–CR9 durable records. They are not the obsolete certification files contained on frozen PR #99. They were themselves superseded as CURRENT authority after the ROOT-A source repair changed covered `src/mtg_kernel` paths.

### R7 documentation head and CI #1314

The R7 documentation-only refresh that recorded the consolidated-repair chain was:

- Commit: `686961ee06d7db7a679442a339e754a637589698`.
- Tree: `047472150ff17e6c29d202f178626e4b5e825673`.
- Parent: `e4e0cbf4e075149d83582dafa9d8225476c3fdba`.
- Subject: `Refresh Stage 3 consolidated repair disposition`.

Exact-head GitHub Actions run `34768828544` (displayed CI #1314) ran on that docs head and concluded `SUCCESS`. Auxiliary exact-head workflows also passed:

- Stage 2 Bridge STANDARD Benchmark, run `34768828459`: `SUCCESS`.
- Stage 3 PR99 Prototype Preservation, run `34768828531`: `SUCCESS`.

A fresh Codex review was then requested against exact head `686961ee06d7db7a679442a339e754a637589698`. That review reopened ROOT-A as recorded below.

## Historical ROOT-A authority completion

The ROOT-A authority-boundary completion recorded here was the current Stage 3 source, certification, and validation authority through docs head `69a6e812d269ce24e341b7f660797497e1cd0ac0` and CI #1315–#1317. It remains legitimate historical provenance. It is superseded as CURRENT authority by the final resource-execution provenance repair recorded below, because `src/mtg_kernel/resource_execution.py` changed afterwards. The CR1–CR9 history, the consolidated audit pinned to `f84ff8a101e59be1742d4ffaf115f9f9e8cd8971`, repair commits `342155019e7c404c6e006e0272e5296ea17c5c9f` and `30914ee584490ebacd0611721e33409f62cdb416`, certification promotion `e4e0cbf4e075149d83582dafa9d8225476c3fdba`, R7 docs head `686961ee06d7db7a679442a339e754a637589698`, and CI #1312–#1314 also remain legitimate historical provenance. Do not treat this section as though the ROOT-A repair never happened.

### Fresh Codex review on `686961ee`

Codex reviewed exact head `686961ee06d7db7a679442a339e754a637589698` and opened two new P1 findings. They were not two unrelated architecture defects. They were two remaining manifestations of ROOT-A: strategic/rules decision ownership had not yet been enforced across every choice-ingress source. The earlier repair secured provider call sites but did not fully unify live provider choices, explicit action-choice payloads, and recorded replay decisions.

P1-A, thread `PRRT_kwDOTe7Y0c6iDKCl`, comment DB id `4003713670`, title “Require owner authorization for explicit opponent choices”:

- Explicit action-choice branches in Prismari Command and Demolition Field could consume a choice for another player from the controlled action actor’s `choices` payload.
- That bypassed the strategic-provider authorization layer and allowed the controlled caster to inject an opponent’s hidden-hand discard or library-search decision.
- This was a new manifestation of the same ROOT-A authority class.

P1-B, thread `PRRT_kwDOTe7Y0c6iDKCp`, comment DB id `4003713676`, title “Reject unbound strategic providers outside replay”:

- `require_authorized_provider(...)` correctly checked an existing binding, but when `binding is None` it fell through to a bare provider.
- Missing live authority therefore did not truly fail closed.
- Codex independently confirmed the earlier Claude REV-1 residual hole.

Implementation correction for both findings landed in the source/test repair below. Those GitHub threads remain open pending a fresh exact-head Codex review. Thread resolution is not claimed here.

### Final ROOT-A authority contract

Every player-owned strategic/rules decision has an explicit decision owner. Before consuming an answer, the engine must establish that the choice source is authorized for that decision owner.

The final contract distinguishes three choice sources:

- `LIVE_PROVIDER`: requires an explicit `StrategicChoiceBinding` for `decision_owner_id`. Missing live binding fails closed. Existence of a provider object alone is not authority.
- `EXPLICIT_ACTION_CHOICE`: the action/input actor may provide the explicit value only when that actor is the actual rules decision owner. A controlled caster may not inject another player’s hidden-hand or library choice merely through the caster’s action payload.
- `RECORDED_REPLAY_CHOICE`: replay is an explicit exception to ordinary live binding. Only the kernel `RecordedStrategicChoiceProvider` may use the binding-free replay route. Recorded replay continues to validate decision-owner identity against the transcript.

Not every explicit choice must use a provider. Caster-owned mechanical choices remain valid where actor and decision owner legitimately coincide.

### Source/test repair

The ROOT-A class completion, not two isolated Codex-comment patches, was:

- Commit: `b63bd6e7bcba8e57921264d13e1286f64d7e5115`.
- Tree: `bcda20a28fcd3837419240e61a94ca205ed5a845`.
- Parent: `686961ee06d7db7a679442a339e754a637589698`.
- Subject: `Complete Stage 3 strategic choice authority boundary`.

Important implementation outcomes:

- Shared executor-aware provider authorization.
- Missing live provider binding fails closed.
- Replay exception explicitly gated to the recorded replay provider.
- Explicit action-choice authorization requires the action actor to own the decision.
- Prismari opponent discard injection closed.
- Demolition Field opponent search injection closed.
- Counter-payment explicit-choice path aligned with the same contract.
- Provider call sites moved to the shared executor authorization path.
- Third-player ownership remains based on decision owner, not binary actor/opponent assumptions.
- Class-level authority regressions added.

### Source-head CI #1315

GitHub Actions run `34924054591` (displayed CI #1315) ran on exact source head `b63bd6e7bcba8e57921264d13e1286f64d7e5115`, tree `bcda20a28fcd3837419240e61a94ca205ed5a845`.

Every substantive technical gate passed:

- Frozen identity lock.
- Repository evidence integrity.
- Phase A authority classification.
- Phase B evaluator/learning boundary.
- Public policy information boundary.
- Public policy noninterference.
- Clean-engine boundary.
- Legacy-package exclusion.
- Format, lint, and type check.
- Phase C exact-deck Turn-10 production policy and replay smoke.
- Phase A production verifier.
- Phase A candidate build and validation.
- Full tests.
- Manifest integrity.
- Phase B verifier.
- Phase B candidate build and validation.
- Phase C no-game dry run.

The only expected source-head failure was `Durable Phase A certification is current`, because the prior durable certification was stale after covered `src/mtg_kernel` changes. Durable Phase B currentness was the expected downstream skip. That was the certification-renewal gate, not a source/test failure.

Source-head auxiliary workflows also passed:

- Stage 2 Bridge STANDARD Benchmark #100, run `34924054467`: `SUCCESS`.
- Stage 3 PR99 Prototype Preservation #54, run `34924054683`: `SUCCESS`.

### Exact ROOT-A certification candidates

The Phase A candidate was:

- Artifact: `phase-a-certification-candidate-b63bd6e7bcba8e57921264d13e1286f64d7e5115`.
- Artifact ID: `10382123949`.
- Exact promoted `CERTIFICATION.json` SHA-256: `366000b41884d66226e5596ed6163ea1551214091aea18af6922e5e1dd0bda43`.
- Bytes: 5138.
- Certified content commit: `b63bd6e7bcba8e57921264d13e1286f64d7e5115`.
- Certified repository tree: `bcda20a28fcd3837419240e61a94ca205ed5a845`.
- Counts: 33 pass, 0 fail, 0 skip, 0 xfail.
- `github_run_id = 34924054591`, `status = PASS`, `clean_tree_before_run = true`, `legacy_evidence_used = false`, and `pilot_lock = PASS`.

The Phase B candidate was:

- Artifact: `phase-b-certification-candidate-b63bd6e7bcba8e57921264d13e1286f64d7e5115`.
- Artifact ID: `10382456676`.
- Exact promoted `CERTIFICATION.json` SHA-256: `a6c66eb69a47a042cd392d0b02cc7002d0f29663ae0c8f7c585b39c9972f00de`.
- Bytes: 6563.
- Certified content commit: `b63bd6e7bcba8e57921264d13e1286f64d7e5115`.
- Certified repository tree: `bcda20a28fcd3837419240e61a94ca205ed5a845`.
- Counts: 241 pass, 0 fail, 0 skip, 0 xfail.
- Golden transcripts: 12.
- `github_run_id = 34924054591`, `status = PASS`, `clean_tree_before_run = true`, `legacy_evidence_used = false`, and `pilot_lock = PASS`.

### Certification promotion

The two exact CI-produced candidates were promoted byte-for-byte, without local regeneration or manual transcription, in:

- Commit: `9c4167add36caba74b1eac34a27c83c99c2f6736`.
- Tree: `7355bb5dc755a7c2f3a87a9cf654ee6e42d9b35d`.
- Parent: `b63bd6e7bcba8e57921264d13e1286f64d7e5115`.
- Subject: `Renew Stage 3 authority boundary certifications`.
- Changed paths: `docs/audit/phase-a-certification/CERTIFICATION.json` and `docs/audit/phase-b-certification/CERTIFICATION.json`.

No source or test files changed in this promotion commit. The certifications intentionally certify source/test candidate `b63bd6e7bcba8e57921264d13e1286f64d7e5115`, not the later promotion commit.

These SHA-256 values are the current durable verification anchors for the exact promoted bytes and remain usable after the CI artifact-retention window expires.

### Promotion-head exact CI #1316

Promotion-head GitHub Actions run `34942615509` (displayed CI #1316) ran on exact head `9c4167add36caba74b1eac34a27c83c99c2f6736`. The workflow conclusion was `SUCCESS`.

Every substantive step passed, including Phase A authority classification, Phase A production verifier, Phase B verifier, full tests, Phase C smoke and no-game dry run, Durable Phase A certification current, Durable Phase B certification current, policy boundaries, evidence and identity checks, format, lint, and typing.

Auxiliary exact-head workflows also passed:

- Stage 2 Bridge STANDARD Benchmark #101, run `34942615508`: `SUCCESS`.
- Stage 3 PR99 Prototype Preservation #55, run `34942615533`: `SUCCESS`.

The post-ROOT-A durable records superseded both the historical CR6–CR9 and consolidated-repair durable records. They are not the obsolete certification files contained on frozen PR #99. They were themselves superseded as CURRENT authority after the resource-execution provenance repair changed covered `src/mtg_kernel` paths.

### ROOT-A documentation head and CI #1317

The documentation-only refresh that recorded the ROOT-A authority completion was:

- Commit: `69a6e812d269ce24e341b7f660797497e1cd0ac0`.
- Parent: `9c4167add36caba74b1eac34a27c83c99c2f6736`.
- Subject: `Refresh Stage 3 final authority disposition`.

Exact-head GitHub Actions run `34999298134` (displayed CI #1317) ran on that docs head and concluded `SUCCESS`. Auxiliary exact-head workflows also passed:

- Stage 2 Bridge STANDARD Benchmark #102, run `34999298158`: `SUCCESS`.
- Stage 3 PR99 Prototype Preservation #56, run `34999298138`: `SUCCESS`.

A fresh Codex review was then requested against exact head `69a6e812d269ce24e341b7f660797497e1cd0ac0`. That review opened the resource-execution provenance P1 recorded below.

## Final resource-execution provenance repair

The current Stage 3 source, certification, and validation authority is the resource-execution provenance repair recorded here. Everything above — the CR1–CR9 history, the consolidated audit and repairs, the ROOT-A authority completion, and their certification promotions — remains legitimate historical provenance only.

### Fresh Codex review on `69a6e81`

Codex reviewed exact docs head `69a6e812d269ce24e341b7f660797497e1cd0ac0` and opened one new blocking P1.

- Thread: `PRRT_kwDOTe7Y0c6ivv7d`.
- Comment DB id: `4021459534`.
- Title: “Reuse already-produced mana across allocation levels”.
- Classification: resource execution and provenance. This is not a ROOT-A authority finding. ROOT-A remains a separate completed repair class.

The finding was that a solver-approved canonical allocation may use one multi-mana source at more than one allocation level: one produced unit funds the final payment and another produced unit funds a different source's activation cost. Execution recorded the first source's production in `context.available_mana`, but recursive child execution could attempt to activate that same source again before consuming the already-produced provenance.

The exact-deck witness is Izzet Boilerworks plus Izzet Signet paying `{3}`. The shared solver returned a feasible canonical allocation:

- Parent payment: Izzet Boilerworks `R` to `GENERIC:0`; Izzet Signet `R` to `GENERIC:1`; Izzet Signet `U` to `GENERIC:2`.
- Child activation-cost allocation for Izzet Signet: Izzet Boilerworks `U` to `GENERIC:0`.

The old execution tapped Boilerworks, recorded its `U` and `R` production, recursed into the Signet activation cost, saw Boilerworks as the child funding source, attempted to activate and tap Boilerworks a second time, and failed with `IllegalAction`. That violated the core contract: a still-valid solver-approved canonical allocation must execute exactly.

### Resource-provenance execution invariant

Once a mana-source activation has produced mana and that production is recorded in the binding context, any later canonical allocation unit that references that same produced provenance must consume or reserve the already-produced mana before attempting another activation of that semantic source. Another source activation is permitted only for an actual remaining deficit, and only where a legal source instance remains available.

The execution order is:

```text
PRODUCE
-> RECORD AVAILABLE PROVENANCE
-> RESERVE / CONSUME EXISTING PROVENANCE
-> ACTIVATE ADDITIONAL SOURCES ONLY FOR UNSATISFIED DEFICIT
```

Explicitly:

- The shared solver remains the sole feasibility and canonical-allocation authority.
- No second resource solver was added.
- No executor-side replanning was added.
- Exact activation-cost allocation remains binding.
- Marked and unmarked provenance remain distinct and preserved, and marker event IDs remain rules-private.
- Multiple physical instances sharing one semantic source identity still execute.
- Source capacity remains enforced. An exhausted source is not reactivated, and an allocation deficit that no legal instance can cover fails closed instead of creating mana.

### Source/test repair

- Commit: `28779896db7b1bcaea08d23cd3cfc3cb92c6a66f`.
- Tree: `1bba721f738cf5d133eee3376f31c8997ef01e51`.
- Parent: `69a6e812d269ce24e341b7f660797497e1cd0ac0`.
- Subject: `Fix canonical multi-level mana provenance execution`.
- Changed paths: `src/mtg_kernel/resource_execution.py` and `tests/kernel/test_resource_execution_contract.py`.

Important implementation outcomes:

- `_BindingContext` gained reserved provenance accounting alongside recorded available provenance.
- Already-produced provenance is distinguished from uncommitted surplus, so a later allocation level may only cover from production that no earlier remaining demand has claimed.
- Matching produced units are reserved before child recursion rather than after it.
- `_take_exact_allocation_payment(...)` consumes the exact reserved provenance and releases the reservation as it spends.
- Source activation occurs only for the remaining deficit.
- Production is recorded and immediately made available to later allocation levels.
- `src/mtg_kernel/resource_payment.py` and `src/mtg_kernel/resource_sources.py` were not changed.
- The canonical solver result for the Boilerworks plus Signet witness was identical before and after the repair.

### Regression and mutation evidence

The exact Codex witness now executes. Izzet Boilerworks plus Izzet Signet paying `{3}` succeeds with payment `{"R": 2, "U": 1}`, exactly one Boilerworks activation, and exactly one Signet activation.

The regression matrix covers the defect class rather than one card pair:

- the exact Boilerworks plus Signet split;
- a synthetic multi-mana parent/child split with no card-specific assumption;
- already-produced provenance preferred over a new activation;
- deficit behavior, where existing provenance is consumed first and only the shortfall activates another instance;
- source capacity, which passes when existing production covers the later allocation and fails closed when additional production is required and no legal instance remains;
- identical semantic source instances backed by two physical objects;
- exact activation-cost color selection, including hybrid;
- floating mana mixed with produced source provenance;
- marked and unmarked floating provenance controls.

Mutation sensitivity used disposable scratch copies of the kernel package. The primary working tree was never mutated, and each scratch file was restored byte-identically between mutations. All four defect classes are pinned by semantic assertion or rules failures rather than import or syntax errors:

- `M1`, restore recursion-first child activation: the exact Boilerworks plus Signet witness and the synthetic split fail with the second-activation `IllegalAction`.
- `M2`, ignore source provenance and spend any matching color: exact-requirement binding and the marked-mana ledger regressions fail.
- `M3`, never reactivate a semantic ID once it has been seen: the identical-instance and reserved-parent regressions fail.
- `M4`, overconsume already-produced provenance: exact-allocation payment accounting fails.

### Local verification of the source repair

Source head `28779896db7b1bcaea08d23cd3cfc3cb92c6a66f` was verified locally before certification renewal:

- Targeted resource-payment tests across kernel, Phase B, and Phase C: 127 passed in 1.62 seconds.
- `tests/kernel`: 80 passed.
- `tests/phase_b`: 241 passed.
- `tests/phase_c`: 180 passed in 7009.53 seconds (`1:56:49`).
- Format, lint, and mypy: PASS.
- Governance checkers: PASS, except the durable Phase A and Phase B certification checkers, which reported the expected staleness before renewal.

Behavioral delta: solver-feasible canonical payments that reuse already-produced source provenance across allocation levels now execute successfully, including Izzet Boilerworks plus Izzet Signet paying `{3}`. Solver feasibility, canonical allocation, STANDARD ranking, the authorized counter-payment criterion, evaluator scores, replay semantics, and unrelated mana payments were unchanged.

### Source-head CI #1318

GitHub Actions run `35270873953` (displayed CI #1318) ran on exact source head `28779896db7b1bcaea08d23cd3cfc3cb92c6a66f`, tree `1bba721f738cf5d133eee3376f31c8997ef01e51`.

Every substantive technical gate passed:

- Frozen identity lock integrity.
- Repository evidence integrity.
- Phase A authority classification.
- Phase B evaluator and learning boundary.
- Public policy information boundary.
- Public policy noninterference.
- Clean-engine and support-package boundary.
- Legacy-package exclusion.
- Format, lint, and type check.
- Phase C exact-deck Turn-10 production policy and replay smoke.
- Phase A production verifier.
- Phase A candidate build and validation.
- Full tests.
- Manifest integrity.
- Phase B verifier.
- Phase B candidate build and validation.
- Phase C no-game dry run.

The overall workflow conclusion was `FAILURE`, and the only failing step was `Durable Phase A certification is current`, because the prior durable certification was stale after covered `src/mtg_kernel` changes. `Durable Phase B certification is current` was the expected downstream skip. This was expected certification staleness at the renewal gate, not a technical failure.

Source-head auxiliary workflows also passed:

- Stage 2 Bridge STANDARD Benchmark #103, run `35270873964`: `SUCCESS`.
- Stage 3 PR99 Prototype Preservation #57, run `35270873957`: `SUCCESS`.

### Exact resource-provenance certification candidates

The Phase A candidate was:

- Artifact: `phase-a-certification-candidate-28779896db7b1bcaea08d23cd3cfc3cb92c6a66f`.
- Artifact ID: `10522047766`.
- Exact promoted `CERTIFICATION.json` SHA-256: `608e1bb677b58b83abb9df2c203d9a5ee6666d1167736946394414cbfe38ae1e`.
- Bytes: 5138.
- Certified content commit: `28779896db7b1bcaea08d23cd3cfc3cb92c6a66f`.
- Certified repository tree: `1bba721f738cf5d133eee3376f31c8997ef01e51`.
- Counts: 33 pass, 0 fail, 0 skip, 0 xfail.
- `github_run_id = 35270873953`, `status = PASS`, `clean_tree_before_run = true`, `legacy_evidence_used = false`, and `pilot_lock = PASS`.

The Phase B candidate was:

- Artifact: `phase-b-certification-candidate-28779896db7b1bcaea08d23cd3cfc3cb92c6a66f`.
- Artifact ID: `10522147688`.
- Exact promoted `CERTIFICATION.json` SHA-256: `296cd7164b41b60b634d98ca3f91255ae98f7c45e3af35a2d198b49bfe8c2d62`.
- Bytes: 6563.
- Certified content commit: `28779896db7b1bcaea08d23cd3cfc3cb92c6a66f`.
- Certified repository tree: `1bba721f738cf5d133eee3376f31c8997ef01e51`.
- Counts: 241 pass, 0 fail, 0 skip, 0 xfail.
- Golden transcripts: 12.
- `github_run_id = 35270873953`, `status = PASS`, `clean_tree_before_run = true`, `legacy_evidence_used = false`, and `pilot_lock = PASS`.

### Certification promotion

The two exact CI-produced candidates were promoted byte-for-byte, without local regeneration or manual transcription, in:

- Commit: `426ff4e6aaa64a9af178cb5bbaf674fbabfda7e9`.
- Tree: `cf667d147d4b5726df048daf2d6a00a3a54a1fa4`.
- Parent: `28779896db7b1bcaea08d23cd3cfc3cb92c6a66f`.
- Subject: `Renew Stage 3 resource provenance certifications`.
- Changed paths: `docs/audit/phase-a-certification/CERTIFICATION.json` and `docs/audit/phase-b-certification/CERTIFICATION.json`.

No source or test files changed in this promotion commit. The certifications intentionally certify source/test candidate `28779896db7b1bcaea08d23cd3cfc3cb92c6a66f`, not the later promotion commit.

These SHA-256 values are the current durable verification anchors for the exact promoted bytes and remain usable after the CI artifact-retention window expires.

### Promotion-head exact CI #1319

Promotion-head GitHub Actions run `35291820662` (displayed CI #1319) ran on exact head `426ff4e6aaa64a9af178cb5bbaf674fbabfda7e9`. The workflow conclusion was `SUCCESS`.

Every substantive step passed, including frozen identity lock integrity, repository evidence integrity, Phase A authority classification, Phase B evaluator and learning boundary, public policy information boundary, public policy noninterference, clean-engine and support-package boundary, legacy-package exclusion, format, lint, type check, Phase C exact-deck Turn-10 policy and replay smoke, Phase A production verifier, Phase A candidate build and validation, full tests, manifest integrity, Phase B verifier, Phase B candidate build and validation, Phase C no-game dry run, `Durable Phase A certification is current`, and `Durable Phase B certification is current`.

Auxiliary exact-head workflows also passed:

- Stage 2 Bridge STANDARD Benchmark #104, run `35291820663`: `SUCCESS`.
- Stage 3 PR99 Prototype Preservation #58, run `35291820661`: `SUCCESS`.

### Current Stage 3 authority

- Current source/test authority: `28779896db7b1bcaea08d23cd3cfc3cb92c6a66f`.
- Current certification promotion: `426ff4e6aaa64a9af178cb5bbaf674fbabfda7e9`.

The earlier ROOT-A source repair `b63bd6e7bcba8e57921264d13e1286f64d7e5115` and its certification promotion `9c4167add36caba74b1eac34a27c83c99c2f6736` remain valid historical provenance. They are no longer the current source or certification authority, because `src/mtg_kernel/resource_execution.py` changed afterwards. This documentation refresh records already validated implementation and certification provenance; its own resulting commit still requires exact-head CI.

## Nonblocking followups

Stage 3 does not change `scripts/_certification_provenance.py`. Independent review identified a governance hardening issue for later work, tracked as open issue #105, “Harden certification provenance against silent comparison bypass”: the helper does not perform the recorded-artifact byte comparison when a current-run candidate is present, and an expired recorded artifact can make that comparison unavailable without itself appending an error. The durable SHA-256 anchors above mitigate later auditability for this Stage 3 promotion, but they do not replace the need for a future fail-closed correction to that helper. This is recorded as a follow-up defect, not treated as evidence that the Stage 3 candidate bytes differ.

Windows path length is also a known measurement hazard for this repository's long golden-transcript paths. Digest verification should prefer repository-object or in-memory archive reads over Windows filesystem extraction when path length could exceed the platform limit; a missing-on-disk path must not by itself be treated as a missing Git object.

- `NB-V3-1` / ROOT-E PATH B: inactive-component valuation still subtracts by feature rather than component identity. That remains a documented future constraint. Stage 3 did not broaden policy scoring. An executable invariant now enforces the one-entry conditional-resolution registry required for current soundness.
- `NB-V3-2`: The class-level conditional-resolution invariant currently binds to the real `BOUNCE_AND_KICKER_DRAW` registry key because synthetic unregistered effect kinds cannot exercise the registry.

The kicked-input truthiness issue is not a remaining followup; it was corrected and independently audited in V3.

## Guardrail outcomes

At this disposition point:

- PR #99 remains frozen exactly at head `4c9a404fc9308ecc281711b4b9b48eef6dfd441b`, base `150671a8e7a78e5fa14b6b3aca2308f6af647df3`, 34 commits, 37 files, open, draft, and unmerged.
- Canonical PR #99 patch preservation remains exact: SHA-256 `31dbf0dad6c8bc497ea8dcb2bd40694d28e9b90cd6b25cf1b24a4cb5aae88b16`, 297677 bytes.
- Historical pilot artifacts were not changed.
- Strategic Context was not implemented.
- REQUIREMENTS_AWARE behavior was not implemented.
- PR #99 V2 exploratory scoring, projection, arms, and configs were not imported.
- No replacement exploratory policy was implemented.
- No duplicate strategic-choice system was added.
- No duplicate semantic-action identity/normalizer layer was added.
- No duplicate resource feasibility solver or full-executor feasibility planner was added.
- No duplicate payment planner and no executor-side payment replanning were added.
- Canonical allocation exactness was not bypassed.
- Existing unrelated STANDARD priority-action ranking, weights, and tie-breaks were not changed.
- Evaluator weights were not changed.
- The authorized counter-payment PAY versus DECLINE criterion was not changed.
- No pilot, replacement pilot, exploratory study, or full study was executed.
- Pilot authorization remains locked and pending explicit owner approval.
- The full study remains separately locked.
- PR #99 branch-local Phase A/B certification files were never copied forward.
- Merge remains a separate owner-gated action.
- Stage 4 has not begun.

## Closeout condition

This supplement is the final Stage 3 disposition layer. Technical implementation is complete. Final certifications are current. Promotion-head exact CI #1319 and auxiliary workflows are green. This documentation refresh records the completed resource-execution provenance repair. It does not declare PR #104 Ready for Review, merge-ready, or merged. Stage 4 has not begun. The pilot is not authorized.

The current source/test authority is `28779896db7b1bcaea08d23cd3cfc3cb92c6a66f`. Its exact CI-produced Phase A and Phase B certifications are promoted in `426ff4e6aaa64a9af178cb5bbaf674fbabfda7e9`, and promotion-head CI #1319 succeeded. The CR1–CR9 history, consolidated repair through `30914ee` / `e4e0cbf` / R7 docs head `686961ee` with CI #1312–#1314, and the ROOT-A completion through `b63bd6e` / `9c4167a` / docs head `69a6e81` with CI #1315–#1317, remain provenance only.

The resource-provenance Codex P1 thread `PRRT_kwDOTe7Y0c6ivv7d` is repaired in code and carries current Phase A and Phase B certifications, but it remains open. Thread resolution is pending a fresh Codex review of the resulting exact final docs head. Do not treat it as resolved in this document. The two earlier ROOT-A Codex P1 threads (`PRRT_kwDOTe7Y0c6iDKCl` and `PRRT_kwDOTe7Y0c6iDKCp`) are likewise repaired in code and remain open pending that same review. Older unresolved review threads were not mutated.

This documentation-only commit must complete exact-head CI. After that, a fresh Codex review of that exact docs head remains required. The status is `TECHNICAL_IMPLEMENTATION_AND_CERTIFICATION_COMPLETE_FINAL_CODEX_REVIEW_PENDING` even if this documentation commit's CI later passes, until that Codex review returns with no new blocking finding. Review threads must remain unresolved until that final review gate. No Ready-for-Review transition or merge is authorized here; merge still requires separate explicit owner authorization.