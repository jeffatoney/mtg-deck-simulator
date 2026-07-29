# Codex Task — Phase A Clean Rules Engine

Repository: `jeffatoney/mtg-deck-simulator`

## Objective

Build the clean, deck-scoped Magic rules engine foundation required by `docs/spec/ENGINE_BUILD_PHASE_A.md` and frozen `IDENTITY_MODEL_V2.0.0`.

Do not run simulations for empirical results. Do not start the complete-deck migration. Do not delete legacy code.

## Branch and pull request

Start only after the engine-preparation pull request has merged to `main`.

1. Update from `origin/main`.
2. Create exactly one branch: `engine/phase-a-rules-kernel`.
3. Open exactly one draft pull request titled `Phase A: build clean Magic rules engine`.
4. Keep all Phase A work on that branch and pull request.

## Read before editing

Read these sources in order:

1. `AGENTS.md`
2. `docs/source/MagicCompRules_2026-06-19.txt`
3. the frozen Oracle snapshot under `docs/source/oracle/`
4. `docs/spec/LEAGUE_MULLIGAN.md`
5. `docs/spec/identity/IDENTITY_MODEL_V2.0.0.md`
6. `docs/spec/identity/IDENTITY_MODEL_V2.0.0_APPROVAL_RECORD.json`
7. `docs/spec/identity/IDENTITY_MODEL_V2.0.0_LOCK_MANIFEST.txt`
8. `docs/spec/ENGINE_BUILD_PHASE_A.md`
9. `docs/architecture/LEGACY_QUARANTINE.md`

Before implementation, run:

```bash
uv sync --frozen --all-extras
uv run python scripts/check_identity_lock.py
uv run python scripts/check_clean_engine_boundary.py
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest -q
uv run python scripts/check_manifest.py
uv run mtg-sim validate-sources
```

Record the exact starting commit and results. If the frozen identity check fails, stop. Do not regenerate, weaken, or replace the approved specification.

## Authority and decision rule

The Comprehensive Rules and frozen Oracle records determine Magic behavior. The league mulligan file is the only league override. The frozen identity model determines object identity, references, hidden identities, hashing, and supported continuity scope.

When implementation details are not selected by Magic rules, choose a deterministic, testable, fail-closed design that preserves the experiment and follows the frozen specification. Do not ask the owner to decide ordinary software representation choices. Stop only for a genuine experiment, scope, or policy decision that cannot be derived from the binding sources or reliability requirements.

## Package boundary

Implement production code under:

```text
src/mtg_kernel/
src/mtg_cards/
```

The new packages must not import, wrap, subclass, monkey-patch, dynamically load, or delegate to `mtg_sim`.

`src/mtg_sim/` is legacy reference code. It may be read to locate prior scenarios or source artifacts, but its behavior is not authoritative and its outputs are not Phase A evidence.

The kernel may not branch on a real card name. Named cards are structured Oracle-backed specifications composed from universal primitives.

## Implementation sequence

### 1. Sources and schemas

Implement typed schemas for:

- `CardSpec`
- `DeckSlot`
- `CardInstance`
- `GameObject`
- `Action`
- `Event`
- `Choice`
- `TargetRef`
- `ZoneChange`
- `LKISnapshot`
- player, turn, mana-pool, zone, stack, and terminal state

Load real card data from the complete frozen Oracle records and verify each record hash. Do not encode remembered or abbreviated text for a real named card.

### 2. Identity and references

Implement one engine-owned `IdentityService` and every blocking identity requirement from `IDENTITY_MODEL_V2.0.0`, including:

- stable `card_instance_id` and changing `object_id`;
- at most one active object component per physical card;
- new objects for all zone changes, re-exile, command-zone face-down, and command-zone re-entry;
- separate characteristics, counters, marked damage, attachment, status, orientation, visibility, and copy provenance;
- explicit ownership and controller tables;
- `CURRENT_OBJECT_REQUIRED`, `LAST_KNOWN_INFORMATION`, and authorized `SUCCESSOR_TRACKING`;
- fail-closed unsupported continuity capabilities;
- synthetic tokens, spell copies, and ability copies without fabricated physical-card IDs;
- separate reincarnation ancestry and copy ancestry;
- commander designation, cast count, tax, damage identity, and optional return choices keyed to physical identity.

### 3. Zones and state transitions

Create one authoritative zone service. No card specification, policy, or executor may mutate a zone directly.

Every transition must record:

- prior object and successor object when applicable;
- source and destination zones;
- physical components;
- cause event;
- predecessor link;
- commander choice when applicable;
- cessation after a real zone arrival for tokens and copies;
- external-owner destination data when an explicitly modeled opponent object leaves the active model.

### 4. Actions, costs, stack, and priority

Create one legality and execution path for spells and activated abilities:

```text
propose → choose → validate → determine costs → pay costs → stack → priority →
resolve/counter → legal destination → state-based actions → waiting triggers → priority
```

Requirements include:

