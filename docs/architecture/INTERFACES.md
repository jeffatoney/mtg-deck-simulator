# Phase 2 Architecture and Interface Design

This document is normative for later implementation. It defines interfaces only; no game-engine behavior is implemented in Phase 2.

## Module and API diagram

```text
Frozen sources
  -> mtg_sim.cards.registry.load_card_definitions()
  -> mtg_sim.simulation.scenario.build_scenario(seed, config)
  -> mtg_sim.engine.mulligan.apply_league_mulligan(state, policy)
  -> mtg_sim.domain.observation.make_observation(state, viewer)
  -> mtg_sim.policies.Policy.choose_action(observation)
  -> mtg_sim.engine.validator.validate_action(state, action)
  -> mtg_sim.engine.executor.apply_action(state, action)
  -> mtg_sim.domain.events.EventLog.append(events)
  -> mtg_sim.audit.replay.replay(events, manifest)
  -> mtg_sim.audit.invariants.validate_replay(replayed_state, events)
  -> mtg_sim.reporting.metrics.summarize(results, manifest)
```

All standard policy, exploratory search, and replay validation callers use the same `validate_action(state, action, context)` contract before mutation.

## Package and file layout

```text
src/mtg_sim/
  domain/{cards.py,instances.py,players.py,zones.py,mana.py,state.py,observation.py,actions.py,events.py,stack.py,seeds.py,results.py}
  engine/{validator.py,executor.py,turns.py,priority.py,stack.py,combat.py,mulligan.py,commander.py,state_based_actions.py,replacement_effects.py,triggers.py}
  cards/{registry.py,coverage.py,primitives.py,mana_sources.py,draw_selection.py,tutors.py,interaction.py,combo_cards.py,split_cards.py}
  policies/{protocol.py,config.py,mulligan.py,development.py,tutor.py,combo.py,protection.py,bundles.py}
  search/{belief.py,sampler.py,beam.py,evaluation.py,safeguards.py}
  simulation/{scenario.py,shuffle_schedule.py,runner.py,sharding.py,aggregation.py,manifests.py}
  audit/{replay.py,invariants.py,sample_selection.py,decode.py}
  reporting/{schemas.py,metrics.py,statistics.py,exports.py}
```

## Data schemas

Schemas are immutable Pydantic models or frozen dataclasses unless noted.

### CardDefinition

Fields: `card_key`, `oracle_name`, `oracle_id`, `mana_cost`, `type_line`, `oracle_text`, `colors`, `color_identity`, `faces`, `legalities`, `source_hash`, `coverage_status`, `handler_id`, `reviewed_by`, `review_notes`.

### CardInstance

Fields: `instance_id`, `card_key`, `owner_player_id`, `controller_player_id`, `current_zone`, `zone_index`, `is_commander`, `face_state`, `tapped`, `damage_marked`, `counters`, `attachments`, `continuous_effect_refs`, `created_by_event_id`.

### PlayerState

Fields: `player_id`, `role`, `life_total`, `poison_counters`, `hand_ids`, `library_ids_ordered_hidden`, `graveyard_ids`, `exile_ids`, `battlefield_ids`, `command_zone_ids`, `mana_pool`, `land_plays_available`, `commander_cast_counts`, `combat_damage_by_commander`, `lost`, `win_status`.

### GameState

Fields: `game_id`, `rules_source_hash`, `oracle_snapshot_hash`, `players`, `active_player_id`, `priority_player_id`, `turn_number`, `phase`, `step`, `stack`, `pending_triggers`, `replacement_effects`, `continuous_effects`, `scenario_seed`, `rng_stream_positions`, `event_cursor`, `terminal_state`, `state_hash`.

### Observation

Fields: `observer_player_id`, `public_state_hash`, `visible_zones`, `known_hand_ids`, `known_exile_ids`, `revealed_cards`, `library_size_by_player`, `unseen_card_multiset`, `legal_action_summaries`, `mana_pool`, `turn_context`, `policy_memory`, `belief_state_seed_refs`.

### Action

Fields: `action_id`, `actor_player_id`, `action_type`, `source_instance_id`, `mode`, `targets`, `cost_selections`, `mana_payment_plan`, `additional_costs`, `replacement_choice`, `trigger_order`, `metadata`, `declared_from_observation_hash`.

### Event

Fields: `event_id`, `game_id`, `sequence_number`, `event_type`, `actor_player_id`, `source_instance_id`, `payload`, `pre_state_hash`, `post_state_hash`, `rng_stream`, `rng_draw_index`, `parent_event_id`, `rules_refs`, `created_at_logical_time`.

### StackObject

Fields: `stack_object_id`, `controller_player_id`, `source_instance_id`, `object_type`, `spell_or_ability_name`, `modes`, `targets`, `costs_paid`, `mana_value`, `is_copy`, `copied_from`, `triggered_by_event_id`, `resolution_handler_id`.

### ManaPool

Fields: `player_id`, `generic`, `white`, `blue`, `black`, `red`, `green`, `colorless`, `conditional`, `source_restrictions`, `expires_at_step`, `payment_history`.

