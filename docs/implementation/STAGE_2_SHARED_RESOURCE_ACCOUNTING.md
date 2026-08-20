# Stage 2: Shared Resource Accounting

## Scope

Stage 2 is the policy-neutral prerequisite between merged PR #100 and any future Strategic Context or REQUIREMENTS_AWARE work. The branch is based on post-PR-#100 `main` at `f6ada4d656002a9942b6938c54e8565f5f9d0c7a`.

This stage does not authorize or execute a pilot, replacement pilot, full study, Strategic Context, REQUIREMENTS_AWARE policy, or exploratory-policy redesign.

## Rules basis

The resource model is grounded in the repository's frozen June 19, 2026 Comprehensive Rules source.

| Rule | Stage 2 consequence |
| --- | --- |
| 106.4 | Floating mana is held in a mana pool and empties at the end of each step and phase. A payment sequence crossing such a boundary must clear floating mana. |
| 106.6 | Mana may carry spending restrictions or additional effects. Resource production therefore records spend tags and rejects an inapplicable restricted unit. |
| 111.10a | One Treasure is one artifact with one `{T}, Sacrifice` mana ability that produces one mana of any color. It is modeled as one persistent consumable source with one unit of source capacity, not as five colored units. |
| 117.3, 117.3a-c | Payment availability is tied to ordered priority/timing windows rather than an unordered aggregate pool. |
| 302.6 | A creature mana source with a tap-symbol cost is unavailable while summoning sick unless a rules exception applies. |
| 601.2f | The total spell cost can contain mana and nonmana costs and becomes locked before payment. |
| 601.2h | The total cost must be paid completely. Partial payment is illegal. |
| 602.2b | Activated-ability payment uses the same casting payment process, so later activation costs must consume the remaining resource state rather than reconstructing a fresh pool. |
| 605.1, 605.1a | Mana abilities are modeled as production options from their battlefield source and share that source's tap/sacrifice capacity. |

## Authoritative model

`src/mtg_kernel/resource_payment.py` owns ordered resource feasibility. Its public result reports:

- Feasibility.
- Ordered payment-step results.
- Canonical semantic source allocation.
- First failed payment step.
- Remaining source capacity.
- Colored-pip, colorless, and generic deficits.
- Explicit reason codes.
- Remaining produced mana and modeled payment windows.

The solver is capacity constrained and backtracking rather than greedy. A source may not be used twice unless its modeled capacity and an explicit untap transition allow another use.

`src/mtg_kernel/resource_sources.py` is the current-state adapter. It converts public/controlled battlefield mana sources and the player's current floating pool into the solver model. Alternate mana abilities on one permanent share one physical source capacity. Treasure is a persistent, tap-and-sacrifice, flexible-color source. Hidden library order is not an input.

`mtg_kernel.mana.pay_mana()` remains the low-level atomic primitive for mana that has already been produced. Stage 2 does not replace execution payment with a strategic forecast.

## Current consumers

`src/mtg_measure/combo_access.py` now routes current combo resource questions through `solve_state_payment()` instead of maintaining separate floating-pool and Treasure heuristics.

The shared result is used for:

- Dualcaster plus Twinflame/Electroduplicate ordered costs.
- Malcolm/Glint-Horn `sufficient_mana` and `legally_executable`.
- Malcolm/Glint-Horn full-table-kill payment across generated Treasure waves.
- Lightning-Rig Crew/Crab Umbra/Malcolm repeated untap payments across generated Treasure waves.
- Curiosity casting in the Niv-Mizzet package.
- Psychosis Crawler casting.
- Protection affordability after a candidate combo line.

The known floating-pool/Treasure contradiction is covered by a focused fixture containing floating `{R}` plus exactly one untapped Treasure for Glint-Horn's `{1}{R}` activation. The same authoritative payment result drives sufficient mana, legal execution, and combo-kill measurement.

A separate regression records the Rule 106.4 correction: mana floating in precombat main cannot be assumed to survive into a later combat payment. Persistent untapped battlefield sources may remain available across that boundary.

## Future consumers

Future Strategic Context, REQUIREMENTS_AWARE, and exploratory search should consume this resource API rather than introducing new resource counters. Stage 2 intentionally does not implement those future consumers.

## Tests-first record

The branch preserves the required tests-first sequence:

1. `3f33d48db408d0d7374a7fb8ab7fd03664fbf96a` added the low-level acceptance tests before the solver implementation.
2. `29ad9081547881c440c5817226ad189b69c10072` added state integration and Malcolm/Glint-Horn contradiction tests before the state adapter and consumer refactor.
3. Solver and integration implementation commits follow those test commits.

Expected values in those tests are hand-specified contract values, not generated from implementation output.

## Policy neutrality

Stage 2 does not intentionally modify STANDARD policy weights, action-class rankings, public semantic action-key rules, tie-break rules, or policy configuration. Any game-path change caused by a corrected resource-feasibility answer is a resource-legality/measurement correction, not a new strategic preference.

## Bridge STANDARD performance baseline

The frozen corpus is `benchmarks/stage2-bridge-standard/corpus.json` and the benchmark harness is `scripts/benchmark_stage2_standard.py`.

The benchmark uses bounded technical `STANDARD` executions through Turn 10 with normal policy actions. It does not run the pilot harness and refuses pilot flags, exploratory search seeds, or a loaded Strategic Context module.

Each trial runs in a fresh Python process and records:

- `seconds_per_10_turn_game`.
- `games_per_minute`.
- `decision_count`.
- `legal_action_count`.
- `semantic_action_class_count`.
- `broker_refresh_count`.
- `state_clone_count`.
- `replay_validation_time`.
- `fresh_replay_time`.
- `peak_memory`.

Repeated trials are summarized with median and p95 values. The harness also records corpus coverage evidence for the Stage 2 scenario classes. A provisional owner-review budget is derived with 25 percent headroom over measured p95 and is explicitly not a final performance budget.

The GitHub Actions workflow `.github/workflows/stage2-bridge-standard.yml` runs this benchmark independently of any pilot workflow and uploads the raw result for review before the result is committed as Stage 2 evidence.

## Completion evidence still required at review time

Before PR #101 is marked review-ready, the branch must contain the measured benchmark result and environment/command record, current Phase A and Phase B durable certifications for changed covered paths, and green normal CI. Historical pilot evidence must remain unchanged, and no pilot or full study may be executed.
