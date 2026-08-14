# Phase C Post-Pilot Audit

## Verdict

**PILOT AUDIT PASS**

Run `31752039318` is a technically valid 500 STANDARD / 200 paired EXPLORATORY pilot.

- Implementation: `150671a8e7a78e5fa14b6b3aca2308f6af647df3`
- Implementation tree: `37cf737691d516a0b7316270364724f91dd28856`
- Approval commit: `6c5db50a06fe3c54557458bc8a45dce7c2abcd04`
- Activation commit: `319fd3f273899e8808888240ff881e97ae3976c1`
- Locked config SHA-256: `c609c9a39e3187297fd83d275db4c94b5b5601a72918bd822a330bff1bfdfaca`
- Workflow SHA-256: `e9525ce182a1914b53e25d771f8fa097cb657c23f863f0c437aaac2a337914fd`
- Approval-record SHA-256: `dee9a764076199afa028968b2ab7ee67d7d0be397ccb4af36d346738e46b3972`
- Aggregate SHA-256: `6bd1ea110dd030075180565b6c1e5856b8cec986970614c5545b8494cd899732`
- Full study authorized: **false**

These figures measure combo assembly speed against opponents who take no actions. They are not win rates and do not predict performance against interactive opponents.

## Technical / execution findings

The live repository and workflow run still bind to the reviewed implementation and tree. The activation branch is two commits ahead of the implementation: one owner-approval commit and one pilot-activation commit. The activation diff contains only the approval record and activated pilot config. Issue #52 remains open, and full-study execution remains locked.

Artifact inventory:

- 10 STANDARD shard artifacts, indexes 0 through 9 exactly once;
- 10 EXPLORATORY shard artifacts, indexes 0 through 9 exactly once;
- 1 aggregate artifact;
- all from run `31752039318` and head `150671a8e7a78e5fa14b6b3aca2308f6af647df3`;
- no missing, duplicate, wrong-run, wrong-head, wrong-mode, or wrong-shard artifacts;
- all 21 downloaded ZIP SHA-256 values matched GitHub's artifact digests.

Record and replay integrity:

| Mode | Attempted | Valid | Replay pass | Replay fail |
|---|---:|---:|---:|---:|
| STANDARD | 500 | 500 | 500 | 0 |
| EXPLORATORY | 200 | 200 | 200 | 0 |
| Total | 700 | 700 | 700 | 0 |

Every game had a technical record, measurement record, replay transcript, final-state hash, and matching fresh-process replay hash. All implementation, activation, config, workflow, approval, policy, evaluator, seed, and manifest bindings reproduced. There were 698 controlled Turn-10 stops and two valid earlier STANDARD terminal states. No game silently failed or disappeared.

The frozen paired STANDARD indexes were exactly:

`1-20, 51-70, 101-120, 151-170, 201-220, 251-270, 301-320, 351-370, 401-420, 451-470`

Every EXPLORATORY record matched one and only one paired STANDARD environment seed, game index, and pair ID, while retaining a separate search seed. Pairing verdict: **PASS**.

The authorized execution used `policy_actions=True` and `validate_fresh_replay=True`. Clean-engine-only execution, the legacy import guard, no future information, no post-result optimization, frozen policy bindings, EXPLORATORY depth 1, no opponent interaction, no blocking, no modeled opponent wins, and exclusion of unknown Breeches cards were all confirmed.

A preliminary apparent discrepancy between summary and manifest measurement digests was resolved as intentional canonicalization: one hashes semantic records with integer checkpoint keys; the other hashes JSON-normalized records with string keys. Both reproduced exactly. This is not a defect.

## Measurement findings

The persisted evidence matches the frozen definition:

- checkpoints T5, T6, T8, and T10;
- T8 primary;
- objective `MAXIMIZE_LEGAL_DETERMINISTIC_TABLE_WIN_ACCESS`;
- primary paired outcome `LEGAL_DETERMINISTIC_TABLE_WIN_ACCESS_BY_TURN_8`;
- exact two-sided McNemar;
- 10,000 deterministic paired-bootstrap resamples;
- 95% percentile interval;
- secondary no-imputation, both-access-only turn shift;
- no numeric action threshold precommitted.

Independent reconstruction from all 20 immutable shards exactly matched the persisted STANDARD summary, EXPLORATORY summary, paired Turn-8 analysis, paired timing artifact, and aggregate SHA-256 `6bd1ea110dd030075180565b6c1e5856b8cec986970614c5545b8494cd899732`. Aggregation verdict: **PASS**.

Package-level legal access and deterministic full-table access are not identical. Psychosis Crawler is conditional; one Lightning-Rig line and one T10 Malcolm/Glint-Horn line were also conditional. The results summary keeps these measures separate.

## STANDARD policy findings

Deterministic full-table access:

| Checkpoint | Count | Rate |
|---|---:|---:|
| T5 | 19 / 500 | 3.8% |
| T6 | 37 / 500 | 7.4% |
| T8 | 82 / 500 | 16.4% |
| T10 | 113 / 500 | 22.6% |

Earliest access occurred on T3: 1, T4: 8, T5: 10, T6: 18, T7: 20, T8: 25, T9: 13, and T10: 18. Another 387 games had no access through T10.

Actual first attempts occurred in 125 games: T4: 3, T5: 13, T6: 20, T7: 25, T8: 26, T9: 19, and T10: 19. An attempted conditional package does not necessarily satisfy deterministic full-table access.

Mulligans:

