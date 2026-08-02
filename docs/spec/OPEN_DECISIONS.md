# Open decisions and required explicit assumptions

This document records baseline assumptions that must be explicit before policy discovery, pilot execution, or the full study. The corrective slice adds strategic-evaluator and learning controls; it does not authorize any outcome-generating run.

## 1. Exotic Orchard and Fellwar Stone

Resolved baseline: `primary_opponent_mana_profile = "blue_red_available"`.

Resolved sensitivity profile: `sensitivity_opponent_mana_profile = "no_known_colors"`.

The baseline must never silently treat these cards as Command Tower. Implementations must read the configured opponent mana profile.

## 2. Opponent choices required by cards

Resolved baseline: `fact_or_fiction_opponent_mode = "PERFECT_MINIMIZER"`.

The opponent may use all legally revealed information and select the legal split that minimizes the caster's best contextual evaluation. This is a conservative worst-case model, not a claim about typical human play. The selected split, evaluator identity, evaluator SHA-256, and fixed-point diagnostics must be recorded.

The rules kernel may reveal cards, enumerate legal splits, validate a returned choice, and move cards. It may not value cards or choose either pile.

## 3. Caster strategic evaluation

Resolved baseline evaluator: `contextual_combo_v1` under `configs/evaluators/contextual_combo_v1.yaml`.

The evaluator must account for current turn, lands already in play, needed versus excess lands, visible combo progress, combo completion, redundancy, protection, and payability. Every declared exact-deck effect kind must have an explicit reviewed classification. Missing classifications fail closed. An intentional neutral classification must be named explicitly rather than produced by a missing lookup.

## 4. Adjustable and learned evaluator snapshots

Resolved architecture: evaluator parameters are adjustable configuration fields rather than rules-engine constants.

Resolved learning mode: `DISCOVERY_ONLY_FROZEN_SNAPSHOT`.

Resolved allocation: 4,800 discovery comparisons from the exact 300 discovery seeds (16 per seed) and 1,000 validation comparisons from the exact 200 validation seeds (5 per seed). The first 200 discovery seeds are the mining/training partition; the remaining 100 are the confirmation partition. The feature set freezes before the final refit on all discovery comparisons.

Resolved label contract: paired alternatives use the same initial state, future RNG streams, continuation policy, policy-visible information, and Turn-10-or-terminal horizon. The label is the frozen lexicographic `OutcomeVector`; ties are excluded and reported.

Resolved promotion bar: at least +3.0 percentage points over the human evaluator on paired validation accuracy, seed-clustered 95% confidence lower bound above zero, and no regression in cumulative table-kill access at Turns 5/6/8/10, full-table-kill rate, or median earliest legal-attempt turn.

Resolved organic discovery mode: `REVIEW_ONLY_HYPOTHESIS_RANKING`. Raw records preserve policy-visible card identities/zones and action order so card-pair and action-sequence candidates can be identified after discovery collection. Candidates require frozen support thresholds and confirmation, make no uncorrected significance claim, and may not alter weights, features, combo packages, or live decisions automatically.

The frozen learning plan is stored at `configs/evaluators/learning_plan_v1.yaml` and content-hashed despite its historical filename. Any count, threshold, label, partition, or promotion change requires a new plan hash before examples are generated.

No learning comparisons have been executed.

## 5. Tutor selection timing

Resolved baseline: `tutor_choice_timing = "RESOLUTION"`.

The policy selects a legal identity when the search instruction resolves. Transmute and typecycling actions do not precommit an identity at activation. Failing to find is legal when the searched hidden zone uses a stated quality. A wrong-quality card may never be offered by the broker or moved to hand.

## 6. Dualcaster Mage and Twinflame loop

Resolved interim status: `FAIL_CLOSED_UNTIL_DETERMINISTIC_LOOP_ADJUDICATOR`.

An audit-only bounded witness may demonstrate copied-spell identity, token Dualcaster triggers, and an explicit stopping choice. The canonical policy may not treat a fixed number of tokens as the combo result. Phase B remains blocked until the legal repeatable loop can be recognized, bounded by a declared player choice, and translated into the modeled table-win outcome without approximation.

## 7. Opponent battlefield scope

Resolved baseline: `opponent_mana_lands_are_targetable = false` and `opponent_mana_lands_are_abstract_metadata = true`.

Opponent mana-profile lands are abstract metadata only and do not create unspecified targets.

## 8. Recovery after losing a first line

Resolved baseline: `baseline_recovery_measurement = "independent_second_line_availability"`.

Resolved separation requirement: `true_disrupted_recovery_study = "separate"`.

True disrupted recovery is not part of baseline percentages and requires a separately authorized scripted perturbation study.

## 9. Oracle snapshot

Resolved baseline: current Oracle data is frozen under `docs/source/oracle/snapshot_v1.json` with live fetching disabled during tests and simulations. A later Oracle refresh must create a new snapshot version and hash.

## 10. Policy-run counts

The canonical pilot remains 500 standard plus 200 exploratory games. Policy-learning examples, policy-screening evaluations, validation evaluations, canonical games, exploratory games, and audit-only scenarios must be reported as separate counts.

## 11. Breeches unknown cards

Resolved baseline: `breeches_unknown_cards = "record_trigger_but_exclude_from_deterministic_resources"`.
