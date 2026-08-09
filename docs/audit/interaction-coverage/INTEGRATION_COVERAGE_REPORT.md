# Integration Coverage Report

**Status:** BLOCKED_PROVISIONAL_SURFACE

**Integration branch:** `agent/integration-interaction-coverage`

## Executive result

The repository currently emits a deterministic **candidate** surface:

`216 candidate requirements / 216 inventoried / 174 policy-ready-or-not-required / 42 policy-replay-gap records / 16 Agent A findings formally pending / 0 record-level PROVEN`

The 216 candidate records are:

- 80 `CARD_COMPOSITION` records;
- 126 `CARD_EFFECT` records; and
- 10 `GLOBAL_RULE` records.

Candidate manifest SHA-256:

`sha256:f976526e34d7297521b9c949c7e3a54905cb8bdaa62e7e3225627de294f8a6b5`

The reserved frozen digest remains all zeroes. The candidate is **not frozen**.

Agent A identified 16 accepted findings that may alter the record set, choice taxonomy, actors, timing, dependencies, and digest. Four findings (`A-BLOCK-001` through `A-BLOCK-004`) now have implementation and direct-test changes in this branch, but they remain formally pending until the synchronized tree passes CI and the adjudication ledger is advanced. The other twelve findings remain pending implementation or authoritative resolution.

## Current candidate policy/replay cross-reference

Of the current 216 candidate records:

- 94 contain at least one strategic choice;
- 122 require no strategic policy;
- 52 of the 94 strategic records currently have complete reviewed routes with live support;
- 42 strategic records have at least one missing reviewed route;
- 174 of 216 are policy-ready or require no strategic policy;
- 144 strategic choice occurrences exist;
- 98 of 144 have reviewed routes and all 98 of those have current live support;
- 49 strategic choice classes exist: 24 reviewed, 25 unrouted;
- both previously concrete live policy-handler defects are closed; and
- strategic provider/replay protocol parity remains 4 of 4 methods.

These values describe the current provisional candidate only. They are not a final denominator certification.

## Source lanes reconciled

| Lane | Source | Integrated treatment |
|---|---|---|
| Agent A / definitive deck interaction inventory | Artifact digest `sha256:212b58f87e0b3082d0851becbf63b8c4298bb11338da33a4cbf6b303e12db90b` | Imported, digest-verified, and represented by a 16-finding adjudication ledger. |
| Coordinator / candidate interaction inventory | PR #88, head `0a6e90d6a0346b837986bfe54ac5e676f22bd5c4` | Preserved as the generator and contract foundation; its output is explicitly provisional. |
| Agent B / engine + rules conformance | PR #91, head `8447444dc6b40f9315c99f5e153bd21166d3341b` | Engine/rules changes and focused tests preserved and extended only through explicit integration review. |
| Agent C / policy + replay conformance | PR #90, head `490960781ba8770cf5e0e9ac4f7bd69e58f5ae4a` | Registry/audit/workflow/tests preserved with reviewed pin refreshes for integration changes. |
| Agent D / pre-pilot diagnostics | PR #89, head `751b98b33bf8556d28c96ee4bec990b2e0ff8429` | Diagnostic executable work preserved; branch-specific derived certification was not transplanted. |

## Independent-verification defects closed

### D1 — headline status was unguarded

Closed. The derived checker compares the committed ledger's top-level `status` and surface candidate status against recomputed values.

### D2 — coverage fields and blockers were partially unchecked

Closed. The checker validates the exact coverage key set and every covered value, including blocker lists, policy defects, protocol counts, and Agent A disposition.

### D3 — pytest did not validate the committed ledger

Closed. The reconciliation suite invokes the same ledger checker used by CI. The adversarial mutation test now derives a value guaranteed to differ from the baseline, so no mutation can be vacuous simply because the true value is already zero.

The Agent C byte pin was also refreshed after the reviewed conformance-test and registry changes. The stale-pin failure is no longer being suppressed or bypassed.

## Unrequested export machinery removed

Two temporary development mechanisms were removed from this PR:

- the whole-repository source snapshot upload from `interaction-surface.yml`; and
- `.github/workflows/integration-dev-environment.yml`, which packaged and uploaded a built `.venv`.

Neither mechanism is required by the interaction-coverage contract.

## Agent A implementation status

### Implemented in the current slice, pending synchronized CI adjudication

1. **A-BLOCK-001 — Izzet Boilerworks**
   - ETB no longer targets a land.
   - The controlled-land choice occurs during resolution through an explicit strategic card-selection request.
   - Direct evidence checks the recorded choice timing.

