# Integration Coverage Report

**Status:** BLOCKED_NOT_PROVEN

**Integration branch:** `agent/integration-interaction-coverage`

## Executive result

The denominator is explicit and frozen:

`216 requirements / 216 inventoried / 173 policy-ready-or-not-required / 43 policy/replay-gap records / 0 record-level PROVEN`

The 216 records are:

- 80 `CARD_COMPOSITION` records;
- 126 `CARD_EFFECT` records; and
- 10 `GLOBAL_RULE` records.

The frozen manifest SHA-256 is:

`sha256:20d767ea754841bf0f9bda378068c4c705e0b9f8f8f4be20ca15be1f24bb2cdc`

Of the 216 records, 94 contain at least one strategic choice and 122 require no strategic policy. Of those 94 strategic records, 51 currently have a complete reviewed route whose live production-policy/replay support is present, while 43 have at least one missing route or live support defect. Therefore 173 of 216 records are currently policy-ready or require no strategic policy.

This integration does **not** claim `216 / 216 engine-supported / 216 / 216 replay-supported / 216 / 216 directly tested`, because the four source lanes did not produce record-addressable proof bundles. They ran before the coordinator denominator was frozen. Converting broad implementation audits or passing repository tests into 216 per-record proof claims would recreate the exact coverage ambiguity this work is intended to eliminate.

The record-level policy/replay calculation is reproducible through `scripts/build_interaction_integration_coverage.py`; it cross-references each frozen record and each strategic choice occurrence against Agent C's reviewed routes and live provider/replay audit.

## Source lanes reconciled

| Lane | PR | Head | Integrated treatment |
|---|---:|---|---|
| Coordinator / interaction inventory | #88 | `0a6e90d6a0346b837986bfe54ac5e676f22bd5c4` | Preserved through Agent B's stacked base; denominator corrected and frozen. |
| Agent D / pre-pilot diagnostics | #89 | `751b98b33bf8556d28c96ee4bec990b2e0ff8429` | Diagnostic workflow, runner, Phase B path coverage, and tests preserved byte-for-byte. Branch-specific derived certification intentionally not copied. |
| Agent C / policy + replay conformance | #90 | `490960781ba8770cf5e0e9ac4f7bd69e58f5ae4a` | Workflow, registry, audit, audit document, and tests preserved byte-for-byte. |
| Agent B / engine + rules conformance | #91 | `8447444dc6b40f9315c99f5e153bd21166d3341b` | Used as the integration branch base, preserving all engine/rules changes and tests. |

There were no direct pathname collisions among the substantive outputs of the four lanes.

## Integration contradictions found and resolved

### 1. Coordinator denominator contradiction — corrected

The coordinator contract defines ten minimum global-rule records, but its bootstrap lock still declared seven global records, zero effect records, and zero total records. The deterministic generator reports and CI independently verifies:

- 80 card-composition records;
- 126 card-effect records;
- 10 global-rule records;
- 216 total records.

The lock now contains those values and the generated manifest digest. This was the single inherited failing repository test on Agent B's standalone head. It was a coordinator/integration defect, not an Agent B engine regression.

### 2. Coordinator workflow Python contradiction — corrected

Both coordinator interaction workflows requested Python 3.11 while `pyproject.toml` requires Python 3.12. The workflows now request Python 3.12.

### 3. Agent D certification cannot be transplanted — resolved by omission

Agent D renewed `docs/audit/phase-b-certification/CERTIFICATION.json` for its standalone branch. That file is derived evidence bound to a specific covered tree. Once Agent D is combined with Agent B's kernel changes, that certificate is stale by definition.

The integration therefore preserves Agent D's executable work but does not copy its branch-specific certificate. The combined tree must generate and install a fresh Phase B certification candidate after its substantive checks pass.

## Cross-lane coverage matrix

| Coverage layer | Explicit denominator | Current integration evidence | Result |
|---|---:|---|---|
| Interaction inventory | 216 records | Deterministically generated, frozen, and CI-verified | **216 / 216 mapped** |
| Record-level engine proof | 216 records | Agent B supplies implementation audit and focused tests, but no frozen-record proof overlay | **0 / 216 record-attested** |
| Strategic policy requirement | 216 records | 94 require strategic policy; 122 do not | **94 require / 122 not required** |
| Record-level policy/replay route completeness | 94 strategic records | 51 have all strategic choices currently routed and live-supported | **51 / 94 complete** |
| Policy-ready or not required | 216 records | 122 no-policy-required + 51 complete strategic records | **173 / 216** |
| Strategic choice occurrences | 145 occurrences | 98 have reviewed routes; 96 also have current live support | **98 / 145 routed; 96 / 145 live-supported** |
| Strategic policy/replay classes | 49 unique classes | 23 reviewed routes; 26 unrouted | **23 / 49 routed** |
| Strategic provider/replay protocol | 4 provider methods | Production provider and recorded replay provider implement all four | **4 / 4 method parity** |
| Record-level replay proof | 216 records | Replay invariants and Turn-10 fresh replay exist, but no frozen-record proof overlay | **0 / 216 record-attested** |
| Record-level direct-test proof | 216 records | Focused/direct tests exist, but evidence is not attached by `record_id` | **0 / 216 record-attested** |
| Aggregate `PROVEN` ledger | 216 records | No frozen-surface proof bundles have yet been aggregated | **0 / 216 PROVEN** |