### PolicyConfig

Fields: `policy_config_id`, `schema_version`, `bundle_name`, `mulligan_policy`, `development_policy`, `tutor_priority_table`, `combo_priority_table`, `protection_thresholds`, `search_enabled`, `search_limits`, `opponent_choice_policy`, `baseline_assumption_profile`, `config_hash`.

### ScenarioSeed

Fields: `scenario_id`, `master_seed`, `seed_split`, `named_stream_seeds`, `mulligan_shuffle_keys_by_round`, `search_sample_streams`, `audit_selection_stream`, `tie_break_stream`, `precommitted_at`, `seed_list_hash`.

### RunManifest

Fields: `run_id`, `run_type`, `git_commit`, `dirty_tree`, `branch`, `command_line`, `python_version`, `dependency_lock_hash`, `rules_source_hash`, `oracle_snapshot_hash`, `decklist_hash`, `config_hash`, `seed_list_hash`, `policy_config_hashes`, `started_at`, `ended_at`, `worker_count`, `shards`, `test_results`, `artifact_hashes`, `status`.

### GameResult

Fields: `game_id`, `scenario_id`, `policy_config_id`, `run_id`, `terminal_status`, `terminal_turn`, `win_package`, `first_attempt_turn`, `checkpoint_access`, `mulligan_keep_level`, `first_decision_divergence`, `failure_labels`, `audit_flags`, `event_log_ref`, `result_hash`.

## Exact hidden-information boundary

Only `GameState`, executor internals, and replay hash verification may store ordered hidden libraries, unobserved opponent hidden zones, or future RNG stream positions. `Observation` may expose library counts, cards known through legal reveals, and an unseen-card multiset for belief sampling. Policies and exploratory search must never receive ordered hidden zones, the executor RNG object, future shuffle keys, or validation seed labels after discovery results are known.

## Shared legality-validator contract

`validate_action(state, action, context) -> ValidationResult` is pure and returns `accepted`, `errors`, `warnings`, `required_events`, `normalized_action`, and `rules_refs`. `executor.apply_action` must reject any action not accepted by this validator. Replay calls the same validator against reconstructed pre-state and logged normalized action. Search action generation may propose actions, but only validator-accepted actions can be evaluated.

## Replay contract

Replay starts from the manifest, frozen sources, scenario seed, and initial deck instances. It re-applies logged normalized actions and deterministic RNG draws, verifies every event's pre/post hash, rejects terminal-state continuation, and emits an audit report containing invariant checks, action legality checks, hidden-information checks, and artifact hashes. Replay must not call policy decision code or change the event sequence.

## Artifact directory structure

```text
artifacts/runs/<run_id>/
  manifest.json
  config.snapshot.toml
  source_hashes.json
  dependency_lock.txt
  test_results.json
  seeds.csv
  shards/<shard_id>/{manifest.json,events.jsonl.zst,game_results.parquet,stdout.log,stderr.log}
  events.jsonl.zst
  game_results.parquet
  policy_discovery.csv
  policy_validation.csv
  paired_differences.csv
  exploratory_search_logs.jsonl.zst
  audit_selection.csv
  audit_results.csv
  decoded_games/
  summary.json
  quarantine_reason.txt
```

## Phase gates

1. Source freeze: inventory hashes match frozen rules, Oracle snapshot, decklist, commanders, and baseline config.
2. Architecture: ADRs, interfaces, and traceability matrix are reviewed.
3. Core domain/RNG: schemas, seed streams, shuffle schedules, and hidden-boundary tests pass.
4. Rules engine: shared validator, executor, stack, combat, mulligan, and state-based action competency tests pass.
5. Card coverage: every deck card has reviewed coverage and no `BLOCKED` entries.
6. Policy framework: policy configs are frozen and observation-only tests pass.
7. Exploratory search: search limits and no-future-information tests pass.
8. Pilot dry run: prints exact execution counts and writes no empirical pilot results.
9. Pilot authorization: only after competency tests pass on the same commit.
10. Pilot audit/report: repeated audit errors trigger complete rerun.
11. Full study authorization: explicit user approval after pilot report; never implied.

## Threat model

- Fabricated results: manifests require command line, commit, test results, raw event logs, hashes, and replayable artifacts.
- Hidden future-library leakage: `Observation` excludes ordered libraries and actual future RNG; tests compare policy-visible objects to hidden state.
- Selective seed replay: precommitted seed lists and run manifests record discovery/validation split and reject missing or duplicated seeds.
- Post-result optimization: policy configs and search procedures are frozen before results; validation seeds remain untouched until finalist selection.
- Stale tests: manifests record test result artifacts for the exact commit and dirty-tree state.
- Mixed-run aggregation: aggregation rejects mixed commits, configs, source hashes, dependency locks, failed shards, gaps, and duplicate seeds.
- Unsupported-card fallback: registry coverage gate fails closed for missing, blocked, or unreviewed handlers.
