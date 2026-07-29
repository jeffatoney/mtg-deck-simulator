# Phase A — Clean Rules Engine Build Contract

**Status:** Engine-preparation contract. It becomes the current Phase A implementation contract when the preparation pull request is merged.

**Cannot override:**

- `docs/source/MagicCompRules_2026-06-19.txt`
- frozen Oracle records under `docs/source/oracle/`
- `docs/spec/LEAGUE_MULLIGAN.md`
- frozen `docs/spec/identity/IDENTITY_MODEL_V2.0.0.md` and its approval record
- `docs/governance/PHASE_A_AUTHORITY_MAP.md` and `automation/phase-a-authority-map.json`

The authority map classifies superseded prompts, architecture documents, tests, reports, workflows, and legacy execution as archival or prohibited evidence. Inclusion in Git history or `HANDOFF_MANIFEST.json` proves preservation only and does not make an item current authority.

## 1. Purpose

Build the trustworthy engine foundation before migrating the complete 98-card library or running a pilot. Phase A must prove that the same production rules path can represent and execute object identity, zones, actions, stack use, priority, triggers, state-based actions, turn processing, replay, and hidden-information boundaries.

Phase A is not a general implementation of every Magic mechanic. It is a complete foundation for this deck and the explicitly modeled environment, with unsupported capabilities failing closed.

## 2. Required package boundary

Create and use these production packages:

```text
src/mtg_kernel/   card-agnostic game state and universal rules services
src/mtg_cards/    frozen-Oracle-backed card specifications and primitive compositions
```

The current `src/mtg_sim/` package is legacy reference code during the transition.

The clean packages must not:

- import any `mtg_sim` module;
- execute or wrap the legacy `GameExecutor`;
- mutate legacy game state;
- copy event-log shortcuts in place of rules objects;
- call the legacy pilot as acceptance evidence;
- branch on real card names inside the kernel.

The clean packages may independently read frozen source artifacts through new source-loading interfaces that do not depend on legacy execution code.

## 3. Build order

### A. State, identity, and sources

Implement:

- `CardSpec`, `DeckSlot`, `CardInstance`, `GameObject`, `Action`, `Event`, `Choice`, `TargetRef`, and `ZoneChange` schemas;
- one engine-owned `IdentityService`;
- complete frozen-Oracle record loading and hash verification;
- the object kinds, ownership, controller, status, visibility, copy provenance, reference modes, and continuity capabilities frozen in `IDENTITY_MODEL_V2.0.0`;
- deterministic, domain-separated identity, shuffle, and policy RNG streams.

### B. Zone and reference services

Implement one authoritative zone-transition service that:

- retires the prior object and creates the correct successor object;
- covers ordinary zone changes and the same-zone reincarnation events required by CR 400.8–400.10;
- records predecessor and causal event links;
- handles commander graveyard/exile choices through the intermediate zone;
- prevents counters, damage, attachments, targets, and temporary effects from following a card illegally;
- supports explicit `CURRENT_OBJECT_REQUIRED`, `LAST_KNOWN_INFORMATION`, and authorized `SUCCESSOR_TRACKING` modes;
- makes unsupported continuity capabilities fail closed.

### C. Actions, stack, priority, and resolution

Implement one production pipeline for spells and activated abilities:

```text
propose → choose modes/targets/values → validate → determine costs → pay costs →
create stack object → priority → resolve or counter → legal destination →
state-based actions → waiting triggers → priority
```

Permanent spells must use the stack. Targets must be revalidated on resolution. Spell and ability copies must be represented as synthetic rules objects and must not be reported as cast or activated.

### D. Trigger, state-based-action, and turn engines

Implement:

- real triggered-ability objects, including waiting triggers and delayed triggers;
- controller determination for waiting and stacked abilities;
- state-based-action stabilization at the rules-required times;
- untap through cleanup, including repeated cleanup steps;
- marked-damage removal, maximum-hand-size discard, actual discard triggers, effect expiry, and conditional priority during cleanup;
- terminal loss and win processing that stops further game execution.

### E. Hidden observations, replay, and hashing

Implement:

