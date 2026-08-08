# Agent B — Engine / Rules Conformance Audit

**Branch:** `agent/engine-rules-conformance`

**Coordinator dependency:** The interaction coverage lock on the branch is still a bootstrap placeholder with a zero manifest digest. This document is therefore an implementation audit, not a proof bundle and not a claim that any frozen interaction record is `PROVEN`.

## Scope

Agent B examines rules-engine legality, timing, execution, rollback, and replay-facing choice ownership for the exact-deck interaction contract. Strategic valuation is outside scope. Where the Comprehensive Rules require a player choice and the production engine has no rules-correct interface for receiving it, the result is a blocker rather than an engine-selected default.

Rules references below use the repository's supplied Comprehensive Rules dated 2026-06-19.

## Executive result

**Current answer: NO. The engine does not yet provide rules-correct legality and execution support for every interaction class identified by the coordinator schema.**

The existing engine has strong atomicity, target validation, stack/priority, object-identity, search, and many effect-execution paths. The interaction-level contract nevertheless exposes several gaps that card-level `IMPLEMENTED` status did not detect.

This Agent B branch closes three rules-semantic gaps that do not require a strategic preference:

1. represented kicker costs now require an explicit boolean declaration during cast proposal;
2. reveal-or-enter-tapped lands now require an explicit reveal-or-decline replacement choice; and
3. qualifying-permanent sacrifice costs now require an explicit permanent selection, including the legal Scavenger Grounds case where another Desert is sacrificed and the source remains.

The remaining blockers below must not be hidden behind deterministic defaults.

## Structural choice audit

| Interaction class | Engine status | Agent B assessment |
|---|---|---|
| Cast path / face / ordinary mode | Implemented | General cast path and ordinary modal spell selection are validated before payment. Compound modal handling such as Prismari Command remains separately blocked below. |
| Spell target selection | Implemented for ordinary target schemas | Core cast validates target count, uniqueness, and legality before costs. Special compound targets such as Prismari Command bypass the ordinary action target path and remain blocked. |
| Variable target count tied to X | Implemented | Phase B cast wrapper requires target count to equal X for represented effects. |
| X declaration | Partial | `x_value` is part of the cast action and cost, but the public API still defaults omitted X to zero. The coordinator contract forbids silently converting an omitted rules choice into an engine default. |
| Kicker declaration | **Corrected on Agent B branch** | Rule 601.2b requires the additional-cost choice while casting. Represented kicker effects now reject an omitted or non-boolean declaration atomically. |
| Additional sacrifice selection | **Corrected on Agent B branch for represented qualifying-subtype costs** | Rule 601.2h / 602.2b cost payment may require choosing which permanent to sacrifice. Scavenger Grounds no longer means “always sacrifice the source.” |
| Hybrid-cost configuration | **Blocking** | `pay_mana()` recursively takes the first available hybrid option. Rule 601.2b requires the hybrid configuration choice during casting/activation. |
| Exact mana-payment configuration | **Blocking** | Generic payment spends mana in a fixed `C, W, U, B, R, G` order. Rules 601.2g-h and 118.3 permit legally distinct payment configurations; the engine may not silently select one when it can affect state or future choices. |
| Discard-cost identity | Implemented where a choice exists | Battlefield activations require explicit `discard_ids`; cycling/transmute correctly discard their own source because the cost identifies that card rather than offering a free identity choice. |
| Optional triggered effect decision | **Blocking** | Current trigger code requires and records the `may` decision while putting the trigger on the stack. Rule 608.2d places choices not made on announcement/stack placement at resolution. |
| Trigger target selection | Implemented with fail-closed policy bridge | Trigger targets are chosen at trigger stacking and validated by the kernel. Ambiguous cases require an explicit/bridged choice rather than a first-target default. Final proof remains coordinator-dependent. |

## Effect-specific choice audit

| Effect family | Engine status | Agent B assessment |
|---|---|---|
| Chosen mana color / commander color / pain-land color | Implemented | Explicit legal color is required and validated. |
| Filter-mana option | Implemented | Exact configured option must be selected; unlisted options fail closed. Hybrid input payment to the filter ability is still part of the global mana-payment blocker. |
| Amass Army choice | Implemented | Engine creates an Army when none exists, uses the only Army when unique, and requires explicit selection when multiple legal Armies exist. |
| Scry 1 | **Blocking** | Base `SCRY` uses `bool(choices.get("scry_to_bottom", False))`, which silently chooses top when absent. Several trigger paths also carry a future scry decision forward from an earlier action rather than obtaining it at resolution. |
| Counter unless pay | Implemented | Target controller's pay/decline choice is explicit, actor-anchored, and recorded at resolution. Global exact mana-payment configuration remains a separate blocker. |
| Arcane Denial delayed draw count | Implemented | The eligible player explicitly chooses 0–2 at delayed-trigger resolution. |
| Copy spell / choose new targets | Implemented | Original decisions are copied; optional new targets are generated from legal candidates and validated when the copying effect permits them. |
| Fact or Fiction split and pile | Implemented through strategic-choice boundary | Kernel enumerates legal piles; policy values only legal options; choices are recorded. Strategic quality is outside Agent B scope. |
| Stated-quality searches | Implemented | Transmute, typecycling, and basic-land searches support legal fail-to-find behavior under rule 701.23b. |
| Long-Term Plans unrestricted search | Implemented | Requires a selection when the library is nonempty, matching rule 701.23d. |
| Look/select/rest-bottom ordering | Implemented through legal candidate selection | Card selection and bottom ordering are explicit and validated. |
| Draw/discard and untap selection | Implemented through legal candidate selection | Resolution-time candidate/count validation is fail closed. |
| Reveal-or-enter-tapped land | **Corrected on Agent B branch** | Omission no longer silently means decline. Explicit `None` records a decline; a supplied object must be a legal reveal. |
| Prismari Command modes and targets | **Blocking** | Choices are currently validated and recorded inside resolution. Rules 601.2b-c require modes and targets while casting. The spell also bypasses ordinary target revalidation, so one illegal target at resolution can produce an `IllegalAction` instead of resolving remaining legal portions. |
| Manifest face-up special action | **Blocking** | Reality Shift creates the correct face-down manifested permanent, but no production special-action interface turns a manifested creature card face up when legally permitted. The schema explicitly identifies this interaction. |
| Scavenger Grounds additional Desert sacrifice | **Corrected on Agent B branch** | Explicit controlled-Desert selection is required; the selected Desert, not automatically the source, is sacrificed as the activation cost. |