- permanent spells use the stack;
- targets are selected legally and revalidated on resolution;
- costs, commander tax, and X values are recorded;
- priority passes are explicit;
- all players passing resolves the top stack object or advances an empty stack;
- copied spells are not cast;
- copied activated abilities are not activated;
- illegal actions change no state and spend no resources.

### 5. Trigger, state-based-action, and turn engines

Implement real triggered-ability objects, waiting triggers, delayed triggers, and controller assignment. An event name may not substitute for a trigger object.

Implement state-based-action stabilization and the turn structure through repeated cleanup, including actual cleanup discard, discard triggers, marked-damage removal, until-end-of-turn expiry, conditional priority, and repeated cleanup when the rules require it.

Stop execution immediately at a defined terminal state.

### 6. Hidden observations, replay, and hashing

Implement:

- domain-separated identity, shuffle, and policy RNG streams;
- per-observation opaque handles and handle revocation;
- no hidden card IDs, object IDs, card identities, library order, or future randomness in policy observations;
- exact `identity-state-v2.0.0` field-path hashing with RFC 8785 JCS and SHA-256;
- append-only actions, choices, payments, targets, transitions, and events;
- replay in a fresh process through the same production engine;
- rejection of altered, omitted, duplicated, reordered, or incompatible replay actions.

### 7. Representative production-card slice

Implement complete frozen Oracle specifications for:

- Island
- Mountain
- Sol Ring
- Opt
- Abrade
- Soul-Guide Lantern
- Commit // Memory
- Malcolm, Keen-Eyed Navigator
- Glint-Horn Buccaneer
- Dualcaster Mage
- Twinflame
- Curiosity

The ten behavior-bearing cards plus the two basic lands are the Phase A named source pool. Fictional fixtures may supplement generic tests but cannot satisfy these obligations.

### 8. Required scenarios and tests

Map every blocking requirement in the frozen identity specification to named positive or negative tests. All acceptance scenarios must run through the new production executor.

At minimum prove:

- permanent spells remain on the stack until resolution;
- priority exists before resolution and after trigger placement;
- countered permanents do not enter and do not create ETB triggers;
- Soul-Guide Lantern creates a real targeted ETB trigger only with a legal target;
- retired targets do not follow cards or successors;
- marked damage clears correctly and does not combine across turns;
- cleanup discard and repeated cleanup are rules-driven;
- every required object reincarnation creates a new ID;
- commander return is a recorded optional choice through the intermediate zone;
- Commit handles internal cards, spell copies, commanders, and modeled external objects;
- Memory is cast from the graveyard and rejects target metadata;
- Twinflame uses a real delayed trigger and token cessation path;
- Dualcaster uses a real ETB trigger and spell-copy object;
- hidden identities remain hidden;
- replay reproduces IDs, state transitions, RNG positions, event order, and final state hash;
- unsupported mechanics and capabilities fail closed.

Tests that patch away production behavior, bypass the executor, or merely assert log strings do not satisfy Phase A.

## CLI and result artifact

Add a dedicated command:

```bash
uv run mtg-sim engine verify-phase-a
```

It must run the clean-boundary check, frozen-identity check, Phase A test mapping, production-path acceptance suite, replay validation, and pilot-lock validation.

Write an immutable result artifact under:

```text
artifacts/engine/phase-a/<run-id>/result.json
```

The artifact must include:

- schema version;
- run ID;
- commit and branch;
- clean-tree status;
- exact commands;
- exact pass, fail, skip, and xfail counts;
- mapping from every blocking identity requirement to test nodes;
- Oracle and rules source hashes;
- architecture-boundary result;
- replay and hash result;
- remaining unsupported capabilities;
- final `PASS` or `FAIL`.

Skipped, xfailed, missing, or helper-only blocking tests are failures.

## Prohibited work

Do not:

- edit the frozen V2 identity document, approval record, or lock manifest;
- delete or rename `src/mtg_sim/`;
- close or merge stale pull requests;
- run the 500/200 pilot or 25,000-game study;
- migrate the remaining deck cards;
- use live Oracle or Gatherer retrieval in tests or CI;
- weaken a requirement to make a test pass;
- fabricate human approval for a transcript or result;
- report the legacy executor as the clean engine.

## Final checks

Run and report:

```bash
uv sync --frozen --all-extras
uv run python scripts/check_identity_lock.py
uv run python scripts/check_clean_engine_boundary.py
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest -q -ra
uv run python scripts/check_manifest.py
uv run mtg-sim validate-sources
uv run mtg-sim engine verify-phase-a
```

Do not report GO unless every blocking Phase A requirement passes through the clean production path, the repository is clean at the tested commit, replay is real, hidden-information checks pass, and the production pilot remains locked.

## Return

Provide:

1. branch, pull request, and commit SHA;
2. architecture summary and package dependencies;
3. files changed;
4. exact command results;
5. exact test counts;
6. blocking-requirement-to-test mapping;
7. result artifact path and digest;
8. unsupported capabilities and fail-closed behavior;
9. remaining P1 or P2 findings;
10. GO or NO-GO for independent review.
