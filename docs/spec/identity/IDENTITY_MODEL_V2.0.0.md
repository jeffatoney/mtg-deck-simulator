# IDENTITY_MODEL_V2.0.0 — Deck-Agnostic Magic Engine Identity Specification

**Supersedes:** `IDENTITY_MODEL_V1` (never frozen)
**Status:** `LOCK_READY` — all rules-required and reliability-required corrections are incorporated. The only remaining human action is approval of the exact document digest recorded in the companion approval record.
**Binding after approval:** Yes
**Rules authority:** Comprehensive Rules, effective 2026-06-19 (`WOTC_CR_2026-06-19`)
**Deck-scope evidence:** `exact_decklist.txt`, 100 total cards including commanders; frozen deck SHA-256 `d620c125d5cbb422196a2037fb9dafaaa60ce4e4b449198a84473540fc265edd`
**Frozen Oracle evidence:** 80 of 80 exact entries resolved from the supplied bulk snapshot; source bulk SHA-256 `6dc3ad46f5bbfaa77a556e73aafb0521cf33ccd5bfaba2590b95de2405739f71`
**Engineering authority:** Owner delegation dated 2026-07-27 authorizes selection of rules-required and reliability-required implementation defaults when they do not alter the experimental question.

---

## 1. How to read this document

Every numbered requirement carries a `classification` that determines what makes it true:

| Classification | What establishes it | Human approval |
|---|---|---|
| `OFFICIAL_RULE_VERIFIED` | A cited Comprehensive Rules reference | Not required to establish the rule; a human reviews the translation |
| `OFFICIAL_ORACLE_VERIFIED` | A frozen Oracle record identified by Oracle ID and hash | Not required to establish the text |
| `PROJECT_MODEL_DECISION` | An explicit project choice needed to make the engine deterministic, auditable, or fail-closed | Required at final freeze; reliability-preserving defaults may be selected under the 2026-07-27 owner delegation |
| `IMPLEMENTATION_INVARIANT` | An executable test | Required for the wording; the test must still pass |
| `AWAITING_HUMAN_DECISION` | A genuine unresolved scope or experiment choice that cannot be determined from rules, frozen sources, or reliability requirements | **Blocks freeze** |

Requirements marked `blocking: true` gate the V2 bootstrap and carry both a plain-English statement and a machine contract. Non-blocking material is prose. This asymmetry is deliberate: requiring paired representations for every statement in the document was proposed and rejected, because it reproduces the control-plane accretion that stalled PR #31 without making anything more correct.

Where a plain-English statement and a machine contract disagree, **the machine contract governs**. The plain-English statement explains the contract and may not add behaviour. Any discovered mismatch must still be corrected before freeze so that the document does not contain two conflicting instructions.

---

## 2. Binding design decision

The engine uses **stable physical identity plus changing rules-object identity**.

```text
card_spec_id          declarative card or fixture definition
    ↓
deck_slot_id          uploaded-deck provenance
    ↓
card_instance_id      one physical card within one game
    ↓
object_id             the current rules-object incarnation
    ↓
action_id / event_id / zone_change_id      the causal chain
```

A reincarnation event does not erase physical-card history. It retires the prior rules object and creates a new rules object linked, where applicable, to the same physical card.

This is the required middle ground. One ID for everything lets targets, counters, damage, and continuous effects follow a card illegally across zones. Completely unrelated IDs after every movement lose physical-card history, commander identity, deck provenance, and readable lifecycle analytics.

---

## 3. Identity layers

### 3.1 `card_spec_id` — declarative definition

Identifies a reusable card or fixture definition. Two namespaces exist and they are not interchangeable:

```text
oracle:<oracle_id>          a real Magic card, bound to the frozen Oracle snapshot
fixture:<fixture_name>      an explicitly fictional TEST_FIXTURE
```

**REQ ID-SPEC-NAMESPACE-001** — `classification: PROJECT_MODEL_DECISION`, `blocking: true`

*Plain English:* A `card_spec_id` in the `oracle:` namespace must resolve to a complete frozen Oracle record. A definition whose behaviour is abbreviated, altered, or invented must use the `fixture:` namespace and must not carry a real card's name.

```yaml
machine_contract:
  schema_version: "2.0"
  assertions:
    - EVERY_ORACLE_NAMESPACE_SPEC_RESOLVES_TO_FROZEN_ORACLE_RECORD
    - EVERY_ORACLE_NAMESPACE_SPEC_IS_BEHAVIOURALLY_COMPLETE
    - NO_FIXTURE_NAMESPACE_SPEC_USES_A_NAME_PRESENT_IN_THE_ORACLE_SNAPSHOT
  forbidden_results:
    - ORACLE_SPEC_WITH_PARTIAL_ABILITY_SET
tests:
  required: [TEST-SPEC-ORACLE-COMPLETENESS, TEST-SPEC-FIXTURE-NAME-COLLISION]
```

A spec points to declarative data: name, mana cost, supertypes, card types, subtypes, power and toughness, loyalty or defense, keywords, static/activated/triggered/replacement abilities, target schemas, cost schemas, primitive effect compositions, card faces, and source version.

Type data is structured, never a printed type line:

```yaml
mana_cost: "{2}{U}"
supertypes: [Legendary]
card_types: [Creature]
subtypes: [Siren, Pirate]
```

**Names are display data. Engine control flow may not branch on a card name.**

```python
execute_effect_graph(card_spec.abilities)          # allowed
if card.name == "Malcolm, Keen-Eyed Navigator":    # forbidden
```

### 3.2 `deck_slot_id` — uploaded-deck provenance

Identifies one entry in an uploaded legal deck package (`deck-slot:island-07`). This is a laboratory identity, not a Magic rules identity. It supports multiple copies of basic lands, reproducible construction, deterministic shuffles, paired simulations, decklist validation, and lifecycle reporting. A new game creates a new `card_instance_id` from each deck slot.

### 3.3 `card_instance_id` — physical card in one game

`game-0042:card-0017`. Stable for the entire game. Carries `card_spec_id`, `deck_slot_id`, owner, commander designation, command-zone cast count, commander-damage identity, printing metadata, and creation provenance.

Commander identity and cast history are keyed here, never to a temporary stack or battlefield object.

### 3.4 `object_id` — current rules-object incarnation

Identifies the current Magic object created from a card, token, copy, spell, permanent, or ability. The same physical commander card across one game:

```text
card_instance_id: game-0042:card-0017

object-0101   command-zone object
object-0148   spell on the stack
object-0159   card in graveyard
object-0161   card back in command zone
object-0194   second spell on the stack
object-0210   permanent on the battlefield
```

### 3.5 `component_card_instance_ids`

Every game object stores its physical-card components. Ability and synthetic-copy objects refer to their sources through object references rather than claiming physical-card components.

| Object | Value |
|---|---|
| Ordinary card, noncopy spell, or nontoken permanent | one card instance |
| Physical card affected by a copy effect | its own card instance |
| Token, spell copy, or ability object/copy | empty |
| Melded or merged permanent | more than one |

**REQ ID-ACTIVE-CARD-001** — `classification: IMPLEMENTATION_INVARIANT`, `blocking: true`

