# Integration Coverage Report

**Status:** BLOCKED_PROVISIONAL_SURFACE

**Integration branch:** `agent/integration-interaction-coverage`

## Executive result

The repository currently emits a deterministic **candidate** surface:

`216 candidate requirements / 216 inventoried / 173 policy-ready-or-not-required / 43 policy-replay-gap records / 16 Agent A findings pending / 0 record-level PROVEN`

The 216 candidate records are:

- 80 `CARD_COMPOSITION` records;
- 126 `CARD_EFFECT` records; and
- 10 `GLOBAL_RULE` records.

Candidate manifest SHA-256:

`sha256:20d767ea754841bf0f9bda378068c4c705e0b9f8f8f4be20ca15be1f24bb2cdc`

This digest is **not frozen**. Agent A reviewed the exact 100-card deck and identified 16 accepted findings that can alter the record set, choice taxonomy, actors, timing, dependencies, and digest. The candidate remains provisional until each finding is implemented, mapped to an equivalent verified record, or rejected with explicit Comprehensive Rules authority and direct evidence.

Of the current 216 candidate records, 94 contain at least one strategic choice and 122 require no strategic policy. Fifty-one of the 94 strategic records currently have complete reviewed routes with live production-policy/replay support; 43 have at least one route or support gap. These values describe only the current provisional candidate and must be recomputed after Agent A integration.

## Source lanes reconciled

| Lane | Source | Integrated treatment |
|---|---|---|
| Agent A / definitive deck interaction inventory | Artifact digest `sha256:212b58f87e0b3082d0851becbf63b8c4298bb11338da33a4cbf6b303e12db90b` | Imported, digest-verified, and represented by a 16-finding adjudication ledger. All 16 findings are accepted pending implementation. |
| Coordinator / candidate interaction inventory | PR #88, head `0a6e90d6a0346b837986bfe54ac5e676f22bd5c4` | Preserved as the generator and contract foundation. Its 216-record output is now explicitly provisional. |
| Agent B / engine + rules conformance | PR #91, head `8447444dc6b40f9315c99f5e153bd21166d3341b` | Engine/rules changes and focused tests preserved. |
| Agent C / policy + replay conformance | PR #90, head `490960781ba8770cf5e0e9ac4f7bd69e58f5ae4a` | Registry, audit, workflow, and tests preserved, subject to integration corrections that prevent a provisional lock from being reported as frozen. |
| Agent D / pre-pilot diagnostics | PR #89, head `751b98b33bf8556d28c96ee4bec990b2e0ff8429` | Diagnostic workflow, runner, Phase B covered-path update, and tests preserved byte-for-byte. Branch-specific derived certification was not transplanted. |

## Independent-verification defects closed

### D1 — headline status was unguarded

Closed. The derived checker now compares the committed ledger's top-level `status` and surface candidate status against recomputed values.

### D2 — coverage fields and blockers were partially unchecked

Closed. The checker validates the exact coverage key set and every value, including:

- engine blocker count and blocker list;
- live policy defect count and concrete defect lists;
- no-policy-required records;
- reviewed strategic classes;
- required/production/replay protocol-method counts; and
- Agent A total, complete, and pending findings.

### D3 — pytest did not validate the committed ledger

Closed. The reconciliation suite calls the same ledger checker used by CI and includes adversarial mutations for the headline status, previously unchecked fields, and blocker list.

The current checker verifies 44 report fields. The CI ledger step passes with zero mismatches.

## Agent A adjudication

All 16 Agent A findings are currently:

`ACCEPTED / PENDING IMPLEMENTATION`

The accepted set includes:

