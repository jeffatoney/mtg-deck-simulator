# Stage 3 final PR #99 disposition supplement

Status: TECHNICAL_DISPOSITION_COMPLETE_PROVENANCE_REFRESH_PENDING_EXACT_HEAD_VALIDATION

Independent final readiness audit classification: `READY_WITH_NONBLOCKING_FOLLOWUPS`. This is a technical classification; it does not declare the pull request merged or automatically merge-ready.

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

The current authoritative Stage 3 CR6 source/test candidate is:

`6a25a766ba13a8c0fa17b0a7abce61c7a77eef3b`

Its certified repository tree is:

`a59c324bb9e55c22ea5b21bc7a0e23001bec8bc7`

CR6 corrected the P1 stack-spell effect-relevance defect discovered after the previous documentation head. Protected-spell contextual valuation now retains selected spell effects, excludes unselected spell modes and non-spell hand-activation capabilities, and retains legitimate post-resolution abilities of permanent spells. The runtime and valuation paths share the same hand-activation classification and use the kernel `PERMANENT_TYPES` authority.

Muddle the Mixture is the exact regression. Before CR6, its protected-spell effect kinds incorrectly included `COUNTER_IF` and `TRANSMUTE`, producing contextual value 27 and selecting `PAY` against Syncopate {3}, whose payment value was 24. After CR6, only `COUNTER_IF` contributes, contextual value is 9, and the correct result is `DECLINE`. The owner-authorized criterion did not change: `PAY` iff contextual target value is strictly greater than actual required payment times mana weight 8; ties remain `DECLINE`, and the evaluator remains `contextual_combo_v1`.

CR6 source commit `6a25a766ba13a8c0fa17b0a7abce61c7a77eef3b` changed exactly:

- `src/mtg_kernel/phase_b_actions_common.py`
- `src/mtg_kernel/phase_b_runtime_effects_interaction.py`
- `tests/kernel/test_stack_spell_effect_relevance.py`
- `tests/phase_c/test_stage3_counter_payment_boundary.py`

The preserved CR6 working patch is `/home/jeffa/stage3-pr104-cr6-working.patch`, SHA-256 `cba49f5e8d5e5075db7f371dbe0e6ef581819c6c5c8e9663d044ccdf75a93f19`, 10682 bytes.

