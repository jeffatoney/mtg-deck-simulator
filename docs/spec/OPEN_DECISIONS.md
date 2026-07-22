# Open decisions and required explicit assumptions

Phase 1B resolves the baseline-blocking assumptions below for source validation and future baseline runs. No baseline decision remains blocking after this phase.

## 1. Exotic Orchard and Fellwar Stone

Resolved baseline: `primary_opponent_mana_profile = "blue_red_available"`.

Resolved sensitivity profile: `sensitivity_opponent_mana_profile = "no_known_colors"`.

The baseline must never silently treat these cards as Command Tower; implementations must read the configured opponent mana profile.

## 2. Opponent choices required by cards

Resolved baseline: `fact_or_fiction_policy = "minimize_deck_frozen_evaluation"`.

Opponent-choice effects must enumerate legal choices and select the choice minimizing this deck's frozen evaluation function, recording the chosen option and score when the engine exists.

## 3. Opponent battlefield scope

Resolved baseline: `opponent_mana_lands_are_targetable = false` and `opponent_mana_lands_are_abstract_metadata = true`.

Opponent mana-profile lands are abstract metadata only and do not create unspecified targets.

## 4. Recovery after losing a first line

Resolved baseline: `baseline_recovery_measurement = "independent_second_line_availability"`.

Resolved separation requirement: `true_disrupted_recovery_study = "separate"`.

True disrupted recovery is not part of baseline percentages and requires a separate scripted perturbation study if authorized.

## 5. Oracle snapshot

Resolved baseline: current Oracle data is frozen under `docs/source/oracle/snapshot_v1.json` with live fetching disabled during tests and simulations. A later Oracle refresh must create a new snapshot version and a new hash.

## 6. Policy-run counts

Resolved baseline: the canonical pilot remains 500 standard plus 200 exploratory games; future dry-run tooling must print all replay and candidate-policy execution counts before execution.

## 7. Breeches unknown cards

Resolved baseline: `breeches_unknown_cards = "record_trigger_but_exclude_from_deterministic_resources"`.
