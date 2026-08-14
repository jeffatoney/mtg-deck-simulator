# Phase C Post-Pilot Results Summary

## Pilot audit verdict

**PILOT AUDIT PASS**

The authorized pilot run `31752039318` produced a complete, replay-valid, source-bound 500 STANDARD / 200 paired EXPLORATORY dataset. All 21 GitHub artifacts, all 20 shard manifests, all 700 game records, all replay and fresh-replay hashes, the frozen pairing, and the aggregate reconstruction passed.

The full study remains unauthorized.

These figures measure combo assembly speed against opponents who take no actions. They are not win rates and do not predict performance against interactive opponents.

## Pilot results

### STANDARD

| Checkpoint | Deterministic table-win access | Rate |
|---|---:|---:|
| Turn 5 | 19 / 500 | 3.8% |
| Turn 6 | 37 / 500 | 7.4% |
| Turn 8 | 82 / 500 | 16.4% |
| Turn 10 | 113 / 500 | 22.6% |

The Turn-8 Wilson 95% interval is approximately 13.4% to 19.9%. The Turn-10 interval is approximately 19.2% to 26.5%.

Earliest deterministic access:

| Turn | Games |
|---|---:|
| 3 | 1 |
| 4 | 8 |
| 5 | 10 |
| 6 | 18 |
| 7 | 20 |
| 8 | 25 |
| 9 | 13 |
| 10 | 18 |
| No access through Turn 10 | 387 |

Actual first attempts were recorded in 125 games: Turn 4: 3, Turn 5: 13, Turn 6: 20, Turn 7: 25, Turn 8: 26, Turn 9: 19, and Turn 10: 19. Seventy attempted games never established deterministic full-table access because conditional packages can be attempted without satisfying that stricter measurement.

### Mulligans

| Final keep | Games |
|---|---:|
| First 7 | 379 |
| Free second 7 | 96 |
| 6 | 10 |
| 5 | 9 |
| 4 | 6 |

The policy used the free second seven in 121 games. At seven cards it kept every two-, three-, and four-land hand and rejected every other land count. Two-, three-, and four-land keeps had broadly similar descriptive Turn-8 and Turn-10 outcomes.

### Mana versus action density

| Checkpoint | Failed games | Action-density primary | Mana primary |
|---|---:|---:|---:|
| Turn 5 | 481 | 403 | 78 |
| Turn 6 | 463 | 381 | 82 |
| Turn 8 | 418 | 348 | 70 |
| Turn 10 | 387 | 302 | 85 |

Missing action or combo access was the larger modeled constraint. Mana remained a meaningful secondary blocker.

## Combo packages

Legal package access and deterministic full-table access are different measurements. Psychosis Crawler, and a small number of other states, can be legally executable but only conditional.

| Package | Legal T8 | Deterministic T8 contribution | Legal T10 | Deterministic T10 contribution |
|---|---:|---:|---:|---:|
| Malcolm / Glint-Horn | 77 | 77 | 108 | 107 |
| Dualcaster / Twinflame | 3 | 3 | 5 | 5 |
| Dualcaster / Electroduplicate | 2 | 2 | 2 | 2 |
| Psychosis Crawler draw | 72 | 0 | 98 | 0 |
| Lightning-Rig / Crab Umbra / Malcolm | 0 | 0 | 1 | 0 |
| Niv-Mizzet / Curiosity | 0 | 0 | 0 | 0 |

Malcolm / Glint-Horn generated nearly all deterministic access: 77 of 82 Turn-8 contributions and 107 Turn-10 contributions. One Turn-10 game overlapped with Twinflame, producing 113 unique STANDARD games with access rather than 114 summed package contributions.

## Commanders

Malcolm was first cast most often on Turn 3. Earlier Malcolm casts were descriptively associated with stronger access and directly supported the dominant Malcolm / Glint-Horn package. This is supportive evidence for the frozen Malcolm-first development plan, not proof that Malcolm must always be cast immediately.

Breeches was cast 449 times across the pilot but had no deterministic combo-contribution tags. Under the frozen restriction excluding unknown opponent cards, the pilot does not show a material deterministic-resource benefit from Breeches.

## Tutors and card selection

Most common recorded tutor targets:

- Long-Term Plans: Glint-Horn Buccaneer 48, Curiosity 16;
- Step Through: Dualcaster Mage 83, Niv-Mizzet 16;
- Vedalken Aethermage: Dualcaster Mage 48, Niv-Mizzet 24;
- Muddle the Mixture: Twinflame 41;
- Drift of Phantasms: Glint-Horn Buccaneer 40;
- Dizzy Spell: Crab Umbra 21.

Drift of Phantasms and Long-Term Plans had the clearest useful descriptive associations. Vedalken Aethermage was frequently used, mainly for Dualcaster Mage or Niv-Mizzet. All 109 Invert // Invent casts used Invert; the policy never selected Invent.

## Exploratory findings

EXPLORATORY recorded zero deterministic full-table access and zero actual attempts through Turn 10.

Paired Turn-8 result:

| Cell | Pairs |
|---|---:|
| Both access | 0 |
| STANDARD only | 37 |
| EXPLORATORY only | 0 |
| Neither | 163 |

- paired difference: -18.5 percentage points;
- discordant pairs: 37;
- exact two-sided McNemar p-value: `1.4551915228366852e-11`;
- paired-bootstrap 95% interval: -24 to -13 percentage points.

All 200 EXPLORATORY games first diverged on Turn 1 precombat main. STANDARD selected `PLAY_LAND`; EXPLORATORY selected `PASS_PRIORITY`. The same divergence occurred in all 37 STANDARD-only Turn-8 pairs.

The depth-1 mechanism executed one candidate action and ranked only the immediate successor. It replaced, rather than supplemented, the baseline continuation. A land play reduced cards in hand without creating an immediate mana-pool gain, allowing pass-priority to win the later lexicographic comparison. Search then predominantly passed. Recorded EXPLORATORY actions were 6,000 pass-priority, 2,000 declare-attackers, three play-land, and three activate actions.

This result establishes that the authorized one-layer mechanism was ineffective. It does not establish that the STANDARD policy is optimal or that every possible exploratory method would fail. Exact candidate score vectors were not persisted, so no numeric evaluator scores are inferred.

## Deck findings

### Strong pilot signals

- Glint-Horn Buccaneer was central to the dominant package and the main productive tutor target.
- Malcolm / Glint-Horn supplied nearly all deterministic Turn-8 access.
- Psychosis Crawler frequently supplied conditional access but no deterministic full-table access; opening copies were often slow or stranded.

### Moderate pilot signals

- Drift of Phantasms and Long-Term Plans were the most productive tutor signals.
- Vedalken Aethermage supplied frequent creature-tutor access.
- Invert // Invent's Invent face was unused by the frozen policy.

### Weak or insufficient pilot signals

Most other singleton differences are too small, confounded, and exposed to multiple-comparison noise to justify adding or cutting a card from this pilot alone.

## Limitations

Opponent interaction, blocking, and opponent wins were not modeled. Unknown Breeches cards were excluded from deterministic resources. The horizon ended after Turn 10 unless a valid earlier terminal state occurred. Associations do not establish causation. Five hundred STANDARD games do not provide stable estimates for every individual singleton or narrow subgroup. The EXPLORATORY result applies only to the authorized depth-1 mechanism.

## Full-study options

### Authorize the original 20,000 / 5,000 study unchanged

Not recommended. Approximately 20,000 STANDARD runs would provide near half-point precision around the observed Turn-8 rate, but 5,000 runs of the current EXPLORATORY mechanism would scale a known ineffective design.

### Require a corrected pilot

Not required for the completed pilot because no technical defect invalidated it. A new pilot would be required after any EXPLORATORY redesign.

### Revise or narrow the study

**Recommended.** Preserve the valid STANDARD pilot. Choose an explicit precision target. Roughly 5,000 STANDARD games would provide about one-percentage-point precision near the observed Turn-8 rate and materially improve combo, mulligan, and card-category estimates. Remove EXPLORATORY from the next study, or redesign it, complete technical validation, and run a new small exploratory pilot before scaling it.

### Stop the study

Not recommended for the STANDARD deck questions.

## Owner decision required

Issue #52 remains open and the full study remains unauthorized. The owner must choose one:

- `AUTHORIZE FULL STUDY`
- `REQUIRE CORRECTED PILOT`
- `REVISE / NARROW STUDY`
- `STOP STUDY`