*Plain English:* A physical card may be a component of no more than one active rules object at one time. Ability objects may reference a source object but may not duplicate the source card as a component.

```yaml
machine_contract:
  uniqueness_key: card_instance_id
  scope: NON_RETIRED_GAME_OBJECT_COMPONENTS
  maximum_occurrences: 1
  forbidden_results:
    - PHYSICAL_CARD_COMPONENT_IN_MULTIPLE_ACTIVE_OBJECTS
    - ABILITY_OBJECT_DUPLICATES_SOURCE_CARD_COMPONENT
tests:
  required: [TEST-ID-CARD-ONE-ACTIVE-OBJECT]
  negative: [TEST-ABILITY-SOURCE-IS-REFERENCE-NOT-COMPONENT]
```

### 3.6 `synthetic_lineage_id` — reserved, optional

A token or copy family identifier. **Not required for V2.** Reincarnation ancestry is authoritative through `predecessor_object_id`; copy ancestry is authoritative through `copied_from_object_id`, `copiable_values_snapshot_id`, and `copy_creation_event_id`. An independently maintained lineage record would be a second source of truth that could disagree with those records. The field is therefore reserved for later analytics convenience. No referee check and no blocking invariant may depend on it while it remains optional.

### 3.7 `action_id`, `event_id`, `zone_change_id`

Deterministic identity for every proposal, decision, resolution step, and state transition, providing the causal chain used by replay, referee verification, analytics, debugging, paired-policy comparison, and state-hash validation.

---

## 4. The object record

**REQ ID-OBJECT-SCHEMA-001** — `classification: IMPLEMENTATION_INVARIANT`, `blocking: true`

```yaml
authority:
  document_id: WOTC_CR_2026-06-19
  rule_refs: ["108.3", "110.2", "110.5d", "111.2", "112.2", "707.10"]
```

*Plain English:* Characteristics, counters, marked damage, attachment, permanent status, nonbattlefield orientation, visibility, and copy provenance are separate state categories. Only battlefield permanents have permanent status. A physical card affected by a copy effect retains its physical-card identity, while synthetic token, spell-copy, and ability-copy objects have no physical-card component.

```yaml
game_object:
  object_id: "game-0042:object-0194"
  object_kind: >-
    CARD_IN_ZONE | SPELL | PERMANENT | TRIGGERED_ABILITY | ACTIVATED_ABILITY |
    MANA_ABILITY | TOKEN_OBJECT | SPELL_COPY | ABILITY_COPY | EMBLEM |
    EXTERNAL_PUBLIC_OBJECT
  zone: BATTLEFIELD | STACK | HAND | LIBRARY | GRAVEYARD | EXILE | COMMAND | NONE
  owner: "P0"                         # nullable when Magic defines no owner
  controller: "P0"                    # nullable — resolved only through §8

  component_card_instance_ids: ["game-0042:card-0017"]
  source_object_id: null               # ability source; may be retired; never auto-follows a successor

  predecessor_object_id: "game-0042:object-0148"  # reincarnation ancestry only
  created_by_event_id: "game-0042:event-00842"

  copy_kind: >-
    NONE | TOKEN_COPY | SPELL_COPY | ABILITY_COPY | PHYSICAL_OBJECT_COPY_EFFECT
  copied_from_object_id: null
  copiable_values_snapshot_id: null
  copy_creation_event_id: null

  current_characteristics: {}         # name, mana cost, types, P/T, abilities, color
  counters: {}                        # counter kind -> integer count
  marked_damage: 0
  attached_to_ref: null               # {kind: OBJECT|PLAYER, id: ...}; sole authority

  permanent_status: null              # non-null only for a battlefield permanent
  # when non-null:
  # {tap: UNTAPPED|TAPPED, flip: UNFLIPPED|FLIPPED,
  #  face: FACE_UP|FACE_DOWN, phase: PHASED_IN|PHASED_OUT}

  nonbattlefield_orientation: NOT_APPLICABLE | FACE_UP | FACE_DOWN
  visibility:
    identity_visible_to: [P0, P1, P2, P3]

  lki_snapshot_id: null
  synthetic_lineage_id: null          # reserved, optional
  debug_label: null                   # never parsed by engine code
  was_cast: true                      # true | false | null when not applicable
  retired: false
  ceased_to_exist: false
```

```yaml
machine_contract:
  assertions:
    - COUNTERS_ARE_NOT_STORED_IN_CURRENT_CHARACTERISTICS
    - MARKED_DAMAGE_IS_NOT_STORED_IN_CURRENT_CHARACTERISTICS
    - ATTACHMENT_IS_NOT_STORED_IN_CURRENT_CHARACTERISTICS
    - ATTACHED_TO_REF_IS_THE_ONLY_AUTHORITATIVE_ATTACHMENT_DIRECTION
    - PERMANENT_STATUS_IS_NON_NULL_ONLY_FOR_BATTLEFIELD_PERMANENTS
    - NONBATTLEFIELD_OBJECTS_HAVE_NO_TAPPED_FLIPPED_OR_PHASED_STATUS
    - NONBATTLEFIELD_FACE_ORIENTATION_IS_SEPARATE_FROM_PERMANENT_STATUS
    - CARD_PERMANENT_TOKEN_AND_SPELL_OWNERSHIP_FOLLOWS_RULES_108_3_110_2_111_2_AND_112_2
    - ABILITY_OBJECT_AND_EMBLEM_OWNER_IS_NULL_UNLESS_A_LATER_RULE_EXPLICITLY_DEFINES_OWNERSHIP
    - SPELL_COPY_OWNER_EQUALS_PLAYER_UNDER_WHOSE_CONTROL_IT_WAS_PUT_ON_STACK
    - SOURCE_OBJECT_ID_NEVER_AUTO_REDIRECTS_TO_SUCCESSOR
    - PHYSICAL_OBJECT_COPY_EFFECT_RETAINS_PHYSICAL_CARD_COMPONENTS
    - SYNTHETIC_TOKEN_SPELL_COPY_AND_ABILITY_COPY_HAVE_NO_CARD_COMPONENTS
    - PREDECESSOR_OBJECT_ID_IS_USED_ONLY_FOR_REINCARNATION_ANCESTRY
    - COPY_ANCESTRY_USES_COPIED_FROM_OBJECT_ID_AND_COPY_SNAPSHOT
  forbidden_results:
    - TOKEN_PERMANENT_KIND_OUTSIDE_BATTLEFIELD
    - AMBIGUOUS_BOOLEAN_IS_COPY_AS_SOLE_COPY_CLASSIFICATION
    - COPY_SOURCE_RECORDED_AS_REINCARNATION_PREDECESSOR
    - INDEPENDENTLY_EDITABLE_REVERSE_ATTACHMENT_LIST

tests:
  required:
    - TEST-OBJECT-STATE-SEPARATION
    - TEST-ATTACHMENT-SINGLE-AUTHORITY
    - TEST-STATUS-ONLY-ON-PERMANENTS
    - TEST-NONBATTLEFIELD-FACE-ORIENTATION
    - TEST-RULES-OWNER-BY-OBJECT-KIND
    - TEST-SPELL-COPY-OWNER
    - TEST-ABILITY-OBJECT-HAS-NO-RULES-OWNER
    - TEST-SOURCE-REFERENCE-DOES-NOT-FOLLOW-SUCCESSOR
    - TEST-PHYSICAL-COPY-RETAINS-CARD-INSTANCE
    - TEST-COPY-ANCESTRY-SEPARATE-FROM-REINCARNATION
  negative:
    - TEST-NO-TOKEN-PERMANENT-KIND-IN-GRAVEYARD-OR-EXILE
    - TEST-NO-AMBIGUOUS-COPY-FLAG
```

