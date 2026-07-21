# Proposed architecture

## Architectural decision

Build a **deck-scoped, fail-closed simulator**, not a general Magic engine. It must fully model every legal interaction reachable from this exact deck and baseline, but it must reject unsupported states rather than invent behavior.

## Data flow

`Frozen sources -> domain state -> legality/action generation -> stack/turn executor -> card handlers -> policy observation -> standard policy or bounded search -> event log -> independent replay validator -> metrics and report`

## Core design principles

1. **One legality path.** Standard play, exploratory play, and replay all call the same action validator and executor.
2. **Hidden-information boundary.** The executor owns the ordered library. Policies receive only an observation and belief state. Search samples unknown draws from the unseen multiset, never from the true future order.
3. **Event-sourced replay.** Every state transition emits typed events with before/after hashes. A game can be decoded and replayed without rerunning policy decisions.
4. **Finite execution.** Loops are simulated iteration by iteration until win, loss, inability to pay/discard, or illegality.
5. **Deterministic randomness.** A master seed spawns named streams for shuffle schedules, search samples, audit selection, and tie-breaks. Parallel worker count cannot change outcomes.
6. **Policy as data.** Policy axes live in versioned configuration so candidate bundles can be frozen before discovery.
7. **Independent validation.** A replay/invariant validator consumes event logs and checks conservation, payments, timing, targets, state-based actions, and terminal states without reusing policy code.
8. **Immutable evidence.** Every run has a manifest, raw game records, event logs, decoded replays, and hashes. Failed runs are quarantined, not overwritten.

## Recommended package layout

```text
src/mtg_sim/
  domain/
    cards.py             # definitions and unique instances
    zones.py
    players.py
    mana.py
    turn.py
    stack_objects.py
    state.py
    observation.py       # policy-visible state only
    events.py
  engine/
    actions.py
    action_generator.py
    validator.py
    executor.py
    stack.py
    triggers.py
    state_based_actions.py
    replacement_effects.py
    combat.py
    commander.py
    mulligan.py
  cards/
    registry.py
    primitives.py
    mana_sources.py
    draw_selection.py
    tutors.py
    interaction.py
    combo_cards.py
    split_cards.py
    coverage.py
  policies/
    config.py
    features.py
    mulligan.py
    development.py
    tutor.py
    combo.py
    protection.py
    bundles.py
  search/
    belief.py
    sampler.py
    beam.py
    evaluation.py
    safeguards.py
  simulation/
    seeds.py
    shuffle_schedule.py
    scenario.py
    checkpoints.py
    runner.py
    sharding.py
  audit/
    replay.py
    invariants.py
    sample_selection.py
    manual_decode.py
  reporting/
    schemas.py
    metrics.py
    statistics.py
    exports.py
  cli.py
```

## Static and dynamic card data

- Freeze Oracle data in a committed snapshot with source, retrieval time, and SHA-256.
- Give every physical card a unique instance ID; basic lands are separate instances.
- Use reusable effect primitives for common behavior and reviewed bespoke handlers for rules-heavy cards.
- Maintain `card_coverage.csv` with `FULL`, `BASELINE_EXPLICIT`, or `BLOCKED` status and reviewer notes.
- The engine refuses to start a pilot if any library or commander entry is `BLOCKED` or missing.

## State and rules engine

`GameState` should contain all zones, ordered hidden library, hand, battlefield, graveyard, exile, command zone, stack, life/status for all four players, turn/step/priority, land plays, mana pools, attackers, commander cast counts, pending triggers, replacement choices, and empty-draw-loss flags.

The engine exposes pure or near-pure transitions where practical:

```text
legal_actions(state, observation) -> actions
validate(state, action) -> validation result
apply(state, action) -> new state + events
resolve_top(state) -> new state + events
check_state_based_actions(state) -> new state + events
```

## Seed and shuffle architecture

A base scenario has a master seed and precomputed named random streams. For league mulligans, use a deterministic random-key schedule per mulligan round so paired policies use the same shuffle process whenever their choices reach the same round. Record first policy divergence.

The policy API never receives the real RNG stream used for future draws.

## Policy discovery

Use 500 precommitted base seeds split before results. Screen a frozen matrix of policy bundles on discovery seeds, advance finalists by a documented racing rule, and evaluate all finalists on validation seeds. After validation, lock a preliminary policy and run the 500 canonical standard games. Report policy-evaluation executions separately.

## Exploratory search

Use bounded beam search with the exact limits in the specification. The search expands only legal actions from the policy-visible observation. Unknown draws are sampled from the remaining-card belief state using separate common-random-number streams. Save branch counts, node counts, depth, pruning, and the selected path.

## Outputs

Recommended run directory:

```text
artifacts/runs/<run_id>/
  manifest.json
  config.snapshot.toml
  source_hashes.json
  test_results.json
  seeds.csv
  policy_runs.parquet
  canonical_games.parquet
  exploratory_games.parquet
  events.jsonl.zst
  summary.json
  policy_discovery.csv
  policy_validation.csv
  paired_differences.csv
  audit_selection.csv
  audit_results.csv
  decoded_games/
  stdout.log
  stderr.log
```

The aggregator rejects duplicate seeds, missing shards, mixed commits, mixed configs, or failed competency-test status.