## Global-rule interaction audit

| Frozen global interaction | Status | Findings |
|---|---|---|
| `GLOBAL-TRIGGER-ORDERING` | **Blocking** | APNAP controller grouping exists, but multiple simultaneous triggers controlled by one player are silently ordered by insertion order. Rule 603.3b requires that player to choose their relative order. |
| `GLOBAL-REPLACEMENT-ORDERING` | **Blocking / not proven** | The engine has individual replacement handlers, but there is no general rule-616.1 affected-player/controller chooser. Umbra Armor helper selection illustrates the first-applicable style that cannot serve as general proof. |
| `GLOBAL-COST-PAYMENT` | **Blocking** | Hybrid and generic payment configuration are still deterministic engine preferences rather than explicit legal choices. |
| `GLOBAL-CLEANUP-REENTRY` | **Blocking** | First cleanup accepts explicit discard identities and the engine creates the rule-514.3a priority exception, but the subsequent cleanup is invoked with `discard_ids=()`. A second maximum-hand-size discard choice therefore has no production interface. |
| `GLOBAL-COMBAT-ATTACKERS` | Partial | Attacker declarations are explicit and validated atomically for opponent destinations. The global contract also covers all legal attack destinations; planeswalker/battle destination support is not general. |
| `GLOBAL-ILLEGAL-ACTION-ROLLBACK` | Implemented broadly | Cast, activation, priority resolution, cleanup, and other core actions use atomic snapshots and rollback on failure. Focused Agent B tests add negative atomic cases for the corrected choice classes. |
| `GLOBAL-SBA-TIMING` | **Blocking** | Resolution-depth suppression correctly prevents normal SBAs during effect resolution, but the legend-rule choice required by rule 704.5j is not implemented as a general explicit choice. |
| `GLOBAL-COMMANDER-GRAVEYARD-EXILE-RETURN` | Implemented | Commander movement through graveyard/exile is real, followed by an explicit owner choice during SBA processing under rule 903.9a. Final proof remains coordinator-dependent. |
| `GLOBAL-COMMANDER-HAND-LIBRARY-REPLACEMENT` | **Blocking** | Commit/Memory contain card-path-specific commander replacement handling, but ordinary engine-wide hand/library movement does not have a general rule-903.9b replacement-choice service. |
| `GLOBAL-PRIORITY-STACK-LIFO` | Implemented | Direct stack resolution is forbidden; stack resolves only after the required priority passes and uses the top stack object. Final proof remains coordinator-dependent. |

## Focused tests added by Agent B

`tests/interaction_coverage/test_engine_rules_conformance.py` adds deterministic production-path checks for:

- omitted kicker declaration fails atomically at cast proposal;
- omitted reveal-or-decline land-entry choice fails atomically;
- omitted qualifying-permanent sacrifice choice fails atomically; and
- Scavenger Grounds can sacrifice another legal Desert while the source survives, after which the activated ability resolves normally.

The existing Scavenger Grounds runtime test is also changed to make its legal choice to sacrifice Scavenger Grounds itself explicit.

## Rules authority for the Agent B corrections

- **601.2b:** mode, alternative/additional-cost, X, and hybrid configuration choices are made while casting.
- **601.2c:** spell targets and variable target count are chosen while casting.
- **601.2g-h / 602.2b:** mana abilities and cost payment choices occur in the rules-defined payment process for spells and activated abilities.
- **603.3b-d:** simultaneous trigger ordering and triggered targets are chosen as those triggers are put on the stack.
- **608.2d:** effect choices not already made on casting/activation/stack placement are made during resolution.
- **614.12a / 616.1:** relevant entry/replacement choices occur before entry and competing replacement effects use the affected-player/controller choice process.
- **704.5j:** the legend rule requires an explicit keep choice.
- **733.1:** illegal actions are reversed in their entirety.
- **903.9a-b:** Commander graveyard/exile return is an optional SBA; hand/library movement uses an optional replacement effect.

## Agent B handoff state

Do **not** mark the interaction surface `PROVEN` from this branch. The coordinator lock is not frozen, and the blockers above are material. The next kernel work should prioritize the global choice services in this order:

1. explicit mana/hybrid payment configuration;
2. trigger ordering and optional-trigger resolution timing;
3. general replacement-order and commander hand/library replacement handling;
4. cleanup re-entry discard interface and legend-rule choice;
5. Prismari Command cast-time compound mode/target representation and revalidation; and
6. manifest face-up special action.

No item in that list should be resolved by adding a first/legal/default strategic preference to the engine.
