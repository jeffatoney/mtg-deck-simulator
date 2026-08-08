# Integration Coverage Report

**Status:** BLOCKED_NOT_PROVEN

**Integration branch:** `agent/integration-interaction-coverage`

## Executive result

The denominator is now explicit and frozen:

`216 requirements / 216 inventoried / 0 record-level PROVEN`

The 216 records are:

- 80 `CARD_COMPOSITION` records;
- 126 `CARD_EFFECT` records; and
- 10 `GLOBAL_RULE` records.

The frozen manifest SHA-256 is:

`sha256:20d767ea754841bf0f9bda378068c4c705e0b9f8f8f4be20ca15be1f24bb2cdc`

This integration does **not** claim `216 / 216 engine-supported / 216 / 216 replay-supported / 216 / 216 directly tested`, because the four source lanes did not produce record-addressable proof bundles. They were prevented from doing so by the coordinator's bootstrap zero lock. Converting broad implementation audits or passing repository tests into 216 per-record proof claims would recreate the exact coverage ambiguity this work is intended to eliminate.

The correct result at this point is therefore a frozen denominator plus explicit remaining evidence and implementation gaps.

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

The coordinator contract defines ten minimum global-rule records, but its bootstrap lock still declared seven global records, zero effect records, and zero total records. The deterministic generator reported the actual frozen surface as:

- 80 card-composition records;
- 126 card-effect records;
- 10 global-rule records;
- 216 total records.

The lock now contains those values and the generated manifest digest.

This was the single inherited failing repository test on Agent B's head. It was a coordinator/integration defect, not an Agent B engine regression.

### 2. Coordinator workflow Python contradiction — corrected

Both coordinator interaction workflows requested Python 3.11 while `pyproject.toml` requires Python 3.12. The workflows now request Python 3.12.

### 3. Agent D certification cannot be transplanted — resolved by omission

Agent D renewed `docs/audit/phase-b-certification/CERTIFICATION.json` for its standalone branch. That file is derived evidence bound to a specific covered tree. Once Agent D is combined with Agent B's kernel changes, that certificate is stale by definition.

The integration therefore preserves Agent D's executable work but does not copy its branch-specific certificate. The combined tree must generate and install a fresh Phase B certification candidate after its substantive checks pass.

## Cross-lane coverage matrix

| Coverage layer | Explicit denominator | Current integration evidence | Result |
|---|---:|---|---|
| Interaction inventory | 216 records | 216 deterministically generated and frozen | **216 / 216 mapped** |
| Record-level engine proof | 216 records | Agent B supplies implementation audit and focused tests, but no 216-record proof overlay | **0 / 216 record-attested** |
| Strategic policy/replay routes | 49 strategic `(timing, purpose, policy_class)` classes | Agent C has 23 reviewed routes and 26 unrouted classes | **23 / 49 routed** |
| Strategic provider/replay protocol | 4 provider methods | Production provider and recorded replay provider both implement all four | **4 / 4 method parity** |
| Record-level replay proof | 216 records | Replay invariants and Turn-10 fresh replay exist, but no per-record proof overlay | **0 / 216 record-attested** |
| Record-level direct-test proof | 216 records | Many focused/direct tests exist, but evidence is not attached by `record_id` | **0 / 216 record-attested** |
| Aggregate `PROVEN` ledger | 216 records | No frozen-surface proof bundles have yet been aggregated | **0 / 216 PROVEN** |

`0 / 216 record-attested` does **not** mean the engine, replay system, or tests support zero interactions. It means zero of the 216 frozen interaction records currently carry the record-addressable evidence required by the coordinator contract. That distinction is important: implementation may exist, but the proof denominator has not yet been populated.

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

Agent C inventories 49 strategic choice classes. Twenty-three have reviewed routes and twenty-six do not.

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

## What must happen before the report can become `0 gaps`

The next proof pass must use the now-frozen 216-record surface and attach evidence by exact `record_id`. For every record, the aggregate ledger must answer, without inference:

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

`216 requirements / 216 inventoried / 23 of 49 strategic choice classes routed / 4 of 4 strategic replay-provider methods mirrored / 10 engine blocker families / 26 unrouted strategic choice classes / 2 concrete policy defects / 0 of 216 records PROVEN`