CR 110.5d is binding here: only permanents have status. A face-down card in exile or the command zone may have a physical face orientation, but it is not a face-down permanent and has no tapped, flipped, or phased status. Ownership is also rules-scoped: cards, permanents, tokens, and spells have owners under CR 108.3, 110.2, 111.2, and 112.2; ability objects and emblems do not receive a fabricated rules owner merely for implementation convenience.

**Attachment has exactly one authoritative direction.** `attached_to_ref` lives on the attaching object. A reverse “what is attached to me” list may exist only as a derived index or query result and must never be independently editable state.

**Zone is an explicit field.** The engine must never infer zone, object kind, or any other property by parsing an identifier string. `debug_label` exists so readable labels remain available to humans without becoming authoritative.

**REQ ID-NO-ID-PARSING-001** — `classification: IMPLEMENTATION_INVARIANT`, `blocking: true`

```yaml
machine_contract:
  forbidden_results:
    - ENGINE_READS_ZONE_FROM_OBJECT_ID_STRING
    - ENGINE_READS_ANY_PROPERTY_FROM_DEBUG_LABEL
tests:
  required: [TEST-NO-ID-STRING-PARSING]
  negative: [TEST-DEBUG-LABEL-MUTATION-DOES-NOT-CHANGE-BEHAVIOUR]
```

---

## 5. Object reincarnation

**REQ ID-OBJECT-REINCARNATION-001** — `classification: OFFICIAL_RULE_VERIFIED`, `blocking: true`

*Plain English:* Every zone change retires the previous rules object and creates a new one. Three further events create a new object **without** any zone change: an object already in exile becoming exiled again; a face-up object in the command zone being turned face down; and an object in the command zone being put into the command zone.

```yaml
authority:
  document_id: WOTC_CR_2026-06-19
  rule_refs: ["400.7", "400.8", "400.9", "400.10"]
machine_contract:
  triggers:
    - ZONE_CHANGE
    - REEXILE_EXISTING_EXILE_OBJECT
    - COMMAND_OBJECT_TURNED_FACE_DOWN
    - COMMAND_OBJECT_PUT_INTO_COMMAND_ZONE
  assertions:
    previous_object_status: RETIRED
    successor_object_id_must_differ: true
    predecessor_link_required: true
    stable_card_instance_link_preserved_when_applicable: true
  forbidden_results:
    - OBJECT_ID_REUSED
    - SUCCESSOR_CREATED_WITHOUT_PREDECESSOR_LINK
tests:
  required:
    - TEST-NEW-OBJECT-ON-ZONE-CHANGE
    - TEST-NEW-OBJECT-ON-REEXILE
    - TEST-NEW-OBJECT-ON-COMMAND-FACE-DOWN
    - TEST-NEW-OBJECT-ON-COMMAND-REENTRY
```

A zone change is one atomic, causally linked transition:

```json
{
  "zone_change_id": "game-0042:zone-change-0042",
  "event_id": "game-0042:event-00842",
  "card_instance_ids": ["game-0042:card-0017"],
  "from_object_id": "game-0042:object-0148",
  "to_object_id": "game-0042:object-0159",
  "from_zone": "STACK",
  "to_zone": "GRAVEYARD",
  "cause": "SPELL_COUNTERED",
  "predecessor_relationship": "SAME_PHYSICAL_CARD"
}
```

**The successor object is created with no inherited state.** Every field on the successor is derived from its own zone entry, except where an explicitly named continuity capability from §6 applies. There is no generic "copy permitted state from the old object" operation, and an implementation containing one is defective.

A commander leaving the stack after being countered is therefore two transitions, not one: stack → graveyard, then graveyard → command zone. Under CR 903.9a the second is a state-based action, so the commander really does occupy the graveyard in between, and any ability that cares sees it there.

---

## 6. Continuity capability registry

CR 400.7's exceptions are not field inheritance. They are distinct mechanisms. The exact deck and the Phase A vertical slice have now been scanned, so V2 scope is final rather than proposed.

```yaml
scope_basis:
  deck_source: exact_decklist.txt
  total_cards_including_commanders: 100
  frozen_deck_sha256: d620c125d5cbb422196a2037fb9dafaaa60ce4e4b449198a84473540fc265edd
  phase_a_vertical_slice:
    - Island
    - Sol Ring
    - Opt
    - Abrade
    - Soul-Guide Lantern
    - Commit // Memory
    - Malcolm, Keen-Eyed Navigator
    - Glint-Horn Buccaneer
    - Dualcaster Mage
    - Twinflame

continuity_capabilities:
  CONTINUOUS_EFFECT_FOLLOWS_PERMANENT_SPELL:
    rule_ref: "400.7a"
    scope_v2: UNSUPPORTED

  STATIC_GRANTED_ABILITY_FOLLOWS_PERMANENT_SPELL:
    rule_ref: "400.7b"
    scope_v2: UNSUPPORTED

  PREVENTION_EFFECT_FOLLOWS_PERMANENT_SPELL:
    rule_ref: "400.7c"
    scope_v2: UNSUPPORTED

  PERMANENT_REFERENCES_CAST_COST_INFORMATION:
    rule_ref: "400.7d"
    scope_v2: UNSUPPORTED

  ZONE_CHANGE_TRIGGER_FINDS_SUCCESSOR:
    rule_ref: "400.7e"
    destination_must_be_public: true
    scope_v2: SUPPORTED

  ENCHANTED_PERMANENT_LEAVE_TRIGGER_FINDS_AURAS:
    rule_ref: "400.7f"
    scope_v2: UNSUPPORTED

  GRANTED_CAST_ABILITY_FOLLOWS_CARD_TO_STACK:
    rule_ref: "400.7g"
    scope_v2: SUPPORTED

  CAST_PERMISSION_EFFECT_FINDS_SPELL_ON_STACK:
    rule_ref: "400.7h"
    scope_v2: SUPPORTED

  LAND_PLAY_PERMISSION_FINDS_NEW_PERMANENT:
    rule_ref: "400.7i"
    scope_v2: UNSUPPORTED

  SAME_EFFECT_FINDS_MOVED_OBJECT:
    rule_ref: "400.7j"
    destination_must_be_public: true
    scope_v2: SUPPORTED

  MADNESS_POST_RESOLUTION_TRACKING:
    rule_ref: "400.7k"
    scope_v2: UNSUPPORTED

  STICKER_RETENTION:
    rule_ref: "400.7m"
    scope_v2: UNSUPPORTED

  FLASHBACK_CARD_TO_SPELL_CONTINUITY:
    rule_ref: "702.34a"
    scope_v2: SUPPORTED

  AFTERMATH_CARD_TO_SPELL_CONTINUITY:
    rule_ref: "702.127a"
    scope_v2: SUPPORTED
```