2. **A-BLOCK-002 — Sentinel Totem**
   - Activation now represents tap + self-exile as the cost.
   - The source reaches exile before the activated ability resolves.

3. **A-BLOCK-003 — Scavenger Grounds**
   - Activation now pays exactly one `Desert` sacrifice.
   - The source itself may be chosen, or another controlled Desert may be chosen.
   - The prior source-plus-extra-Desert representation is removed.

4. **A-BLOCK-004 — Vedalken Aethermage**
   - The ETB target cardinality is exactly one Sliver.
   - When no legal Sliver exists, the targeted trigger is removed during trigger stacking.

Formal adjudication still reports **0 / 16 complete** until the synchronized branch checks pass. This prevents implementation intent from being promoted to verified completion.

### Still pending after this slice

`A-BLOCK-005` through `A-BLOCK-010` and `A-REV-011` through `A-REV-016` remain pending.

## Cross-lane candidate coverage matrix

| Coverage layer | Candidate denominator | Current repository value |
|---|---:|---:|
| Candidate interaction inventory | 216 | **216 mapped, provisional** |
| Agent A disposition | 16 findings | **0 complete / 16 pending** |
| Record-level engine proof | 216 | **0 attached** |
| Strategic policy requirement | 216 | **94 require / 122 not required** |
| Strategic route completeness | 94 strategic records | **52 complete / 42 gap** |
| Policy-ready or not required | 216 | **174 / 216** |
| Strategic choice occurrences | 144 | **98 routed / 98 live-supported** |
| Strategic policy/replay classes | 49 | **24 reviewed / 25 unrouted** |
| Strategic provider/replay protocol | 4 | **4 / 4 parity** |
| Record-level replay proof | 216 | **0 attached** |
| Record-level direct-test proof | 216 | **0 attached** |
| Aggregate `PROVEN` ledger | 216 | **0 / 216 PROVEN** |

## Remaining engine/rules blockers from Agent B

1. hybrid and exact/generic mana-payment configuration;
2. simultaneous same-controller trigger ordering;
3. optional-trigger decision timing;
4. general replacement-effect ordering;
5. cleanup re-entry discard selection;
6. legend-rule keep choice;
7. Commander hand/library replacement choice;
8. generic resolution-time scry choice ownership;
9. compound retarget metadata for copied Prismari Command spells; and
10. global attack destinations beyond opponent players.

## Remaining policy/replay work

There are currently **no concrete missing live policy handlers** among reviewed routes: `BOUNCE_TARGET` and `PRISMARI_DISCARD` are both supported.

The policy/replay lane is nevertheless still blocking because **25 strategic choice classes have no reviewed route**. The newly explicit Scavenger Grounds `SACRIFICE_PERMANENT_SELECTION` is intentionally among those unrouted classes until production policy/replay ownership is reviewed rather than inferred.

## Certification and CI boundary

The candidate digest above was independently reproduced by GitHub Actions before the lock was advanced. The synchronized tree containing the updated lock, ledger, integration pins, and direct tests must still pass its checks before `A-BLOCK-001` through `A-BLOCK-004` can be marked `IMPLEMENTED_VERIFIED`.

No Phase A or Phase B durable certification is claimed from this provisional slice. Certifications must be renewed only after the final integrated tree is stable and blocking checks pass.

## Required sequence to freeze the denominator

1. Implement or rules-authoritatively resolve all 16 Agent A findings.
2. Regenerate the interaction manifest without preserving 216 or 244 as a target.
3. Recompute the manifest digest and every strategic/policy/replay numerator.
4. Mark the lock `FROZEN_REVIEWED` only after the adjudication ledger has zero pending findings and independent freeze review agrees.
5. Attach engine, policy where required, replay, positive/negative test, and fresh-process replay evidence by exact final `record_id`.
6. Clear all engine and policy blockers.
7. Renew Phase A and Phase B certifications from CI on the final integrated tree.

Only then may the repository publish a line in the intended form:

`N requirements / N engine-supported / policy-supported everywhere required / N replay-supported / N directly tested / 0 gaps`

Current truthful summary:

`216 provisional candidate requirements / 216 inventoried / 174 policy-ready-or-not-required / 42 policy-replay-gap records / 10 engine blocker families / 25 unrouted strategic classes / 0 live policy-handler defects / 16 Agent A findings formally pending / 0 candidate records PROVEN`
