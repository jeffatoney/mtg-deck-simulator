# Phase A Acceptance Specification — Clean Rules Kernel

STATUS: FROZEN. This specification is immutable during Phase A. Implementation
and acceptance-test code must satisfy it but may not weaken, skip, delete, or
reinterpret a requirement. Any specification change must be made by the user in
a separate pull request before Phase A continues.

Phase A builds the new clean kernel in parallel with the quarantined legacy
engine. Every acceptance test must execute through the new canonical Phase A
path:

`mtg_kernel.executor.GameExecutor` → `TurnEngine` → action/casting pipeline →
stack and priority → resolution → state-based actions → replay.

An isolated helper test does not satisfy an acceptance requirement. Tests live
under `tests/phase_a_acceptance/` and use node names beginning with the exact
requirement ID, such as `test_A1_...`.

Vertical-slice card pool: Island, Mountain, Sol Ring, Opt, Abrade,
Soul-Guide Lantern, Commit // Memory, Malcolm, Keen-Eyed Navigator,
Glint-Horn Buccaneer, Dualcaster Mage, Twinflame, and Curiosity.

The existing production pilot remains locked and continues to use no Phase A
results. Phase B promotes the new kernel after the complete 98-card migration.

---

## A. Casting pipeline — no permanent bypasses the stack

- A1. Casting Sol Ring places a `SpellObject` on the stack; the battlefield is
  unchanged until resolution. Assert stack contents between cast and resolution.
- A2. Casting Glint-Horn Buccaneer places a `SpellObject` on the stack; the
  permanent enters only on resolution and has correct summoning-sickness state.
- A3. Casting Malcolm from the command zone places a `SpellObject` on the stack;
  commander cast count increments at cast time; commander tax is included in the
  paid cost and escalates correctly after Malcolm returns to the command zone.
- A4. An explicit external counterspell can counter a creature spell. The
  creature never enters, no ETB trigger is created, and the actual card instance
  moves to its owner's legal destination.
- A5. The same is true for an artifact spell.
- A6. No enter-the-battlefield trigger exists before a permanent spell resolves.
- A7. Priority is offered after a spell is put on the stack and before
  resolution; a policy holding priority can respond.

## B. Trigger engine — triggers are objects, not log claims

- B1. Soul-Guide Lantern resolving with one legal modeled graveyard card creates
  a real `TriggeredAbilityObject` on the stack. The card is not exiled while the
  trigger is pending and is exiled only on legal resolution.
- B2. With multiple legal modeled graveyard cards, exactly one target is selected
  and preserved in the action log and replay.
- B3. With all modeled graveyards empty, Lantern still resolves and enters. No
  target is invented, no exile occurs, and no `trigger_put_on_stack` event is
  emitted without a corresponding stack object.
- B4. If the target leaves the graveyard before resolution, the triggered ability
  resolves with no legal targets and exiles nothing.
- B5. Priority exists between trigger placement and resolution.
- B6. Across every acceptance game, each `trigger_put_on_stack` event corresponds
  to a real `TriggeredAbilityObject` present on the stack at that timestamp.

## C. Turn engine and cleanup — one authoritative path

- C1. Through `GameExecutor.run`, three damage marked on a creature during turn 1
  is absent at the start of turn 2.
- C2. Three damage in turn 1 and one damage in turn 2 are never combined; a
  four-toughness creature survives both nonlethal events.
- C3. Lethal damage before cleanup removes a creature through state-based actions
  before cleanup runs.
- C4. A nine-card hand at cleanup discards exactly two cards through real zone
  moves; discard-triggered abilities trigger from those actual discards.
- C5. Curiosity attached to a creature that dealt no damage to an opponent creates
  no Curiosity trigger during cleanup.
- C6. A real cleanup discard with Glint-Horn on the battlefield creates its damage
  trigger. When that trigger resolves and Glint-Horn is enchanted by Curiosity,
  Curiosity creates one trigger for each opponent actually damaged. Each optional
  draw is a recorded choice. The resulting priority process causes a complete
  additional cleanup step.