Support for 400.7g and 400.7h provides a generic, fail-closed path for effects that grant or create casting permission. Flashback and aftermath also have explicit keyword capabilities because their own rules create graveyard and stack behavior that must be recorded and replayed. Unsupported capabilities are outside the current deck and modeled environment; encountering one is a hard validation failure.

**REQ ID-CONTINUITY-SCOPE-001** — `classification: IMPLEMENTATION_INVARIANT`, `blocking: true`

*Plain English:* Every continuity capability is either `SUPPORTED` or `UNSUPPORTED`. A capability marked `UNSUPPORTED` blocks any card, action, or scenario that requires it. It may never silently degrade to generic state copying or to no behavior at all.

```yaml
machine_contract:
  assertions:
    - EVERY_CONTINUITY_CAPABILITY_HAS_FINAL_SUPPORTED_OR_UNSUPPORTED_STATUS
    - UNSUPPORTED_CAPABILITY_BLOCKS_AFFECTED_CARD_ACTION_OR_SCENARIO
    - SUPPORTED_CAPABILITY_NAMES_ITS_RULE_REFERENCE_AND_TEST
  forbidden_results:
    - GENERIC_STATE_COPY_ON_REINCARNATION
    - SILENT_NO_OP_FOR_UNSUPPORTED_CAPABILITY
    - PROPOSED_OR_AWAITING_SCOPE_AT_RUNTIME

tests:
  required:
    - TEST-CONTINUITY-REGISTRY-FINAL
    - TEST-UNSUPPORTED-CAPABILITY-BLOCKS
    - TEST-ZONE-CHANGE-TRIGGER-FINDS-SUCCESSOR
    - TEST-SAME-EFFECT-FINDS-MOVED-OBJECT
    - TEST-FLASHBACK-CARD-TO-SPELL-CONTINUITY
    - TEST-AFTERMATH-CARD-TO-SPELL-CONTINUITY
  negative: [TEST-NO-GENERIC-INHERITANCE-PATH]
```

---

## 7. Reference modes

**REQ ID-REFERENCE-MODE-001** — `classification: IMPLEMENTATION_INVARIANT`, `blocking: true`

*Plain English:* Every primitive or effect that holds an object reference declares, at definition time, how that reference behaves when the referenced object has been retired. The engine never chooses at runtime.

```yaml
reference_modes:
  CURRENT_OBJECT_REQUIRED:
    behavior_if_retired: REFERENCE_INVALID
  LAST_KNOWN_INFORMATION:
    behavior_if_retired: USE_CAPTURED_LKI_SNAPSHOT
    official_rule_ref_required: true
  SUCCESSOR_TRACKING:
    behavior_if_retired: FIND_SPECIFIED_SUCCESSOR_OBJECT
    continuity_capability_required: true

machine_contract:
  assertions:
    - EVERY_OBJECT_REFERENCE_DECLARES_A_MODE
    - LKI_AND_SUCCESSOR_MODES_NAME_AN_AUTHORISING_RULE_OR_CAPABILITY
  forbidden_results:
    - RETIRED_REFERENCE_SILENTLY_REDIRECTED_TO_SUCCESSOR
    - RETIRED_REFERENCE_SILENTLY_REDIRECTED_TO_CARD_INSTANCE_ID
    - RUNTIME_CHOICE_BETWEEN_MODES
tests:
  required: [TEST-REFERENCE-MODE-DECLARED-EVERYWHERE]
  negative:
    - TEST-RETIRED-TARGET-DOES-NOT-FOLLOW-CARD
    - TEST-RETIRED-COUNTERS-DO-NOT-FOLLOW-CARD
    - TEST-RETIRED-ATTACHMENT-DOES-NOT-FOLLOW-CARD
```

Default for targeting is `CURRENT_OBJECT_REQUIRED`. A target whose object has been retired is illegal; last known information is not a fallback for a missing target.

This single requirement is what makes the following bug class mechanically checkable rather than merely deprecated: counters following a permanent that left and returned, marked damage surviving a zone change, Auras or Equipment remaining attached illegally, temporary continuous effects applying to a new incarnation, a flickered permanent being treated as though it never left, and a stack spell and its resulting permanent being treated as one unchanged object.

---

## 8. Controller determination

**REQ ID-CONTROLLER-001** — `classification: OFFICIAL_RULE_VERIFIED`, `blocking: true`

*Plain English:* Controller is determined by object kind and rules state, not by zone alone. Only battlefield and stack objects have controllers by default, but the Comprehensive Rules provide explicit exceptions, including a triggered ability waiting to be placed on the stack.

| Object kind or state | Controller source | Rule |
|---|---|---|
| Permanent | The permanent's current controller | 109.4 |
| Noncopy spell on the stack | The player who put it on the stack, normally the player who cast it, as modified by control-changing effects | 112.2, 405.4 |
| Spell copy | The player under whose control the copy was put on the stack | 707.10 |
| Activated ability on the stack | The player who activated it | 113.8 |
| Activated-ability copy | The player under whose control the copy was put on the stack | 707.10 |
| Triggered ability on the stack, other than delayed | The player who controlled its source when it triggered; if the source had no controller, its owner at that time | 113.8 |
| Triggered ability waiting for placement, other than delayed | The player who controlled its source when it triggered; if the source had no controller, its owner at that time | 109.4b, 113.8 |
| Triggered-ability copy | The player under whose control the copy was put on the stack | 707.10 |
| Mana ability, which is not placed on the stack | Determined as though it were on the stack | 109.4a |
| Delayed trigger created by a resolving spell | The player who controlled that spell as it resolved | 603.7d |
| Delayed trigger created by a resolving activated or triggered ability | The player who controlled that ability as it resolved | 603.7e |
| Delayed trigger created by a static ability's replacement effect | The controller of the object with that static ability when the replacement effect was applied | 603.7f |
| Emblem | The player who put it into the command zone | 109.4c |
| Ordinary card in hand, library, graveyard, exile, or command zone | **None** | 108.4, 109.4 |
| Plane, phenomenon, vanguard, scheme, or conspiracy | **UNSUPPORTED in V2; fail closed** | 109.4d–g |

