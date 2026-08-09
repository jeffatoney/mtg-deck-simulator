# Agent B — Engine / Rules Conformance Audit

**Branch:** `agent/engine-rules-conformance`

**Coordinator dependency:** the interaction-coverage lock is still a bootstrap placeholder with a zero manifest digest/count. This is therefore an implementation audit and kernel handoff, not a frozen proof bundle and not a claim that any interaction record is `PROVEN`.

## Scope

Agent B examines rules-engine legality, timing, execution, rollback, and replay-facing choice ownership for the exact-deck interaction contract. Strategic valuation is outside scope. When the Comprehensive Rules require a player choice and the production engine has no rules-correct interface for receiving it, Agent B reports a blocker instead of inserting a deterministic engine preference.

Rules references use the repository-supplied Comprehensive Rules dated 2026-06-19.

## Executive result

**Current answer: NO. The engine does not yet provide rules-correct legality and execution support for every interaction class emitted by the coordinator schema.**

The interaction-level audit nevertheless closes several rules defects that card-level `IMPLEMENTED` status did not expose. On this branch:

1. multi-face cast paths must be explicit;
2. variable target-count declarations must be explicit, including an explicit zero-target choice;
3. represented X values must be explicit, including X = 0;
4. represented kicker choices must be explicit at cast proposal;
5. reveal-or-enter-tapped lands require an explicit reveal-or-decline replacement choice, and the broker now represents decline explicitly;
6. qualifying-permanent sacrifice costs require an explicit qualifying permanent and are paid in the activation cost-payment sequence;
7. Reality Shift manifests now have a rules-defined, replayable face-up special action for manifested creature cards; and
8. Prismari Command modes/targets are chosen and validated at cast proposal, with resolution-time target revalidation so remaining legal modes still resolve.

The remaining blockers below require general player-choice services or broader kernel architecture. They must not be hidden behind “first legal,” fixed color-order, insertion-order, or other engine defaults.

## Structural interaction audit

| Schema interaction | Status | Agent B assessment |
|---|---|---|
| `CAST_PATH` | **Corrected on Agent B branch** | A physical card with multiple faces now rejects an omitted face selection. Ordinary same-face spell modes already reject an omitted mode when more than one spell mode exists. |
| `TARGET_COUNT` | **Corrected on Agent B branch** | A spell whose target schema permits multiple legal counts now distinguishes an omitted declaration from an explicit empty target tuple. Core target count/uniqueness legality is still validated before costs. |
| `TARGET_SELECTION` | Implemented for ordinary schemas | Core casting/activation validates target count, uniqueness, visibility/rules predicates, and legality before cost mutation. Prismari's compound target representation is corrected separately below. |
| `X_VALUE` | **Corrected on Agent B branch** | Represented X spells reject an omitted X rather than silently using zero. X = 0 remains legal when explicitly declared. |
| `KICKER_DECLARATION` | **Corrected on Agent B branch** | Represented kicker effects require an explicit boolean declaration while casting; omission fails atomically. |
| `ADDITIONAL_SACRIFICE_SELECTION` | **Corrected for represented qualifying-subtype costs** | Scavenger Grounds now requires a controlled Desert selection, pays that exact permanent during activation cost payment, and permits another Desert to be sacrificed while the source remains. |
| `HYBRID_COST_CONFIGURATION` | **Blocking** | `pay_mana()` recursively takes the first payable hybrid option. Rule 601.2b requires the hybrid-symbol configuration to be chosen while casting. |
| `ALTERNATIVE_COST_DECLARATION` | Implemented for represented spell modes | Flashback/foretell/other represented cast permissions are selected through explicit spell modes and validated against zone/timing permissions. This does not cure the global mana-payment blocker. |
| `DISCARD_COST_CARD_IDENTITY` | Implemented where the cost offers a choice | Battlefield activations require explicit `discard_ids`. Cycling/transmute discard the source because the rules cost identifies that card rather than offering an identity choice. |
| `OPTIONAL_EFFECT_DECISION` | **Blocking** | Optional triggered effects currently consume the `may` decision while the trigger is being put on the stack. Choices not made during casting/activation/trigger stacking belong at resolution under rule 608.2d. |

## Effect-specific interaction audit