- policy observations that expose no hidden internal IDs, hidden identities, library order, or future randomness;
- per-observation opaque handles with revocation;
- exact `identity-state-v2.0.0` state hashing;
- append-only causal action and event records;
- replay from initial state, named RNG streams, choices, payments, targets, and actions through the same production engine;
- rejection of altered, omitted, duplicated, or reordered replay actions.

### F. Minimal external-opponent boundary

Do not build complete opponent decks in Phase A. Represent only explicitly modeled public external objects and choices required by a scenario, with an external-zone ledger that records owner, destination, position, and cessation. Opponent-owned objects may never enter the simulated player’s zones.

## 4. Representative production-card slice

Use complete frozen Oracle records and the production execution path for ten behavior-bearing cards:

1. Sol Ring
2. Opt
3. Abrade
4. Soul-Guide Lantern
5. Commit // Memory
6. Malcolm, Keen-Eyed Navigator
7. Glint-Horn Buccaneer
8. Dualcaster Mage
9. Twinflame
10. Curiosity

Also implement Island and Mountain as basic mana-source specifications. Thus the Phase A source pool contains twelve named card entries: ten behavior-bearing cards plus two basics.

Fictional fixtures may supplement generic tests but cannot satisfy a named production-card obligation.

## 5. Required production-path proofs

Phase A tests must prove, through the clean `GameExecutor` path:

- a permanent spell is on the stack before it becomes a permanent;
- explicit priority exists between stack placement and resolution;
- a creature or artifact spell can be countered without producing an ETB trigger;
- Soul-Guide Lantern creates a real targeted trigger only when a legal target exists;
- a target that leaves before resolution is not silently followed;
- marked damage clears at cleanup and does not combine across turns;
- cleanup discards are real zone moves and can create real triggers and repeated cleanup;
- every zone change creates the required new object identity;
- re-exile and command-zone same-zone reincarnation create new object identities;
- commander return from graveyard or exile is an explicit recorded choice;
- Commit handles internal cards, spell copies, commanders, and modeled external objects correctly;
- Memory is cast from the graveyard with no targets;
- Twinflame creates token copies with a real delayed exile trigger;
- Dualcaster creates a real ETB trigger and a real spell-copy object;
- hidden IDs and face-down identities are absent from policy observations;
- replay reproduces action order, event order, object identities, zones, RNG positions, and final state hash in a fresh process;
- unsupported rules capabilities block the affected action, card, scenario, or run.

Each blocking requirement in `IDENTITY_MODEL_V2.0.0` must map to at least one named positive or negative test.

## 6. Phase A completion gate

Phase A may be called complete only when all of the following are true on one clean commit:

```text
[ ] src/mtg_kernel and src/mtg_cards contain the production implementation.
[ ] Neither clean package imports or delegates to mtg_sim.
[ ] The frozen identity digest and lock records verify.
[ ] The Phase A authority map passes and the legacy pilot workflow is absent.
[ ] Every blocking identity requirement has executable passing tests.
[ ] The representative real cards load complete frozen Oracle records.
[ ] Required scenarios execute through the clean production path.
[ ] Replay and state hashes reproduce across fresh processes.
[ ] Hidden-information boundary tests pass.
[ ] Unsupported capabilities fail closed.
[ ] Existing repository checks still pass or are intentionally replaced with documented equivalents.
[ ] A dedicated Phase A result artifact records commit, clean-tree status, commands, exact counts, and PASS/FAIL.
[ ] The production pilot remains locked.
[ ] No unresolved P1 or P2 correctness finding remains.
```

Golden transcripts may be authored alongside the engine, but Phase A cannot be accepted as complete until each required transcript is independently approved and digest-bound as required by the frozen identity specification.

## 7. Explicit non-goals

Phase A does not:

- migrate all 98 library cards;
- select or optimize game policies;
- run the 500/200 pilot;
- run the 25,000-game study;
- delete the legacy package;
- merge or reuse stale recovery control-plane branches;
- treat archival materials or legacy execution as acceptance evidence;
- implement unsupported side formats or every CR 400.7 capability.

## 8. Removal and transition rule

No legacy file, workflow, branch, or pull request is deleted or closed as part of this preparation contract without owner approval. The owner approved closing PR #31 without merging and disabling the active legacy pilot workflow on 2026-07-29. See `docs/architecture/ENGINE_TRANSITION_REMOVALS.md` for the recorded sequence.