```yaml
authority:
  document_id: WOTC_CR_2026-06-19
  rule_refs: ["108.4", "109.4", "109.4a", "109.4b", "109.4c", "112.2", "113.8", "405.4", "603.7d", "603.7e", "603.7f", "707.10"]

machine_contract:
  assertions:
    - CONTROLLER_RESOLVED_BY_EXHAUSTIVE_OBJECT_KIND_AND_RULE_STATE_TABLE
    - EVERY_SPELL_ON_STACK_HAS_A_CONTROLLER
    - SPELL_AND_ABILITY_COPIES_USE_COPY_PLACEMENT_CONTROLLER
    - CARD_IN_HAND_LIBRARY_GRAVEYARD_EXILE_OR_COMMAND_HAS_NULL_CONTROLLER
    - WAITING_TRIGGERED_ABILITY_USES_SOURCE_CONTROLLER_OR_SOURCE_OWNER_FALLBACK
    - DELAYED_TRIGGER_CONTROLLER_IS_SELECTED_BY_CREATOR_KIND_PER_603_7D_TO_603_7F
    - TRIGGERED_ABILITY_WITH_UNCONTROLLED_SOURCE_USES_SOURCE_OWNER
  forbidden_results:
    - CONTROLLER_INFERRED_FROM_ZONE_ALONE
    - SPELL_COPY_CONTROLLER_INFERRED_FROM_CAST_EVENT
    - NON_NULL_CONTROLLER_ON_ORDINARY_CARD_OUTSIDE_BATTLEFIELD_AND_STACK
    - OPEN_ENDED_AS_APPROPRIATE_CONTROLLER_RULE

tests:
  required:
    - TEST-CONTROLLER-TABLE-EXHAUSTIVE
    - TEST-SPELL-COPY-CONTROLLER
    - TEST-ABILITY-COPY-CONTROLLER
    - TEST-TRIGGERED-ABILITY-SOURCE-OWNER-FALLBACK
    - TEST-WAITING-TRIGGER-CONTROLLER
    - TEST-WAITING-TRIGGER-SOURCE-OWNER-FALLBACK
    - TEST-DELAYED-TRIGGER-CONTROLLER-FROM-SPELL
    - TEST-DELAYED-TRIGGER-CONTROLLER-FROM-ABILITY
    - TEST-DELAYED-TRIGGER-CONTROLLER-FROM-STATIC-REPLACEMENT
  negative:
    - TEST-GRAVEYARD-CARD-HAS-NO-CONTROLLER
    - TEST-COMMAND-ZONE-CARD-HAS-NO-CONTROLLER
```

No “as appropriate” clause is permitted anywhere in controller resolution.

---

## 9. Commander model

Commander behaviour is format logic keyed to physical identity. It is never card-specific.

```yaml
commander_designations:
  "game-0042:card-0017": P0
command_zone_cast_counts:
  "game-0042:card-0017": 1
```

```text
prior_casts    = command_zone_cast_counts[card_instance_id]
commander_tax  = {2} × prior_casts
```

Tax applies only when the physical card is designated a commander **and** is being cast from the command zone. The count increments when the cast is completed, even if the spell is later countered (CR 903.8). Each commander has an independent count.

**REQ ID-COMMANDER-RETURN-001** — `classification: OFFICIAL_RULE_VERIFIED`, `blocking: true`

*Plain English:* Moving a commander from a graveyard or exile to the command zone is a state-based action and is **optional**. The engine records the choice explicitly. It must never be hard-coded to always return, and the commander must pass through the intermediate zone rather than moving directly.

```yaml
authority:
  rule_refs: ["903.9a", "903.9b"]
machine_contract:
  assertions:
    - COMMANDER_GRAVEYARD_OR_EXILE_RETURN_IS_A_RECORDED_CHOICE
    - COMMANDER_OCCUPIES_INTERMEDIATE_ZONE_BEFORE_RETURN
  forbidden_results:
    - DIRECT_STACK_TO_COMMAND_ZONE_MOVE_FOR_GRAVEYARD_DESTINATION
    - IMPLICIT_ALWAYS_RETURN
tests:
  required: [TEST-COMMANDER-RETURN-CHOICE-RECORDED, TEST-COMMANDER-TRANSITS-GRAVEYARD]
```

The hand-and-library replacement effect of CR 903.9b is a separate mechanism and does route directly, without the intermediate zone.

No engine function may branch on Malcolm, Breeches, or any other commander name.

---

## 10. Tokens, copies, and physical cards affected by copy effects

Synthetic copies and physical cards affected by copy effects are different identity categories.

- A token object, spell copy, or ability copy has no physical-card component and never receives a fabricated `card_instance_id`.
- A physical card affected by a Clone-like copy effect retains its own `card_instance_id` and records `copy_kind: PHYSICAL_OBJECT_COPY_EFFECT`.
- A copy object's source is recorded in `copied_from_object_id`; this is copy ancestry, not reincarnation ancestry.
- An ability copy has the same source as the original ability under CR 707.10b.

A token that moves from the battlefield to another zone arrives in that zone before it ceases to exist at the next state-based-action check. A spell copy that leaves the stack likewise enters the applicable zone before ceasing to exist. The zone arrival and cessation must be separately observable events. “Ceases at cleanup” is not a valid general rule.

**REQ ID-SYNTHETIC-001** — `classification: IMPLEMENTATION_INVARIANT`, `blocking: true`

```yaml
authority:
  document_id: WOTC_CR_2026-06-19
  rule_refs: ["111.7", "704.5d", "704.5e", "707.10", "707.10a", "707.10b", "707.10c", "707.10f"]

machine_contract:
  assertions:
    - SYNTHETIC_TOKEN_OBJECT_HAS_NO_CARD_INSTANCE_COMPONENT
    - SPELL_COPY_HAS_NO_CARD_INSTANCE_COMPONENT
    - ABILITY_COPY_HAS_NO_CARD_INSTANCE_COMPONENT
    - PHYSICAL_CARD_AFFECTED_BY_COPY_EFFECT_RETAINS_CARD_INSTANCE_COMPONENT
    - COPY_SOURCE_USES_COPIED_FROM_OBJECT_ID
    - ABILITY_COPY_RETAINS_ORIGINAL_ABILITY_SOURCE_REFERENCE
    - CESSATION_FOLLOWS_A_RECORDED_ZONE_ARRIVAL
    - SPELL_COPY_IS_NOT_CAST
    - ACTIVATED_ABILITY_COPY_IS_NOT_ACTIVATED
    - COPY_TARGET_DECISION_IS_RECORDED_EVEN_WHEN_TARGETS_ARE_RETAINED
  forbidden_results:
    - FABRICATED_CARD_INSTANCE_ID_ON_SYNTHETIC_OBJECT
    - PHYSICAL_COPY_EFFECT_ERASES_CARD_INSTANCE_ID
    - COPY_SOURCE_STORED_AS_PREDECESSOR_OBJECT_ID
    - CAST_TRIGGER_FIRES_FOR_SPELL_COPY
    - CESSATION_WITHOUT_PRIOR_ZONE_ARRIVAL

tests:
  required:
    - TEST-TOKEN-NULL-CARD-INSTANCE
    - TEST-SPELL-COPY-NULL-CARD-INSTANCE
    - TEST-ABILITY-COPY-NULL-CARD-INSTANCE
    - TEST-PHYSICAL-COPY-RETAINS-CARD-INSTANCE
    - TEST-COPY-SOURCE-SEPARATE-FROM-PREDECESSOR
    - TEST-COPY-GRAVEYARD-TRANSIT-THEN-CEASE
    - TEST-TOKEN-ZONE-TRANSIT-THEN-CEASE
    - TEST-SPELL-COPY-NOT-CAST
    - TEST-ABILITY-COPY-NOT-ACTIVATED
  negative: [TEST-NO-FABRICATED-GRAVEYARD-CARD]
```

Copies of spells, activated abilities, and triggered abilities are put directly onto the stack. A spell copy is not cast, and an activated-ability copy is not activated. Token copies are instead created in the zone specified by the effect, normally the battlefield. A copy records its copied source, a copiable-values snapshot, and whether new targets were chosen or the original targets retained.

---

## 11. Card data authority