`0 / 216 record-attested` does **not** mean the engine, replay system, or tests support zero interactions. It means zero of the 216 frozen interaction records currently carry the record-addressable evidence required by the coordinator contract. Implementation and broad test evidence exist; the proof overlay does not yet exist.

Similarly, `173 / 216 policy-ready-or-not-required` is a policy/replay routing measure, not an aggregate proof score. It says that 122 records require no strategic policy and 51 strategic records have complete current routes. It does not imply those 173 records are engine-proven or directly tested by frozen `record_id` evidence.

## Remaining engine/rules blockers from Agent B

Agent B identifies ten unresolved blocker families:

1. hybrid-cost and exact/generic mana-payment configuration;
2. simultaneous same-controller trigger ordering;
3. optional-trigger decision timing;
4. general replacement-effect ordering;
5. cleanup re-entry discard selection;
6. legend-rule keep choice;
7. Commander hand/library replacement choice;
8. generic resolution-time scry choice ownership;
9. compound retarget metadata for copied Prismari Command spells; and
10. global attack destinations beyond opponent players.

These are rules-owned blockers. They must not be closed by inserting a deterministic strategic preference into the engine.

## Remaining policy/replay blockers from Agent C

Agent C inventories 49 unique strategic choice classes. Twenty-three have reviewed routes and twenty-six do not. At record level, those missing routes and live-support defects affect 43 of the 94 records that require strategic policy.

Two additional concrete production-policy defects are independently exposed:

- runtime purpose `PRISMARI_DISCARD` is emitted and legality/replay checked, but the production policy provider has no handler for it; and
- targeted trigger effect `BOUNCE_TARGET` reaches mandatory trigger targeting but is not supported by the production trigger-target policy provider.

The Agent C audit emits 29 violation messages because the `PRISMARI_DISCARD` defect is reported at two separate audit boundaries. Those 29 messages should not be described as 29 independent root causes.

## Cross-lane evidence mismatches

Several Agent B paths are engine-implemented while Agent C still reports the corresponding policy route as absent. These are not reasons to discard Agent B's work; they are exactly the links the integration coverage contract is meant to expose. Examples include kicker declaration, additional sacrifice selection, reveal-or-decline entry, color/mana choices, amass selection, counter-unless-pay decisions, Commander graveyard/exile return, and manifest face-up handling.

The strongest apparent contradiction is triggered targeting: Agent B correctly reports that the kernel now has an explicit fail-closed trigger-target bridge, while Agent C shows that at least one reachable targeted-trigger effect (`BOUNCE_TARGET`) still lacks production policy support. The integrated conclusion is therefore **kernel bridge implemented, policy coverage incomplete**, not “trigger targeting fully covered.”

## Agent D diagnostic boundary

Agent D remains diagnostic infrastructure only:

- 700 frozen seeds;
- production-equivalent game execution;
- fresh replay validation;
- `fail-fast: false` across shards;
- distinct-error collection; and
- explicit prevention of pilot measurement artifact creation.

Its existence is validation infrastructure, not interaction proof. A 700-seed run may expose additional gaps, but a green 700-seed run cannot by itself convert any of the 216 records to `PROVEN` without the required record-level evidence.

## Integrated CI evidence

On the reconciled tree, the interaction-surface job independently verifies the 216-record lock and manifest digest. The main CI has cleared formatting, lint, strict type checking, clean-engine boundaries, and the exact-deck Turn-10 production-policy/fresh-replay smoke in the integrated tree.

The interaction contract currently fails on the known policy gap `BOUNCE_TARGET`; its frozen-lock check passes. Agent C policy/replay conformance also remains intentionally red while substantive policy routes are missing. These red checks are evidence that the integration fails closed rather than hiding unresolved work.

## What must happen before the report can become `0 gaps`

The next proof pass must use the frozen 216-record surface and attach evidence by exact `record_id`. For every record, the aggregate ledger must answer, without inference:

- engine handler/support present and rules-correct;
- policy support present when the rules assign a strategic choice;
- replay support records and revalidates the exact decision;
- direct deterministic positive evidence exists;
- required negative/atomic evidence exists;
- fresh-process replay exists for Phase C-reachable choice paths; and
- no blocking engine or policy finding remains.

Only after those overlays are complete can the project truthfully publish a line in the intended form:

`216 requirements / 216 engine-supported / policy-supported everywhere required / 216 replay-supported / 216 directly tested / 0 gaps`

At this integration point, the truthful summary is:

`216 requirements / 216 inventoried / 173 policy-ready-or-not-required / 43 policy-replay-gap records / 10 engine blocker families / 26 unrouted strategic choice classes / 2 concrete policy defects / 0 of 216 records PROVEN`