- Izzet Boilerworks resolution-time land selection rather than targeting;
- Sentinel Totem self-exile as an activation cost;
- Scavenger Grounds one-Desert sacrifice cost;
- mandatory Vedalken Aethermage Sliver targeting;
- role-specific Prismari Command targets and target-player discard ownership;
- contextual manifest controller ownership for Reality Shift;
- Fact or Fiction opponent selection;
- fixed self-discard for cycling/typecycling/transmute;
- distinct delayed/generated-trigger records;
- Electroduplicate's copiable token ability;
- omitted global exact-deck rules;
- Frostboil Snarl reveal identity;
- X/target-count dependency;
- Twinflame target-count/strive-cost dependency;
- generated Treasure ability ownership; and
- keyword/static/permission composition evidence.

No finding may disappear. The integration checker requires the imported Agent A artifact digest and the adjudication finding IDs to match exactly.

## Cross-lane candidate coverage matrix

| Coverage layer | Candidate denominator | Current evidence | Result |
|---|---:|---|---|
| Candidate interaction inventory | 216 records | Deterministically generated; candidate lock matches | **216 / 216 mapped, provisional** |
| Agent A disposition | 16 findings | All accepted; none completed | **0 / 16 complete** |
| Record-level engine proof | 216 candidate records | No record-addressable proof overlay | **0 / 216 attached** |
| Strategic policy requirement | 216 candidate records | 94 require strategic policy; 122 do not | **94 require / 122 not required** |
| Record-level policy/replay route completeness | 94 strategic candidate records | 51 currently complete | **51 / 94** |
| Policy-ready or not required | 216 candidate records | 122 + 51 | **173 / 216** |
| Strategic choice occurrences | 145 occurrences | 98 reviewed routes; 96 live-supported | **98 / 145 routed; 96 / 145 supported** |
| Strategic policy/replay classes | 49 classes | 23 reviewed; 26 unrouted | **23 / 49** |
| Strategic provider/replay protocol | 4 methods | Production and replay providers implement all four | **4 / 4 parity** |
| Record-level replay proof | 216 candidate records | No record-addressable proof overlay | **0 / 216 attached** |
| Record-level direct-test proof | 216 candidate records | No record-addressable proof overlay | **0 / 216 attached** |
| Aggregate `PROVEN` ledger | 216 candidate records | No proof bundles aggregated | **0 / 216 PROVEN** |

These numerators are useful diagnostics, not a final denominator certification.

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

## Remaining policy/replay defects from Agent C

- runtime purpose `PRISMARI_DISCARD` lacks production policy support; and
- targeted-trigger effect `BOUNCE_TARGET` lacks production trigger-target policy support.

The current interaction suite completes **29 passed / 1 failed**. The sole failure is the known `BOUNCE_TARGET` defect. The broader integrated suite previously completed **357 passed / 1 failed** on the same defect. Formatting, lint, strict type checking, Phase A verification, and the exact-deck Turn-10 production-policy/fresh-replay smoke passed before that failure.

## Certification boundary

A fresh Phase A CI candidate was generated and validated on the integrated tree before the full test failure. Durable certification closeout is not complete. Phase B verification/certification did not run because the full suite failed first. Both final certifications must be renewed after the provisional surface is corrected and all blocking checks pass.

## Required sequence to freeze the denominator

1. Implement or rules-authoritatively resolve all 16 Agent A findings.
2. Regenerate the interaction manifest without preserving 216 as a target.
3. Recompute the manifest digest and every strategic/policy/replay numerator.
4. Mark the lock `FROZEN_REVIEWED` only after the adjudication ledger has zero pending findings.
5. Attach engine, policy where required, replay, positive/negative test, and fresh-process replay evidence by exact final `record_id`.
6. Clear all engine and policy blockers.
7. Renew Phase A and Phase B certifications from CI on the final integrated tree.

Only then may the repository publish a line in the intended form:

`N requirements / N engine-supported / policy-supported everywhere required / N replay-supported / N directly tested / 0 gaps`

Current truthful summary:

`216 provisional candidate requirements / 216 inventoried / 173 policy-ready-or-not-required / 43 policy-replay-gap records / 10 engine blocker families / 2 concrete policy defects / 16 Agent A findings pending / 0 candidate records PROVEN`