**REQ ID-ORACLE-AUTHORITY-001** — `classification: PROJECT_MODEL_DECISION`, `blocking: true`

*Plain English:* The binding source for any real card's wording is the repository's frozen Oracle snapshot, referenced by Oracle ID and verified by hash. Live retrieval is not permitted in CI, and no aggregator, remembered wording, or model recollection is authoritative.

```yaml
machine_contract:
  configuration:
    oracle_source: REPO_FROZEN_SNAPSHOT
    live_retrieval_in_ci: false
  assertions:
    - EVERY_ORACLE_NAMESPACE_SPEC_NAMES_ORACLE_ID_SNAPSHOT_VERSION_AND_HASH
tests:
  required: [TEST-ORACLE-HASH-MATCHES-SNAPSHOT]
```

The rationale is empirical rather than theoretical. During verification of the golden transcripts, Gatherer and the Scryfall API both returned HTTP 403, and two card aggregators returned confidently wrong mana costs — Malcolm as `{2}{U}{R}` and Twinflame as `{2}{R}`. Both are plausible enough to pass a casual read. A requirement resting on live retrieval is not enforceable; one resting on a hashed artifact in the repository is.

A transcript or spec references the record by ID and digest; it does not copy the full record inline. The engine loads the complete frozen record.

---

## 12. Hidden information

**REQ MODEL-HIDDEN-IDENTITY-001** — `classification: PROJECT_MODEL_DECISION`, `blocking: true`

*Plain English:* Policy and strategy code may never see stable internal identities for hidden objects. It receives temporary opaque handles only for identities it is legally entitled to know. Two mechanisms are required together, because a stable ID assigned in deck order would otherwise leak library position.

```yaml
machine_contract:
  configuration:
    internal_ids_visible_to_policy: false
    hidden_handle_mode: PER_OBSERVATION_OPAQUE
    identity_rng_stream: identity_rng
    shuffle_rng_stream: shuffle_rng
    policy_rng_stream: policy_rng
    streams_must_be_domain_separated: true
  assertions:
    - POLICY_OBSERVATION_CONTAINS_NO_HIDDEN_CARD_INSTANCE_IDS
    - POLICY_OBSERVATION_CONTAINS_NO_HIDDEN_OBJECT_IDS
    - SHUFFLE_SEED_DOES_NOT_DETERMINE_IDENTITY_ALLOCATION
    - IDENTITY_SEED_DOES_NOT_DETERMINE_LIBRARY_ORDER
    - REVOKED_HANDLE_CANNOT_BE_RESOLVED
    - FACE_DOWN_OBJECT_DOES_NOT_EXPOSE_CARD_SPEC_ID
    - SEARCH_AND_MODEL_FEATURES_RECEIVE_THE_SAME_RESTRICTED_OBSERVATION
tests:
  required:
    - TEST-HIDDEN-ID-BOUNDARY
    - TEST-RNG-DOMAIN-SEPARATION
    - TEST-FACE-DOWN-IDENTITY-MASKING
    - TEST-HANDLE-REVOCATION
```

```yaml
random_streams:
  identity_rng: {seed_derivation_domain: "mtg-v2/identity"}
  shuffle_rng:  {seed_derivation_domain: "mtg-v2/shuffle"}
  policy_rng:   {seed_derivation_domain: "mtg-v2/policy"}
```

`card_instance_id` allocation runs through a deterministic permutation from `identity_rng`, independent of `shuffle_rng`. Every assertion above is boolean and CI-checkable. An earlier proposal to assert that the ID-to-library-position mapping is "statistically indistinguishable from random" was rejected: a probabilistic gate is flaky and is adjudicated by judgement, which is exactly what a blocking check must not be.

The face-down case matters because the battlefield is a public zone that can contain an object whose `card_spec_id` must not be visible to policy. This is the one hidden-information case a zone-based rule does not reach.

This requirement is blocking because a leak here does not crash anything. It produces confidently wrong win rates, which is the worst available failure mode for a simulator.

---

## 13. Determinism, allocation, and hashing

IDs are namespaced by `game_id` and allocated only by an engine-owned `IdentityService`. Card specifications and mechanic extensions may not invent IDs. Allocation order, identity masking, and shuffle order use domain-separated deterministic streams.

Three digests serve different purposes and must not share a value:

| Digest | Covers |
|---|---|
| `state_hash` | One rules-relevant game snapshot under Appendix B |
| `transcript_digest` | A complete transcript artifact, including its plain-English and machine representations |
| `approval_record.document_sha256` | The exact canonical specification file approved by the owner |

**REQ ID-HASH-CONTRACT-001** — `classification: PROJECT_MODEL_DECISION`, `blocking: true`, `decision_status: APPROVED_UNDER_OWNER_DELEGATION_2026-07-27`

```yaml
hash_contract:
  canonicalization: RFC_8785_JCS
  digest_algorithm: SHA-256
  encoding: UTF-8
  state_hash_schema_version: "identity-state-v2.0.0"
  transcript_schema_version_required: true
  numeric_constraint: ALL_HASHED_GAME_STATE_NUMERIC_FIELDS_MUST_BE_INTEGERS

  specification_file_digest:
    normalization: UTF8_WITH_LF_LINE_ENDINGS_NO_BOM
    digest_algorithm: SHA-256
    digest_location: COMPANION_APPROVAL_RECORD

machine_contract:
  assertions:
    - STATE_HASH_FIELD_SCOPE_MATCHES_APPENDIX_B_EXACT_POINTER_ALLOWLIST
    - HASH_INPUT_CONTAINS_ITS_SCHEMA_VERSION
    - APPROVAL_RECORD_HASHES_THE_EXACT_CANONICAL_MARKDOWN_FILE
    - TRANSCRIPT_DIGEST_COVERS_PLAIN_ENGLISH_AND_MACHINE_REPRESENTATIONS
    - RNG_STREAM_POSITIONS_AND_IDENTITY_ALLOCATION_STATE_ARE_HASHED
  forbidden_results:
    - FLOATING_POINT_GAME_STATE_FIELD_INSIDE_HASH_SCOPE
    - HASH_SCOPE_INFERRED_FROM_SERIALIZER_DEFAULTS
    - SELF_REFERENTIAL_DOCUMENT_DIGEST_INSIDE_HASHED_MARKDOWN

tests:
  required:
    - TEST-HASH-REPRODUCIBLE-CROSS-PROCESS
    - TEST-HASH-ALLOWLIST-ENFORCED
    - TEST-HASH-SCHEMA-VERSION-BOUND
    - TEST-SPECIFICATION-FILE-DIGEST-REPRODUCIBLE
```

RFC 8785 plus SHA-256 is selected as a stable interoperability baseline. The exact algorithm is a project choice, but choosing and freezing one is necessary for reproducible replay and independent validation. The exact game state does not require floating-point values; life, mana, damage, counters, sequence values, turn values, and card mana values used by this deck are integers.

---

## 14. Binding invariants

