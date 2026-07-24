# Phase A — Clean Rules Kernel and Vertical Slice

Repository: `jeffatoney/mtg-deck-simulator`

## Existing branch and pull request

Work only on the existing branch:

`recovery/phase-a-rules-kernel`

Work only in its existing draft pull request. Do not create another branch or
pull request. Do not modify, merge, or close PR #29, and do not push to the PR
#29 branch.

Keep agent internet access OFF. Do not start Phase B. Do not run the 500/200
pilot or the 25,000-game study.

## Read first — immutable inputs

1. `AGENTS.md`
2. `tests/acceptance/PHASE_A_ACCEPTANCE_SPEC.md`
3. `automation/architecture-invariants.json`
4. `scripts/check_architecture_invariants.py`
5. Frozen Comprehensive Rules and Oracle sources under `docs/source/`

The acceptance specification and its frozen hash may not be changed. If a
requirement is genuinely impossible or contradictory, stop and return NO-GO;
do not weaken the requirement or its tests.

## Recovery boundary

Build the clean kernel in parallel with the quarantined legacy implementation.
The legacy source may remain temporarily so existing CI stays green, but the new
packages must not import or execute it. Phase B migrates the remaining cards and
promotes the new kernel to the production pilot.

Create the clean packages required by the invariant configuration:

- `src/mtg_kernel/` — card-agnostic rules kernel
- `src/mtg_cards/` — structured card specifications

The kernel may contain no vertical-slice card-name branches. It interprets
structured specs and universal rules.

## Required architecture

### 1. Object identity

Implement stable IDs and ownership for:

- `CardInstance`
- `GameObject`
- `PermanentObject`
- `SpellObject`
- `AbilityObject`
- `TriggeredAbilityObject`
- `ExternalObjectRef`

Every internal zone stores IDs only. A real card object keeps the same
`instance_id` through every zone. Tokens and copies have object IDs but never
become fabricated cards.

### 2. Zone service

`ZoneService` is the only service that moves internal objects between zones. It
handles:

- owner-correct destinations
- commander replacement choices
- tokens and copies ceasing to exist
- moving opponent-owned objects through `ExternalZoneLedger`
- exact library positions such as second from the top

No card specification or executor may directly mutate a zone.

### 3. Casting and activation pipeline

One pipeline handles every nonland spell and activated ability:

propose → choose face/modes/targets/X → validate → determine and pay costs →
move the actual object to the stack → priority → resolve/counter → move to the
legal destination → state-based actions → waiting triggers → priority.

Permanent spells never bypass the stack. Commander cast counts and tax are
handled by this pipeline.

### 4. Stack and priority

Implement real stack objects, priority passes, target revalidation, resolution,
countering, spell-copy cessation, and deterministic external actions. A log line
may never substitute for a stack object.

### 5. Trigger engine

Events are matched to structured trigger definitions. The engine creates real
`TriggeredAbilityObject` instances, selects legal targets, places them on the
stack, opens priority, rechecks targets, and resolves them. Only the stack
service emits `trigger_put_on_stack`, at the moment a real object is added.

### 6. Turn engine

`TurnEngine` exclusively owns phases and steps, including:

- untap, upkeep, draw
- precombat main
- beginning of combat, attackers, combat damage, end of combat
- postcombat main
- end step
- complete cleanup

Cleanup includes maximum-hand-size discard, real discard triggers, marked-damage
removal, until-end-of-turn expiry, state-based actions, waiting triggers,
conditional priority, and complete repeated cleanup steps. `GameExecutor` may
not assign phases or steps directly.

### 7. Minimal external-opponent boundary

Do not build opponent decks. Model only explicitly scripted public objects and
choices:

- external spells
- external permanents
- external attackers
- external graveyard cards
- external commanders

When an external object leaves the active model, record owner, destination,
position, and cessation state in `ExternalZoneLedger`. No opponent-owned object
may enter the simulated player's zones.

Implement scenario `opponent_counter_on_first_commander` exactly as required by
acceptance item E2. Baseline and interaction-scenario artifacts remain separate.

### 8. Structured vertical-slice card specifications

Implement structured specs, not game-flow code, for:

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

Specs declare costs, zones, timing, modes, targets, effects, static abilities,
trigger conditions, and delayed triggers. Universal processing belongs in the
kernel.

Memory declares zero targets, so the generic action validator must reject target
metadata without a Memory-specific patch. Commit declares “target spell or
nonland permanent” and “put second from the top of its owner’s library”; the
zone service handles real cards, copies, tokens, commanders, and external
objects.

### 9. Replay

Persist initial state, named RNG streams, actions, choices, payments, targets,
and state hashes. Replay reconstructs and re-executes the game through the same
kernel. It may not trust terminal or event-log claims.

### 10. Commands and gates

Add a Typer command that preserves the requested interface:

`uv run mtg-sim recovery kernel`

It must run:

- the architecture invariant gate
- collection checks for all acceptance IDs A1–G4
- all Phase A acceptance tests
- replay validation
- production-pilot lock validation

Write:

`artifacts/recovery/kernel/result.json`

with commit, clean-tree status, exact test counts, acceptance-ID mapping,
architecture result, and PASS/FAIL status.

Update `validate-prepolicy-readiness` so it also requires this Phase A gate.
Do not make the production pilot executable.

## Acceptance tests

Implement every requirement under `tests/phase_a_acceptance/` with node names
beginning with its exact ID. Tests must use the new
`mtg_kernel.executor.GameExecutor` path. Isolated helper tests do not satisfy the
spec.

Port useful scenarios from PR #29 as requirements or fixtures, but do not port
its `setattr` patch architecture, direct zone mutation, direct stack mutation,
or event-log-as-engine behavior.

## Required commands before final review

```bash
uv sync --frozen --all-extras
uv run python scripts/check_architecture_invariants.py
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest -q -ra
uv run python scripts/check_manifest.py
uv run mtg-sim validate-sources
uv run mtg-sim validate-coverage
uv run mtg-sim validate-executable-coverage
uv run mtg-sim validate-prepolicy-readiness
uv run mtg-sim recovery kernel
uv run mtg-sim pilot --config configs/pilot.toml --dry-run
```

Do not run a non-dry production pilot. Do not use the legacy smoke run as proof
of the new kernel.

## Return

1. Files changed
2. Architecture diagram and service responsibilities
3. Mapping of every acceptance item A1–G4 to collected test node and result
4. Exact result of every required command
5. Final pytest counts
6. Recovery artifact path and contents summary
7. Any unsatisfied requirement and reason
8. Remaining P1/P2 findings
9. GO or NO-GO for independent review
10. Branch and commit SHA

Return NO-GO unless every acceptance item passes through the new
`mtg_kernel.executor.GameExecutor`, the architecture gate passes, existing CI
passes, replay is real, and the production pilot remains locked.