Source-head CI run `33240921215` (displayed CI #1301) verified that candidate and produced both certification candidates. Recorded technical validation included:

- Format, lint, and mypy: PASS.
- Turn-10 production/fresh replay smoke: PASS.
- Phase A production verifier: 33 pass, 0 fail, 0 skip, 0 xfail.
- Phase A certification candidate validation: PASS.
- Full pytest: 524 passed.
- Manifest: PASS.
- Phase B verifier: 239 pass, 0 fail, 0 skip, 0 xfail.
- Phase B golden transcripts: 12/12 PASS.
- Phase B certification candidate validation: PASS.
- Phase C no-game dry run: PASS.
- Pilot lock: PASS.

Run-status provenance: source-head CI #1301 has an overall workflow conclusion of `failure` only because, after the substantive technical gates passed, the previously tracked durable Phase A certification expectedly reported `missing=[]`, `extra=[]`, and `changed=['src/mtg_kernel']`. Durable Phase B current was skipped after that Phase A current step failed. This was the expected source-head certification-renewal boundary, not a source, test, verifier, or candidate failure.

Source-head auxiliary validation also passed:

- Stage 2 Bridge STANDARD Benchmark, run `33240921218` (displayed run #86): PASS.
- Stage 3 PR99 Prototype Preservation, run `33240921231` (displayed run #40): PASS.

The two exact CI-produced certification candidate files were promoted byte-for-byte, without local regeneration or manual transcription, in commit:

`946b223e66f66824f0a469b12f0baa76b8d5d581`

Both durable records intentionally remain bound through `certified_content_commit` to source/test candidate `6a25a766ba13a8c0fa17b0a7abce61c7a77eef3b`; they do not certify the certification-promotion commit itself.

Current exact durable certification provenance:

| Certification | Certified source/test candidate | Certified repository tree | Source-head CI run | Promotion commit | SHA-256 of exact candidate/promoted bytes | Bytes | Git blob at promotion head | Covered-content SHA-256 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Phase A | `6a25a766ba13a8c0fa17b0a7abce61c7a77eef3b` | `a59c324bb9e55c22ea5b21bc7a0e23001bec8bc7` | `33240921215` | `946b223e66f66824f0a469b12f0baa76b8d5d581` | `8eaf37c9dc6df83f773a9b15980f042a78620f4b85a9f877bc289d882549cf1c` | 5138 | `c28ed6f1fe444afe994aedd453aea01271ab09a4` | `sha256:3e24a9f8debf9f823a2e6240dfe230c08841d99be88f3eb578b1bf69a2f8dbc2` |
| Phase B | `6a25a766ba13a8c0fa17b0a7abce61c7a77eef3b` | `a59c324bb9e55c22ea5b21bc7a0e23001bec8bc7` | `33240921215` | `946b223e66f66824f0a469b12f0baa76b8d5d581` | `a7c6ef0cb19038634eaa2cd3a1e1168011960ffb73d084298c8d9c6c0d039692` | 6563 | `2ea57726f393266b19c79d8ef10db149849ffada` | `sha256:d4c5517e220a289e3bb74e01780b576cc0b126d00fc6fc749184b64e65c2bf38` |

Compared with the immediately prior durable records, the only Phase A covered-path digest change is `src/mtg_kernel`, now `sha256:19f874eec2eda7ef17837c55fa268bafafdb06316830d65ab8312d8a82761ae0`. The only Phase B covered-path digest changes are that same `src/mtg_kernel` digest and `tests/phase_c`, now `sha256:ea90fa45cf0daa7538280600b21a47af6d3e6fcb79de3eb90d56e24fca48dd4d`. `tests/kernel` remains intentionally outside both certification `covered_paths`.

Both candidates record `github_run_id = 33240921215`, `verification_environment = GITHUB_ACTIONS`, `clean_tree_before_run = true`, `legacy_evidence_used = false`, and `pilot_lock = PASS`.

The certification-promotion head `946b223e66f66824f0a469b12f0baa76b8d5d581` then completed final-head validation:

- Main CI run `33263922366` (displayed CI #1302): SUCCESS. It ran from 2026-08-29 09:47:32 PT through 11:37:20 PT, an actual duration of 1 hour 49 minutes 48 seconds. All normal steps passed, including full Tests, both verifiers, both candidate validations, Phase C no-game dry run, and both durable-current certification checks.
- Stage 2 Bridge STANDARD Benchmark, run `33263922371` (displayed run #87): PASS.
- Stage 3 PR99 Prototype Preservation, run `33263922435` (displayed run #41): PASS.

The immediately preceding pre-CR6 chain remains legitimate but superseded historical provenance: source/test commit `3da7f577e9bd24aa4c587412b54cf42b911db5f4`, source-head CI run `33101238756`, certification promotion `048e3565560a7d6d3bc60e46fc60f5df7a36a9fd`, and documentation refresh `ef4864d02503737bfa65f72d9c383f211fa56800`. That chain was valid when recorded, but CR6 subsequently identified and corrected the stack-spell effect-relevance defect, so none of those commits or runs is the current authoritative chain.

The still-earlier Stage 3 source and certification chain also remains historical context: source head `f8eb5343c3d89d956b8fe994184c6599c817c815`, CI run `32595603688`, and promotion commit `e8db5fd0f3f068b8b01c898373a2bcd973d16bda`. It is not current.

These SHA-256 values are durable verification anchors for the exact promoted bytes and remain usable after the CI artifact-retention window expires.

Certification candidate artifact bytes, durable SHA-256 anchors, and Git repository object identity are distinct provenance layers. The Git blob IDs identify the exact promoted repository objects; they do not replace the SHA-256 anchors or imply that artifact retention is permanent.

The durable records are the current post-PR #101 Stage 3 certifications. They are not the obsolete certification files contained on frozen PR #99. This documentation refresh records already validated provenance; its own resulting commit is not CI-validated until exact-head CI completes.

## Known certification-provenance follow-up

Stage 3 does not change `scripts/_certification_provenance.py`. Independent review identified a governance hardening issue for later work: the helper does not perform the recorded-artifact byte comparison when a current-run candidate is present, and an expired recorded artifact can make that comparison unavailable without itself appending an error. The durable SHA-256 anchors above mitigate later auditability for this Stage 3 promotion, but they do not replace the need for a future fail-closed correction to that helper. This is recorded as a follow-up defect, not treated as evidence that the Stage 3 candidate bytes differ.

Windows path length is also a known measurement hazard for this repository's long golden-transcript paths. Digest verification should prefer repository-object or in-memory archive reads over Windows filesystem extraction when path length could exceed the platform limit; a missing-on-disk path must not by itself be treated as a missing Git object.

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
- No pilot, replacement pilot, exploratory study, or full study was executed.
- PR #99 branch-local Phase A/B certification files were never copied forward.

## Closeout condition

This supplement is the final Stage 3 disposition layer. It does not itself declare the pull request merge-ready merely by existing.

The CR6 source/test candidate `6a25a766ba13a8c0fa17b0a7abce61c7a77eef3b` is technically validated, its exact CI-produced Phase A and Phase B certifications are promoted in `946b223e66f66824f0a469b12f0baa76b8d5d581`, and promotion-head CI #1302 is fully green. This documentation-only commit is the remaining provenance refresh.

The independent technical audit classification remains `READY_WITH_NONBLOCKING_FOLLOWUPS`, but this documentation refresh does not itself make PR #104 ready for GitHub review or merge. Its resulting exact head must complete CI before CR6 thread resolution or any Ready-for-Review mutation. A fresh live review-thread and current-head audit must follow that CI. Merge still requires separate explicit human authorization.