| Invariant | Requirement |
|---|---|
| Physical identity | A `card_instance_id` never changes during a game. |
| Object identity | An `object_id` is never reused. |
| Reincarnation | Zone changes and the CR 400.8–400.10 events retire the prior object and create a new one. |
| No inheritance | The successor inherits nothing except via a named continuity capability. |
| Card activity | A `card_instance_id` appears in the `component_card_instance_ids` of at most one non-retired object at any time. |
| Retired-object immunity | A retired `object_id` is never silently redirected to its successor or to its `card_instance_id`. |
| Reference modes | Every object reference declares its retired-object behaviour at definition time. |
| Ownership | Rules owner exists only for object kinds for which Magic defines one; ability objects and emblems do not receive fabricated owners. |
| Controller | Resolved by the §8 object-kind table only, never from zone alone. |
| Attachment | `attached_to_ref` is the sole authority; reverse lists are derived. |
| State separation | Counters, marked damage, attachment, permanent status, nonbattlefield orientation, and visibility are not characteristics. |
| Targeting | Targets reference `object_id`, never physical-card root identity. |
| Commander history | Designation and cast count reference `card_instance_id`. |
| Commander return | An explicit recorded choice, via the intermediate zone. |
| Synthetic objects | Token objects, spell copies, and ability copies never receive fabricated physical-card IDs; physical cards affected by copy effects retain their IDs. |
| Cessation | Always follows a recorded zone arrival. |
| Causality | Every new object identifies its creation or zone-change event. |
| History | Retired and ceased objects remain immutable audit records. |
| Hidden information | Internal IDs are never visible to policy code; RNG streams are domain-separated. |
| Zone authority | Zone is an explicit field; no engine code parses an ID or `debug_label`. |
| Name independence | Card names never determine engine control flow. |
| Oracle fidelity | An `oracle:` spec is complete and hash-bound; anything else is a `fixture:`. |
| Declarative cards | Normal cards execute through declarative primitive compositions. |
| Replay | The same inputs reproduce identical ID allocation, actions, events, RNG stream positions, state hashes, and final state. |

---

## 15. Approval policy

Human approval may establish a project abstraction, a scope choice, a policy, or an experimental setup. It **may not** override the Comprehensive Rules or frozen Oracle text, and it may not substitute for a passing test.

Under the owner's 2026-07-27 delegation, this document directly resolves implementation defaults when all of the following are true:

1. Magic's rules do not select the representation.
2. A concrete choice is necessary for determinism, hidden-information protection, fail-closed behavior, replay, or independent validation.
3. The choice does not alter the experimental question, opponent assumptions, policy objective, or reported outcome definition.
4. The choice is explicit, versioned, and testable.

The selected hash algorithm, hidden-identity mechanism, exact hash allowlist, reserved status of `synthetic_lineage_id`, and unsupported side-format categories meet those conditions and are resolved in §17. The owner must still approve the exact final document digest before the specification becomes frozen and binding.

Where a rule is `OFFICIAL_RULE_VERIFIED`, human review confirms the translation from rule to contract; it does not create the rule. A failing implementation cannot be approved into correctness.

---

## 16. Gates

### 16.1 Specification lock gate

These checks determine whether this document may be locked. They do not require the engine to exist first.

```text
[x] All rules-required identity corrections are incorporated.
[x] Every blocking requirement has a machine contract and named tests.
[x] Every official-rule claim names a rule reference in WOTC_CR_2026-06-19.
[x] Every project-model decision is resolved under explicit owner authority.
[x] Every continuity capability is marked SUPPORTED or UNSUPPORTED.
[x] Unsupported capabilities are required to fail closed.
[x] The exact state_hash JSON-pointer allowlist is versioned in Appendix B.
[x] Policy observations are forbidden from accessing hidden internal identities.
[x] Zone and object kind are explicit fields and are never encoded authoritatively in IDs.
[x] Generic fixture tests are separated from Oracle-backed production-card obligations.
[x] No AWAITING_HUMAN_DECISION or PROPOSED scope remains.
[ ] The owner approves the exact SHA-256 digest in the companion approval record.
```

### 16.2 Phase A implementation acceptance gate

These checks are required after implementation and before Phase A may merge. They do not block locking this specification.

```text
[ ] CardSpec, DeckSlot, CardInstance, GameObject, Action, and Event schemas exist in code.
[ ] Every blocking positive and negative test passes through the production execution path.
[ ] Unsupported capabilities demonstrably block affected cards, actions, and runs.
[ ] state_hash and replay reproduce identical results across fresh processes.
[ ] Policy observations cannot access hidden internal identities.
[ ] The ten real Phase A vertical-slice cards use complete frozen Oracle records.
[ ] The required end-to-end scenarios execute through GameExecutor.
[ ] The five golden transcripts carry digest-bound owner approvals.
[ ] The production pilot remains physically locked.
```

---

## 17. Resolved project decisions and remaining lock action

All six former open decisions are resolved. None remains `AWAITING_HUMAN_DECISION`.

| ID | Final decision | Basis | Status |
|---|---|---|---|
| `OD-V2-1` | Use the final continuity table in §6 and Appendix A. Support 400.7e, 400.7g, 400.7h, 400.7j, flashback, and aftermath; mark the other listed capabilities unsupported and fail closed. | Exact deck and Phase A scan plus official rules | `RESOLVED` |
| `OD-V2-2` | RFC 8785 JCS, SHA-256, UTF-8, and integer-only hashed game-state numerics | Required reproducibility default selected under owner delegation | `RESOLVED` |
| `OD-V2-3` | Domain-separated identity, shuffle, and policy RNG streams plus per-observation opaque handles | Required hidden-information and paired-simulation validity | `RESOLVED` |
| `OD-V2-4` | Freeze the exact versioned JSON-pointer state-hash allowlist in Appendix B | Required replay validity | `RESOLVED` |
| `OD-V2-5` | Keep `synthetic_lineage_id` reserved and optional; no invariant or referee check may depend on it | Avoids a second authoritative lineage source | `RESOLVED` |
| `OD-V2-6` | Planechase, Vanguard, Archenemy, and Conspiracy controller categories are unsupported in V2 and fail closed | Outside the frozen Commander project scope | `RESOLVED` |

The only remaining human action is governance rather than rules interpretation:

```yaml
remaining_lock_action:
  id: LOCK-V2-1
  action: APPROVE_EXACT_DOCUMENT_DIGEST
  approval_record: IDENTITY_MODEL_V2.0.0_APPROVAL_RECORD.json
  effect: CHANGE_STATUS_FROM_LOCK_READY_TO_FROZEN_BINDING_FOR_PHASE_A
```

---

## Appendix A — Final CR 400.7 and alternate-zone continuity scope