- C7. A quiet cleanup runs once. Additional cleanup steps occur only after the
  rules required state-based actions or waiting triggers and priority.
- C8. `GameExecutor` contains no direct phase or step assignment. Every phase and
  step transition in acceptance-game logs is emitted by `TurnEngine`.

## D. Object identity, ownership, and Commit // Memory

- D1. All game zones contain instance/object IDs, never bare card-name strings.
- D2. Commit targeting the simulated player's real spell puts the same
  `CardInstance` second from the top of its owner's library; the spell leaves the
  stack and library size remains correct.
- D3. Commit targeting a spell copy makes the copy cease to exist and adds
  nothing to any library.
- D4. Commit targeting an opponent-owned external spell removes it from the stack
  and records owner, destination `owners_library`, and position 2 in the
  `ExternalZoneLedger`. Nothing enters the simulated player's hand, library, or
  graveyard.
- D5. Action generation never offers a Commit target whose destination cannot be
  represented by the modeled internal zones or external ledger.
- D6. If Commit's target leaves the stack before resolution, Commit resolves with
  no legal targets, does nothing to the former target, and the Commit card moves
  to its normal post-resolution zone.
- D7. Every generated Memory action is cast from the graveyard, has `targets ==
  ()`, and has no stack target.
- D8. Validation rejects targeted Memory actions before mana payment or zone
  movement; state is bit-identical before and after rejection.
- D9. Replays containing each supported Commit outcome and a targetless Memory
  cast reproduce identical final states and external-ledger contents.

## E. Minimal external-opponent boundary

- E1. No opponent-owned object ever appears in the simulated player's hand,
  library, graveyard, exile, or command zone.
- E2. Scenario `opponent_counter_on_first_commander` injects an external
  counterspell targeting Malcolm. Priority returns to the simulated player;
  Commit can target that external spell; after Commit resolves, Malcolm remains
  on the stack and may later resolve.
- E3. Every external object leaving the active model passes through the
  `ExternalZoneLedger` with owner, destination, and position or cessation state.
- E4. Baseline goldfish mode contains no external objects. Cards requiring an
  external target are not offered illegal actions and are classified
  `stranded_no_legal_external_target` when applicable.
- E5. Interaction-scenario results and baseline results use separate artifact
  namespaces and are never aggregated together.

## F. Replay, tokens, and copies

- F1. A complete vertical-slice scenario containing lands, Sol Ring, Opt,
  Malcolm combat and Treasure production, Twinflame, Dualcaster copying Opt,
  Abrade, Soul-Guide Lantern, Commit on an external spell, Memory from the
  graveyard, and Glint-Horn/Curiosity cleanup replays to a bit-identical final
  state from the initial state, named RNG streams, and recorded actions.
- F2. Twinflame token copies gain haste and are exiled at the beginning of the
  next end step by a real delayed trigger; the token then ceases to exist through
  the normal object/state process, not hardcoded cleanup.
- F3. Dualcaster Mage cast in response to Opt uses a real ETB triggered-ability
  object; the spell copy is a real stack object; resolving the copy does not put
  a card into a graveyard.

## G. Gate integrity and isolation

- G1. `validate-prepolicy-readiness` and `mtg-sim recovery kernel` fail if A1,
  B1, C1, D4, or D7 is missing, skipped, xfailed, or absent from pytest
  collection.
- G2. `scripts/check_architecture_invariants.py` passes and the new kernel imports
  no legacy engine, legacy game executor, phase patch, or pilot module.
- G3. This specification and `automation/frozen-spec-sha256.txt` are unchanged
  from `main`; CI verifies both the content hash and the PR diff.
- G4. The existing 500/200 production pilot remains locked. Phase A may run only
  its own recovery gate and non-production fixtures.

---

## Advancement criteria — all required

1. Every acceptance item A1–G4 has a collected test node and passes through the
   new `mtg_kernel.executor.GameExecutor` path.
2. The architecture invariant gate passes.
3. Existing repository CI remains green.
4. An independent Codex review evaluates the current PR head and returns no P1
   or P2 finding.
5. The reviewed commit equals the PR head.
6. The production pilot remains locked.