- 379 kept the first 7;
- 121 used the free second 7, and 96 kept it;
- 10 kept at 6;
- 9 kept at 5;
- 6 kept at 4.

At seven cards, the frozen policy kept every 2-, 3-, and 4-land hand and rejected every other land count. Two-, three-, and four-land keeps had broadly similar descriptive outcomes. Hands with two tutor-capable cards were uncommon but had stronger observed access; this category includes Invert // Invent even though the policy never used Invent.

Action density was the larger constraint:

- T8 failures: 348 action-density primary, 70 mana primary;
- T10 failures: 302 action-density primary, 85 mana primary.

Malcolm/Glint-Horn was the dominant deterministic package: 77 of 82 T8 contributions and 107 T10 contributions before the one T10 overlap with Twinflame. Psychosis Crawler became legally executable in 98 games by T10 but never supplied deterministic full-table access. Dualcaster/Twinflame reached 5 legal games by T10; Electroduplicate reached 2; Lightning-Rig reached one conditional legal line; Niv-Mizzet/Curiosity reached none.

Earlier Malcolm casts correlated with stronger access and directly supported the main package. Breeches was cast often but had no deterministic combo-contribution tags under the unknown-card restriction.

Tutor use was most often:

- Long-Term Plans: Glint-Horn 48, Curiosity 16;
- Step Through: Dualcaster 83, Niv-Mizzet 16;
- Vedalken Aethermage: Dualcaster 48, Niv-Mizzet 24;
- Muddle the Mixture: Twinflame 41;
- Drift of Phantasms: Glint-Horn 40;
- Dizzy Spell: Crab Umbra 21.

All 109 Invert // Invent casts used Invert; Invent was never used.

## EXPLORATORY policy findings

EXPLORATORY recorded 0/200 deterministic full-table access and no actual attempts through T10.

Paired T8 cells:

- BOTH_ACCESS: 0;
- STANDARD_ONLY_ACCESS: 37;
- EXPLORATORY_ONLY_ACCESS: 0;
- NEITHER_ACCESS: 163;
- difference: -18.5 percentage points;
- exact McNemar p-value: `1.4551915228366852e-11`;
- paired-bootstrap 95% interval: -24 to -13 points.

All 200 first divergences occurred on Turn 1 precombat main:

- STANDARD selected `PLAY_LAND`;
- EXPLORATORY selected `PASS_PRIORITY`.

The same first divergence occurred in all 37 STANDARD-only T8 pairs.

The authorized depth-1 adapter executed one action and evaluated only the immediate successor. It did not continue the frozen baseline. A land play reduced hand size while its future developmental value was not represented by an immediate mana-pool gain, allowing pass-priority to win a later lexicographic tiebreak. Repeated search then predominantly passed.

Observed EXPLORATORY actions were 6,000 `PASS_PRIORITY`, 2,000 `DECLARE_ATTACKERS`, three `PLAY_LAND`, and three `ACTIVATE`, across 8,006 decisions and 29,105 nodes. Every game recorded depth 1.

This supports causes B and C:

- the one-layer mechanism selected systematically poor continuations;
- search replaced rather than supplemented the baseline continuation.

It does not support a replay, pairing, legality, measurement, terminal-tracking, or aggregation defect. Exact candidate score vectors were not persisted, so no numeric score is invented. The result shows that this specific exploratory mechanism was ineffective, not that all exploratory search is ineffective.

## Deck findings

**Strong pilot signals**

- Glint-Horn Buccaneer was central to the dominant package and the main productive tutor target.
- Psychosis Crawler frequently offered conditional legal access but not deterministic full-table access; opening copies were often slow or stranded.
- Malcolm/Glint-Horn supplied nearly all T8 deterministic access.

**Moderate pilot signals**

- Drift of Phantasms and Long-Term Plans had the clearest useful tutor associations.
- Vedalken Aethermage was frequently used, primarily for Dualcaster or Niv-Mizzet.
- The frozen policy never used the Invent face of Invert // Invent.

**Weak or insufficient pilot signals**

Most other individual singleton associations are too small, confounded, and exposed to multiple-comparison noise to justify additions or cuts.

## Study-design limitations

Opponent interaction, blocking, and opponent wins were not modeled. Breeches unknown cards were excluded. Games ended after Turn 10 unless a valid earlier terminal state occurred. Pilot associations do not establish causation. Five hundred STANDARD games are not enough for stable card-by-card optimization. The EXPLORATORY result applies only to the authorized depth-1 mechanism.

## Post-pilot decision implications

### AUTHORIZE FULL STUDY

Not recommended unchanged. Scaling 5,000 games of the current EXPLORATORY mechanism would scale a known ineffective design. Twenty thousand STANDARD games are justified only if approximately half-point precision or rare subgroup estimates are required.

### REQUIRE CORRECTED PILOT

Not required for the completed pilot. No technical defect invalidated it. A new pilot is needed only after redesigning EXPLORATORY.

### REVISE / NARROW STUDY

**Recommended.** Preserve the valid STANDARD evidence. Set an explicit precision target, likely about 5,000 STANDARD games for the core questions. Remove EXPLORATORY or redesign, technically validate, and test it in a new small pilot before scale-up.

### STOP STUDY

Not recommended for the STANDARD questions.

## Owner decision required

The full study remains unauthorized. Issue #52 must remain open until the owner chooses:

- `AUTHORIZE FULL STUDY`
- `REQUIRE CORRECTED PILOT`
- `REVISE / NARROW STUDY`
- `STOP STUDY`
