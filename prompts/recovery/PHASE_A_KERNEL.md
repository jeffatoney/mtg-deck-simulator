# Phase A — Clean Rules Kernel and Vertical Slice

Repository: `jeffatoney/mtg-deck-simulator`

## Branch and draft pull request

Verify that the current branch is:

`recovery/phase-a-rules-kernel`

If that branch or its draft pull request does not exist, create exactly that
branch from `origin/main` and exactly one draft pull request titled **Phase A:
Replace the simulation rules kernel**. Create no other branch or pull request.
Do not modify, merge, or close PR #29, and do not push to the PR #29 branch.

Keep agent internet access OFF. Do not start Phase B. Do not run the 500/200
pilot or the 25,000-game study.

## PHASE A BASE-STATE GUARD — first required action

Before editing any file:

1. Verify these files exist:
   - `tests/acceptance/PHASE_A_ACCEPTANCE_SPEC.md`
   - `automation/frozen-spec-sha256.txt`
   - `automation/architecture-invariants.json`
   - `scripts/check_architecture_invariants.py`
   - `prompts/recovery/PHASE_A_KERNEL.md`
   - `.github/workflows/architecture-gate.yml`
2. Verify the SHA-256 of the specification matches
   `automation/frozen-spec-sha256.txt`.
3. Run `uv run python scripts/check_architecture_invariants.py` and confirm it
   executes. Before the kernel exists, the only acceptable findings are
   `MISSING_REQUIRED_PATH` findings.

If any check fails, stop and return exactly:

`NO-GO — Phase A branch was not created from the post-setup main branch.`

Do not create a replacement gate, an alternate checker, or a kernel under
`src/mtg_sim`, and do not continue using the legacy `GameExecutor` as the normal
game path.

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

The architecture gate must enforce project-local dependency closure: no clean
kernel or card implementation may be delegated to a project-local package that
is outside the configured, scanned `enforced_paths`. No support implementation
may live outside those enforced packages.

Run the acceptance suite only with the configuration boundary
`--confcutdir=tests/phase_a_acceptance`. Any Phase A `conftest.py` must live
inside that directory and be scanned by the gate. Parent conftests and
unscanned project-local test helpers must not influence or supply acceptance
behavior. The `mtg-sim recovery kernel` command must use this same isolated
invocation.

Acceptance tests may not replace or delete protected kernel behavior, whether
through direct assignment, patch helpers, reflective `setattr`/`delattr`
variants, or direct/transitive aliases of those operations.

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

## Gate v2 protected evidence and causal liveness

The authoritative examiner is the immutable protected-`main` referee, not any
candidate copy. It stages only candidate `src/mtg_kernel/` and
`src/mtg_cards/` with frozen reference evidence. Physical absence is the
primary boundary; the frozen meta-path import finder, module-origin checks, and
static scanner are defense in depth. Candidate tests, root modules, parent
`conftest.py`, `src/mtg_sim/`, workflows, scripts, and helpers are never staged.
Skipped or xfailed reference items are failures.

Deliver `scripts/check_kernel_liveness.py`. The referee must invoke the public
`mtg_kernel.executor.GameExecutor.run` in actual end-to-end games and obtain
causal evidence for action generation and validation, cost determination and
payment, stack push, priority pass, resolution, target revalidation,
`ZoneService` movement, state-based-action stabilization, trigger creation and
placement, `TurnEngine` cleanup, `ExternalZoneLedger` movement, and replay.
Evidence requires all three independent classes: referee-observed call trees
with code-object/file provenance; observed pre/post state transitions correlated
to those calls; and candidate receipts checked against those observations.
Setup probes, helper-only tests, disconnected facades, and coverage alone do not
count. Each receipt includes run, game and action IDs; service and operation;
source object ID when applicable; pre/post hashes; and causal event IDs.

## Frozen scenarios, trace properties, and golden replay evidence

Implement every frozen forced scenario in `automation/reference-scenarios.json`
and at least 200 deterministic random-seed games for trace-property testing.
Random games never replace forced scenarios. Enforce every invariant in
`automation/trace-invariants.json`. The five setup fixtures are deliberately
marked `draft-needs-human-review`; Phase A **must not merge** until a separately recorded
human approval advances each complete transcript to `independently-reviewed`.
No reviewer identity, date, or approval may be invented. Candidate-authored
expected outcomes are not evidence. Replay must execute through the public
`ReplayEngine` in a fresh state and reproduce action and event order, named RNG
streams, external ledger, object identities, zone contents, life totals, and
final state hashes; altered, omitted, duplicated, or reordered actions must be
rejected.

Candidate verdict fields (`satisfied_acceptance_ids`, `postconditions`,
`trace_invariants`, and `referee_observations`) are prohibited. The candidate
emits objective raw facts only. The protected referee derives every acceptance,
scenario, invariant, and liveness verdict from those facts and profiler-owned
observations.

## Simulation Analytics Contract

Phase A is an instrumented decision laboratory. The engine emits objective,
append-only, causally linked raw records for events, actions, meaningful policy
decisions, card instances, service receipts, state hashes, replay actions, and
run manifests. Every event contains schema version, run/game IDs, sequence,
turn/phase/step/priority-window, actor, type, source card-instance/object IDs,
target IDs, parent action/event IDs, pre/post hashes, and structured payload.
It must not label raw facts as combo/protection/second-line access,
strandedness, high-value draw, or strategic optimality; those are derived Phase
B meanings.

At every meaningful decision record decision ID, policy-visible observation
hash, complete canonical legal-action set, selected action ID, policy
ID/version, action-set hash, candidate scores, search branch/depth/node counts
when applicable, and `future_information_used=false`. Any state with a legal
non-pass action is meaningful. Forced pass-throughs record counts, hash,
selected pass, and reason without repeating the full set.

Maintain separate full audit state, policy-visible observation, and post-game
analytics output. Policy/search may access only the observation. Every real
card has a stable card-instance ID; tokens and copies have object IDs and never
fabricated card instances. Phase A raw outputs are events, actions, decisions,
card instances, receipts, replay records, optional checkpoints, and manifest.

Phase B derives card lifecycles, draw impact, combo/protection access, first
attempt, second-line access, strandedness, bottlenecks, tutor value,
paired-policy differences, and model-ready features. Each derived row records
evaluator name/version/commit, metric schema version, and source event-schema
version.

Phase A merge freezes event schema v1. Later changes require a new explicit
version, compatibility classification, migration notes, preserved prior schema,
and tests. Every game records simulation mode, scenario ID/version, opponent
policy/version, blocking model, and interaction assumptions. Baseline,
exploratory, and scripted-interaction records remain separately identifiable.
All policy variants of one seed share a train/validation/test group. Live
summaries are monitoring-only and cannot alter frozen policies. Every final
statistic must reproduce from raw events.

## Phase boundaries and required checks

The production pilot workflow remains physically absent until a separately
reviewed Phase C pull request restores the inactive template. Phase A requires
all five distinct checks documented in `docs/audit/GATE_KNOWN_LIMITS.md`;
ordinary green CI alone is not GO.
