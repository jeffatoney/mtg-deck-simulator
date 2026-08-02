# Coded pilot protocol

Do not run the full 25,000-game study.

## Pre-pilot evaluator discovery

Evaluator learning is optional but must occur before canonical pilot outcomes. The frozen plan permits 4,800 discovery comparisons (300 frozen seeds × 16) and 1,000 untouched validation comparisons (200 frozen seeds × 5). These are decision comparisons, not canonical pilot games, and must be reported separately.

The learning stage must:

1. Generate both alternatives from the same initial state, future RNG streams, continuation policy, information boundary, and Turn-10-or-terminal horizon.
2. Use the first 200 discovery seeds for fitting and candidate mining, then the remaining 100 discovery seeds only to confirm candidate direction and support.
3. Freeze the feature set and candidate report before refitting on all 4,800 discovery comparisons.
4. Preserve hidden-information-safe raw card, zone, action-order, mana, combo, protection, and counterfactual-outcome records before any discovery comparison is spent.
5. Surface generic-feature, card-pair, and action-sequence hypotheses for human review; no mined relationship activates automatically.
6. Freeze a content-addressed candidate snapshot before inspecting validation outcomes.
7. Evaluate the frozen snapshot once on 1,000 untouched validation comparisons.
8. Promote only when paired accuracy improves over the human evaluator by at least 3.0 percentage points, the seed-clustered 95% confidence lower bound is above zero, and checkpoint table-kill access, full-table-kill rate, and median earliest legal-attempt turn do not regress.
9. Bind the selected evaluator ID, evaluator SHA-256, learning-plan SHA-256, data hashes, feature-set hash, and candidate-report hash into all later policy and run manifests.

A failed validation snapshot remains an immutable rejected artifact. Validation outcomes may not be used to revise the candidate and reuse the same validation set. No evaluator may learn or mutate during canonical or exploratory execution.

## Canonical pilot sizes

- 500 canonical standard-policy games
- 200 exploratory games paired with canonical Standard Games 1 through 200

## Policy discovery and validation

- Precommit 500 base standard seeds.
- Use the recorded 300 discovery and 200 validation seed split before any policy result exists.
- Evaluate candidate policies and already frozen evaluator snapshots on paired discovery seeds.
- Select a small finalist set using discovery results only.
- Evaluate all finalists on untouched validation seeds.
- Lock the preliminary standard policy and evaluator snapshot before generating canonical outcomes.
- Report learning examples, base seeds, policy-evaluation runs, validation runs, canonical standard games, and exploratory games separately.

## Audit requirements

Fully decode and inspect:

- 50 randomly selected canonical standard games
- 25 randomly selected exploratory games
- Every Turn 3 or Turn 4 win
- Every unfamiliar or nonstandard line
- At least ten mulligans to four
- At least ten games classified as one piece short
- At least ten games where the simulator delayed a combo for protection
- Every use of a newly promoted learned interaction feature in the audit sample

If the canonical pilot does not naturally contain ten examples of a required category, generate supplemental audit-only scenarios. Label them clearly and exclude them from pilot percentages.

Check mana payments, land sequencing, targets, timing, stack order, combat legality, tutor legality, commander tax, evaluator snapshot identity, future-information access, conditional-loop classification, and whether a materially better legal decision was obviously available.

If a repeated error is found:

1. Quarantine the run without deleting it.
2. Add a regression test.
3. Correct the engine, policy, evaluator, or measurement layer.
4. Rerun the full competency suite and recertify affected surfaces.
5. Rerun the entire pilot with a new run ID and, when applicable, a new evaluator snapshot ID.

## Required pilot report

1. Rules, policy, evaluator, or coding errors discovered
2. Corrections made
3. Audit pass rate
4. Evaluator-learning and holdout-validation results, reported separately
5. Candidate policy results on discovery seeds
6. Candidate policy results on validation seeds
7. Preliminary best-performing policies and evaluator snapshots
8. Policies whose performance is too close to distinguish
9. Simulation choices that still materially affect results
10. Turn distribution for earliest legal attempt, actual attempt, and terminal outcomes
11. Ten representative decoded games
12. Clear go/no-go recommendation for the full study

Pilot percentages are preliminary and must not be presented as final deck conclusions.