| Rule | Mechanism | V2 scope | Deck/Phase A reason |
|---|---|---|---|
| 400.7a | Effect changing a permanent spell continues to the permanent | `UNSUPPORTED` | No frozen deck or Phase A requirement needs it |
| 400.7b | Static ability granting an ability to a permanent spell continues | `UNSUPPORTED` | No frozen deck or Phase A requirement needs it |
| 400.7c | Prevention effect on permanent-spell damage continues | `UNSUPPORTED` | No frozen deck or Phase A requirement needs it |
| 400.7d | Permanent references information about the spell and costs paid | `UNSUPPORTED` | No frozen deck permanent references cast-payment information |
| 400.7e | Zone-change triggered ability finds the successor in a public zone | `SUPPORTED` | Required by the generic zone-trigger model and ETB/zone-change scenarios |
| 400.7f | Trigger from enchanted permanent leaving finds Auras in graveyard | `UNSUPPORTED` | Curiosity and Crab Umbra do not require this exception in the frozen scenarios |
| 400.7g | Granted cast ability continues after the card becomes a spell | `SUPPORTED` | Generic alternate-zone casting must retain its authorization without ID leakage |
| 400.7h | Other parts of a cast-permission effect find the resulting spell | `SUPPORTED` | Generic alternate-zone casting and fail-closed replay support |
| 400.7i | Land-play permission effect finds the resulting permanent | `UNSUPPORTED` | Unknown Breeches-exiled opponent cards are not usable deterministic resources |
| 400.7j | Later instruction of the same effect finds an object moved to a public zone | `SUPPORTED` | Required for effects such as counting objects successfully exiled by the same effect |
| 400.7k | Madness post-resolution tracking | `UNSUPPORTED` | No madness card in the frozen deck |
| 400.7m | Sticker retention | `UNSUPPORTED` | No sticker card or sticker sheet in scope |
| 702.34a | Flashback graveyard permission and stack replacement behavior | `SUPPORTED` | Electroduplicate and Faithless Looting |
| 702.127a | Aftermath graveyard permission and stack replacement behavior | `SUPPORTED` | Memory half of Commit // Memory |

A future deck or modeled environment requiring an unsupported capability must update this versioned registry, add rule-linked positive and negative tests, and receive a new specification version before the capability may execute.

---

## Appendix B — Exact `state_hash` JSON-pointer allowlist

The state-hash schema version is `identity-state-v2.0.0`. Paths use JSON Pointer syntax with `*` as the schema-defined wildcard for every key or array member at that level. No serializer-default field inclusion is permitted.

```yaml
state_hash_schema:
  version: "identity-state-v2.0.0"
  canonicalization: RFC_8785_JCS
  digest_algorithm: SHA-256

  included_paths:
    - /schema_version
    - /game_id

    - /allocation/next_object_sequence
    - /allocation/next_action_sequence
    - /allocation/next_event_sequence
    - /allocation/next_zone_change_sequence
    - /allocation/next_lki_sequence

    - /rng_streams/*/domain
    - /rng_streams/*/draw_count
    - /rng_streams/*/state_digest

    - /turn/number
    - /turn/active_player_id
    - /turn/phase
    - /turn/step
    - /turn/priority_holder_id
    - /turn/consecutive_priority_passes
    - /turn/cleanup_iteration

    - /players/*/player_id
    - /players/*/life
    - /players/*/in_game
    - /players/*/loss_reasons
    - /players/*/mana_pool
    - /players/*/land_plays_remaining
    - /players/*/maximum_hand_size
    - /players/*/failed_draw_count

    - /deck_slots/*/deck_slot_id
    - /deck_slots/*/card_spec_id
    - /deck_slots/*/deck_source_position

    - /card_instances/*/card_instance_id
    - /card_instances/*/card_spec_id
    - /card_instances/*/deck_slot_id
    - /card_instances/*/owner_id
    - /card_instances/*/commander_designation
    - /card_instances/*/creation_provenance

    - /zones/*/zone_id
    - /zones/*/zone_type
    - /zones/*/owner_id
    - /zones/*/ordered_object_ids

    - /objects/*/object_id
    - /objects/*/object_kind
    - /objects/*/zone
    - /objects/*/owner
    - /objects/*/controller
    - /objects/*/component_card_instance_ids
    - /objects/*/source_object_id
    - /objects/*/predecessor_object_id
    - /objects/*/created_by_event_id
    - /objects/*/copy_kind
    - /objects/*/copied_from_object_id
    - /objects/*/copiable_values_snapshot_id
    - /objects/*/copy_creation_event_id
    - /objects/*/current_characteristics
    - /objects/*/counters
    - /objects/*/marked_damage
    - /objects/*/attached_to_ref
    - /objects/*/permanent_status
    - /objects/*/nonbattlefield_orientation
    - /objects/*/visibility/identity_visible_to
    - /objects/*/lki_snapshot_id
    - /objects/*/was_cast
    - /objects/*/retired
    - /objects/*/ceased_to_exist

    - /stack/ordered_object_ids

    - /pending_actions/*
    - /recorded_choices/*
    - /targets/*
    - /waiting_triggers/*
    - /delayed_triggers/*
    - /replacement_effects/*
    - /continuous_effects/*
    - /lki_snapshots/*

    - /commander/designations/*
    - /commander/command_zone_cast_counts/*
    - /commander/damage_by_commander/*
    - /commander/pending_zone_choices/*

    - /external_object_ledger/*

    - /terminal/status
    - /terminal/winners
    - /terminal/losers
    - /terminal/cause_event_ids

  excluded_paths:
    - /wall_clock_timestamp
    - /objects/*/debug_label
    - /objects/*/display_name_when_canonical_spec_id_exists
    - /caches
    - /derived_indexes
    - /analytics
    - /approval_metadata
    - /state_hash
    - /raw_rng_seeds
```

The run manifest separately binds the initial raw seeds and frozen source hashes. Each state snapshot hashes the current RNG stream position and state digest so replay divergence is detected without exposing raw seeds to policy observations.

Any field added beneath the game-state root is excluded by default until this allowlist is versioned. Changing included or excluded paths requires a new state-hash schema version and a specification version change.

---

## Appendix C — Resolved transcript and fixture decisions

The owner resolved the Glint-Horn discard source on 2026-07-27 as **Glint-Horn Buccaneer's own activated ability**: `{1}{R}, Discard a card: Draw a card. Activate only if Glint-Horn Buccaneer is attacking.` The transcript must therefore begin in combat with Glint-Horn attacking, treat the discard as an activation cost, place the discard-triggered damage ability above the activated draw ability, and include legal mana sources for `{1}{R}`.

Abbreviated generic fixtures must use fictional names in the `fixture:` namespace. They may prove generic identity, stack, trigger, copy, and zone behavior, but they **do not** satisfy production-card migration or Oracle-backed vertical-slice obligations.

The Phase A production path must separately implement and test the real frozen Oracle records for:

- Sol Ring
- Soul-Guide Lantern
- Dualcaster Mage
- Twinflame
- Every other named card in the ten-card vertical slice

A test using a fictional mana artifact or fictional copy spell may supplement those tests, but it may not be reported as evidence that the corresponding real card is migrated or complete.

---

## Appendix D — Lock record procedure

The canonical Markdown file is normalized as UTF-8, LF line endings, and no BOM, then hashed with SHA-256. The digest is stored in `IDENTITY_MODEL_V2.0.0_APPROVAL_RECORD.json`, not inside this Markdown file, to avoid a self-referential digest.

The specification becomes frozen only when the owner approves the exact digest. After approval:

```yaml
freeze_transition:
  from_status: LOCK_READY
  to_status: FROZEN_BINDING_FOR_PHASE_A
  required_evidence:
    - exact document SHA-256
    - owner identity or repository approval identity
    - approval timestamp
    - repository commit SHA
```

Any later binding change requires a new semantic version and a new digest. Editorial changes that can affect interpretation are binding changes.
