# Coded pilot protocol

Do not run the full 25,000-game study.

## Canonical pilot sizes

- 500 canonical standard-policy games
- 200 exploratory games paired with canonical Standard Games 1–200

## Policy discovery and validation

- Precommit 500 base standard seeds.
- Recommended split: 300 discovery seeds and 200 validation seeds, recorded in `configs/pilot_split.json` before any policy results are generated.
- Evaluate candidate policies on paired discovery seeds.
- Select a small finalist set using discovery results only.
- Evaluate all finalists on the untouched validation seeds.
- Lock a preliminary standard policy and then generate the 500 canonical standard-game outcomes.
- Report the number of base seeds, policy-evaluation runs, canonical standard games, and exploratory games separately.

## Audit requirements

Fully decode and inspect:

- 50 randomly selected canonical standard games
- 25 randomly selected exploratory games
- Every Turn 3 or Turn 4 win
- Every unfamiliar or nonstandard line
- At least ten mulligans to four
- At least ten games classified as one piece short
- At least ten games where the simulator delayed a combo for protection

If the canonical pilot does not naturally contain ten examples of a required category, generate supplemental audit-only scenarios. Label them clearly and exclude them from pilot percentages.

Check mana payments, land sequencing, targets, timing, stack order, combat legality, tutor legality, commander tax, future-information access, conditional-loop classification, and whether a materially better legal decision was obviously available.

If a repeated error is found:

1. Quarantine the run without deleting it.
2. Add a regression test.
3. Correct the engine.
4. Rerun the full competency suite.
5. Rerun the entire pilot with a new run ID.

## Required pilot report

1. Rules or coding errors discovered
2. Corrections made
3. Audit pass rate
4. Candidate policy results on discovery seeds
5. Candidate policy results on validation seeds
6. Preliminary best-performing policies
7. Policies whose performance is too close to distinguish
8. Simulation choices that still materially affect results
9. Ten representative decoded games
10. Clear go/no-go recommendation for the full study

Pilot percentages are preliminary and must not be presented as final deck conclusions.