| Effect / choice family | Status | Agent B assessment |
|---|---|---|
| Chosen mana color / commander color / pain-land color | Implemented | Required color choices are explicit and validated against the effect's legal colors. |
| Filter-mana option | Implemented locally | The output option is explicit and validated. The mana spent to pay the filter cost remains subject to the global exact-payment blocker. |
| Amass Army selection | Implemented | The engine creates an Army when none exists, uses the only Army when unique, and requires explicit selection when multiple legal Armies exist. |
| Scry | **Blocking** | Generic `SCRY` still interprets missing `scry_to_bottom` as `False`, silently choosing “top.” Some triggered scry paths also carry the future decision from an earlier action rather than requesting it at resolution. |
| Counter unless pay | Implemented locally | The targeted player's pay/decline decision is explicit, actor-anchored, recorded, and made during resolution. Exact mana composition remains a global blocker. |
| Arcane Denial delayed draw count | Implemented | The eligible player explicitly chooses 0–2 at delayed-trigger resolution. |
| Ordinary spell copying / choose new targets | Implemented for ordinary target schemas | Existing copy handling preserves copied decisions and validates optional new targets. **Prismari Command copied-spell mode-to-target association remains a blocker** because its compound metadata is not yet generalized through copy retargeting. |
| Fact or Fiction split / pile | Implemented through strategic-choice boundary | Kernel enumerates legal pile choices and records them; policy may value those legal choices. Strategic quality is outside Agent B scope. |
| Stated-quality searches / fail to find | Implemented | Transmute, typecycling, and represented basic-land searches support the legal stated-quality fail-to-find case. |
| Unrestricted search requiring a card | Implemented | Long-Term Plans requires a selection when the library is nonempty. |
| Look / select / rest-bottom ordering | Implemented through legal-candidate selection | Selection count and bottom ordering are explicit and validated. |
| Draw/discard and untap selection | Implemented through legal-candidate selection | Resolution-time candidate/count legality is fail closed. |
| Reveal-or-enter-tapped land | **Corrected on Agent B branch** | Omission is illegal. Explicit `None` means decline; a supplied reveal object must satisfy the legal subtype/zone requirements. The broker exposes the decline as an explicit internal choice without leaking raw IDs publicly. |
| Prismari Command modes / targets | **Corrected for base spell casting and resolution** | Exactly two distinct modes and their mode-associated targets are fixed at cast proposal. Targets are revalidated at resolution; an illegal target suppresses only its affected mode when another targeted mode remains legal. |
| Prismari Command copied-spell retargeting | **Blocking** | The compound `mode -> target` association is not yet a general copied-spell target interface, so the base-spell correction is not enough to certify every Prismari copy interaction. |
| Manifest face-up special action | **Corrected on Agent B branch** | A controlled face-down manifested creature card may be turned face up as a special action for its mana cost while the controller has priority. Noncreature manifests reject the action atomically. Replay support is included. |
| Scavenger Grounds additional Desert sacrifice | **Corrected on Agent B branch** | The exact chosen controlled Desert is sacrificed during activation cost payment; the engine no longer aliases “sacrifice a Desert” to “sacrifice this source.” |
| Trigger target selection | Implemented with fail-closed strategic bridge | Trigger targets are chosen as triggers are stacked, validated by the kernel, recorded, and ambiguous cases require an explicit provider choice rather than a first-target default. Final record proof remains coordinator-dependent. |

## Global interaction audit

