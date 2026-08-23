# Stage 3 final PR #99 disposition supplement

Status: TECHNICAL_DISPOSITION_COMPLETE_PENDING_FINAL_HEAD_VALIDATION

This document supplements, and does not rewrite, `INVENTORY.json`.

`INVENTORY.json` is the immutable first-substantive Stage 3 snapshot. Its original classifications and `PENDING_*` / `OWNER_DECISION_PENDING` statuses remain historical evidence of what was known before extraction and before the owner decision. Final outcomes are recorded here instead of mutating that snapshot.

## Frozen prototype and Stage 3 base

- Stage 3 base `main`: `8b69b0aa3c3896c26f9c0823fd102dfa9a87f41f`.
- Frozen prototype PR: #99, `Phase C: directed exploratory V2 redesign`.
- PR #99 base: `150671a8e7a78e5fa14b6b3aca2308f6af647df3`.
- PR #99 head: `4c9a404fc9308ecc281711b4b9b48eef6dfd441b`.
- PR #99 commit count: 34.
- PR #99 changed-file count: 37.
- Canonical PR #99 patch SHA-256: `31dbf0dad6c8bc497ea8dcb2bd40694d28e9b90cd6b25cf1b24a4cb5aae88b16`.
- PR #99 remains open, draft, unmerged, and unmodified.

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
4. Execute actual mana abilities during resolution without creating a new priority opportunity.
5. Spend the exact allocation chosen by the shared solver.
6. Fail closed if current execution state cannot bind the canonical semantic allocation.

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

## Source-behavior verification and certification promotion

The implementation source-behavior head is:

`f8eb5343c3d89d956b8fe994184c6599c817c815`

CI run `32595603688` verified that head and produced the certification candidates that were later promoted. Recorded verification included:

- Full test suite: 476 passed.
- Phase A production verifier: 33 pass, 0 fail, 0 skip, 0 xfail.
- Phase B verifier: 239 pass, 0 fail, 0 skip, 0 xfail.
- Exact-deck Turn-10 smoke: PASS with fresh replay equality.
- Frozen manifest integrity: PASS.
- Phase C no-game dry run: `READY_FOR_OWNER_REVIEW` with `execution_allowed = false`, `full_study_execution_allowed = false`, and `game_results_created = 0`.

The two exact CI-produced certification candidate files were promoted atomically, without manual transcription, in commit:

`e8db5fd0f3f068b8b01c898373a2bcd973d16bda`

Exact durable certification provenance:

| Certification | Certified source head | SHA-256 of exact candidate/committed bytes | Git blob |
| --- | --- | --- | --- |
| Phase A | `f8eb5343c3d89d956b8fe994184c6599c817c815` | `ed3954e921157cfc84291ace5a9d690f3c5bd33412f9b4fe87fbb27bc7b9beec` | `143c54564caf13e0de7d68168d9dcc5b3e15f149` |
| Phase B | `f8eb5343c3d89d956b8fe994184c6599c817c815` | `6604d17b7afce4f132c42f7c542d1802803ddce08b7375c4f1b7c8fbabc9e3fa` | `a522016c09bf613dfb2737ab17da5c11b8dae0c8` |

The durable records are current post-PR #101 Stage 3 certifications. They are not the obsolete certification files contained on frozen PR #99.

## Guardrail outcomes

At this disposition point:

- PR #99 remains exactly at head `4c9a404fc9308ecc281711b4b9b48eef6dfd441b`, base `150671a8e7a78e5fa14b6b3aca2308f6af647df3`, 34 commits, 37 files, open, draft, and unmerged.
- Canonical PR #99 patch SHA-256 remains `31dbf0dad6c8bc497ea8dcb2bd40694d28e9b90cd6b25cf1b24a4cb5aae88b16`.
- Historical pilot artifacts were not changed.
- Strategic Context was not implemented.
- REQUIREMENTS_AWARE behavior was not implemented.
- PR #99 V2 exploratory scoring, projection, arms, and configs were not imported.
- Existing unrelated STANDARD priority-action ranking, weights, and tie-breaks were not changed.
- No duplicate resource feasibility solver or full-executor feasibility planner was added.
- No duplicate semantic-action identity/normalizer layer was added.
- No pilot or full study was executed.
- PR #99 branch-local Phase A/B certification files were never copied forward.

## Closeout condition

This supplement is the final Stage 3 disposition layer. It does not itself declare the pull request merge-ready merely by existing.

Technical Stage 3 closeout requires CI and Stage 3 prototype preservation to pass on the actual post-supplement PR head. Those final-head run identifiers belong in the PR #104 conversation after they complete, not in this file. The final audit must also confirm that `INVENTORY.json` remains byte-identical to its first-substantive snapshot and that no prohibited or historical pilot paths were introduced by this supplement.