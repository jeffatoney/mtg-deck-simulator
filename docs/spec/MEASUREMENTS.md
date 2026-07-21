# Measurements

Collect exact counts, denominators, paired differences, and uncertainty intervals. Preserve raw game-level fields so every summary can be recomputed.

## Opening hands and mulligans

- Card appearance in initial and replacement hands
- Keep rate when each card is present
- Outcome lift when present, both raw and conditioned on mana/action features
- Original seven kept, first replacement seven kept, six kept, five kept, four kept
- Outcome and first-attempt turn by keep level
- Refill cards and whether they changed combo or mana access

## Mana versus action density

Classify failures at each checkpoint as mana shortage, color shortage, tapped-land delay, protection-mana shortage, action-density shortage, tutor-without-cast-mana, interaction-only hand, sequencing failure, or other documented cause. Preserve all applicable labels and a primary cause chosen by a frozen classifier.

## Combo availability

For each defined package and exploratory line, record by turn:

- Pieces assembled
- Legally executable with sufficient mana
- Available with usable protection
- Attempted
- Resolved
- Full table kill
- Conditional kill or takeover only

At minimum track Malcolm plus Glint-Horn, Dualcaster plus Twinflame, Dualcaster plus Electroduplicate, Niv-Mizzet plus Curiosity, Lightning-Rig Crew plus Crab Umbra plus Malcolm, Psychosis Crawler draw-based lines, tutor-created access, hybrid lines, and recovery lines.

## Timing and protection

- Earliest legal attempt turn
- Actual first-attempt turn
- Attempt package
- Immediate versus delayed attempt
- Zero, one, or multiple usable protection effects
- Protection in hand but not payable
- Protection that does not answer the modeled category

## Second lines

In the baseline, measure independent second-line availability. Report true post-disruption recovery only in a separately configured and reported perturbation analysis.

## Stranded or irrelevant cards

For every card: draw frequency, cast frequency, average turns held, stranded frequency, stranded reason, cast-without-outcome-improvement frequency, and contribution to win, protection, recovery, mana, cards, or takeover.

## Policy and exploratory comparisons

- Checkpoint table-win access at Turns 5, 6, 8, and 10
- Paired result difference by seed
- First decision divergence
- Information visible at divergence
- Win-turn change
- Narrow-condition flag
- Search branches, nodes, and depth
- Future-information and post-result-optimization rejection counts

## Reproducibility metadata

Every run manifest must include git commit, dirty-tree flag, Python version, dependency-lock hash, rules-source hash, Oracle-snapshot hash, decklist hash, config hash, seed-list hash, command line, start/end timestamps, worker count, and test results for the same commit.