| Coordinator global interaction | Status | Findings |
|---|---|---|
| `GLOBAL-TRIGGER-ORDERING` | **Blocking** | APNAP controller grouping exists, but multiple simultaneous triggers controlled by one player retain insertion order. Rule 603.3b requires that player to choose their relative order. |
| `GLOBAL-REPLACEMENT-ORDERING` | **Blocking** | Individual replacement handlers exist, but there is no general rule-616.1 affected-player/controller chooser when multiple replacement/prevention effects are applicable. |
| `GLOBAL-COST-PAYMENT` | **Blocking** | Hybrid configuration and generic mana composition are deterministic engine preferences. Generic payment uses a fixed color order instead of an explicit legal payment configuration. A general player-controlled mana-ability/payment sequence is also absent. |
| `GLOBAL-CLEANUP-REENTRY` | **Blocking** | The first cleanup accepts explicit discard identities and correctly creates the rule-514.3a priority exception. After that priority window, `pass_priority` starts the next cleanup with an empty discard selection, so a second maximum-hand-size discard decision has no production choice interface. |
| `GLOBAL-COMBAT-ATTACKERS` | Partial | Attacker declarations and opponent destinations are explicit and atomically validated. The global rules surface does not generally represent attack destinations such as planeswalkers/battles. |
| `GLOBAL-ILLEGAL-ACTION-ROLLBACK` | Implemented broadly | Core cast, activation, priority resolution, cleanup, and Agent B fail-closed choice checks use atomic snapshots/rollback. Focused negative tests verify no mutation on rejected X, cast path, target count, kicker, land replacement, sacrifice, and manifest actions. |
| `GLOBAL-SBA-TIMING` | **Blocking** | Resolution-depth suppression prevents ordinary SBAs during effect resolution, but the legend-rule keep choice required by rule 704.5j is not implemented as a general explicit player choice. |
| `GLOBAL-COMMANDER-GRAVEYARD-EXILE-RETURN` | Implemented | Graveyard/exile movement occurs first and is followed by the explicit owner choice during SBA processing required by rule 903.9a. Final record proof remains coordinator-dependent. |
| `GLOBAL-COMMANDER-HAND-LIBRARY-REPLACEMENT` | **Blocking** | Some card paths contain commander-aware movement handling, but ordinary engine-wide hand/library movement lacks a general rule-903.9b optional replacement-choice service. |
| `GLOBAL-PRIORITY-STACK-LIFO` | Implemented | Direct stack resolution is prohibited; the top stack object resolves only after all required priority passes. |

## Focused Agent B tests

`tests/interaction_coverage/test_engine_rules_conformance.py` now exercises production paths for:

- omitted X declaration versus explicit X = 0;
- omitted split-card face versus explicit face 0;
- omitted variable target-count declaration versus explicit zero targets;
- omitted kicker declaration;
- omitted reveal-or-decline land-entry choice and explicit decline;
- omitted qualifying-permanent sacrifice choice;
- Scavenger Grounds sacrificing another Desert while the source survives;
- manifested creature face-up special action plus replay; and
- atomic rejection of the manifest face-up action for a noncreature card.

Existing exact-deck runtime tests are also tightened for:

- explicit Scavenger Grounds source-sacrifice selection;
- explicit Frostboil Snarl decline;
- Prismari Command cast-time modes/targets; and
- Prismari Command resolution when one mode's target becomes illegal before resolution.

## Rules authority

- **601.2b:** card face/mode, alternative/additional-cost decisions, X, and hybrid configuration are fixed while casting.
- **601.2c:** target count and targets are chosen while casting.
- **601.2g-h / 602.2b:** mana abilities and cost payment occur in the rules-defined payment process for spells and activated abilities.
- **603.3b-d:** simultaneous trigger ordering and triggered targets are chosen as those triggers are put on the stack.
- **608.2b:** targets are rechecked on resolution; if at least one remains legal, the object resolves using the remaining legal targets as applicable.
- **608.2d:** effect choices not already made during casting/activation/trigger stacking are made during resolution.
- **614.12a / 616.1:** relevant entry/replacement choices occur before entry, and competing replacement effects use the affected-player/controller choice process.
- **701.40b:** a manifested creature card may be turned face up by the manifest special action for its mana cost.
- **704.5j:** the legend rule requires the controller to choose which qualifying legendary permanent remains.
- **733.1:** an illegal action is reversed in its entirety.
- **903.9a-b:** Commander graveyard/exile return is an optional SBA; hand/library movement uses an optional replacement effect.

## Validation boundary

Do **not** mark the interaction surface `PROVEN` from this branch. The coordinator manifest/lock is not frozen, so a stable record-by-record proof bundle cannot yet be keyed to the final surface hash. CI must also distinguish Agent B failures from the inherited zero-lock coordinator failure.

The remaining kernel priorities are:

1. a general explicit mana/hybrid payment configuration service;
2. simultaneous trigger ordering and optional-trigger resolution-time choice ownership;
3. a general replacement-order service plus commander hand/library replacement;
4. cleanup re-entry discard and legend-rule choice services;
5. generic resolution-time scry choice handling; and
6. generalized compound target metadata for copied Prismari Command spells.

None of those should be closed by adding a fixed strategic preference to the rules engine.
