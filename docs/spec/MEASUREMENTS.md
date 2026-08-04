# Measurements

Collect exact counts, denominators, paired differences, and uncertainty-ready raw records. Every summary must be recomputable from game-level data.

## Opening hands and mulligans

- Card appearance in initial and replacement hands
- Keep rate when each card is present
- Outcome lift when present, both raw and conditioned on mana/action features
- Original seven kept, first replacement seven kept, six kept, five kept, four kept
- Outcome and first-attempt turn by keep level
- Refill cards and whether they changed combo or mana access

## Mana versus action density

Classify failures at each checkpoint as mana shortage, color shortage, tapped-land delay, protection-mana shortage, action-density shortage, tutor-without-cast-mana, interaction-only hand, sequencing failure, or another documented cause. Preserve all applicable labels and a primary cause chosen by a frozen classifier.

## Continuous combo availability

Combo status must be evaluated from Turn 1 through terminal resolution or the end of Turn 10. It must be refreshed before every major policy decision and after every state change that can alter pieces, mana, timing, targets, protection, or terminal access. Turns 5, 6, 8, and 10 are cumulative reporting checkpoints, not the first turns on which combos are checked.

For each defined package and exploratory line, record by turn:

- Pieces assembled
- Sufficient mana
- Legally executable, including timing and targets
- Available with usable protection
- First offered to policy
- Attempted
- Resolved
- Full table kill
- Conditional kill or takeover only
- Unsupported detector or loop-adjudication reason, when applicable

At minimum track Malcolm plus Glint-Horn, Dualcaster plus Twinflame, Dualcaster plus Electroduplicate, Niv-Mizzet plus Curiosity, Lightning-Rig Crew plus Crab Umbra plus Malcolm, Psychosis Crawler draw-based lines, tutor-created access, hybrid lines, and recovery lines.

A Turn 3 or Turn 4 legal line must retain its true earliest turn. If it wins before a later checkpoint, table-win access at Turns 5, 6, 8, and 10 is cumulatively true.

## Timing and protection

- Earliest pieces-assembled turn
- Earliest sufficient-mana turn
- Earliest legal-attempt turn
- Actual first-attempt turn
- Terminal turn
- Attempt package
- Immediate versus delayed attempt
- Zero, one, or multiple usable protection effects
- Protection in hand but not payable
- Protection that does not answer the modeled category

Summaries must include turn distributions for earliest legal attempt, actual first attempt, and terminal result, including Turns 1 through 4 rather than hiding early outcomes inside the Turn 5 checkpoint.

## Strategic-choice evidence

For tutor, pile, and copy-target choices, record:

- Rules-defined choice time
- Legal choice set using opaque handles or legal identities
- Selected choice
- Policy configuration ID
- Evaluator snapshot ID and SHA-256
- Fixed-point diagnostics with no floating-point values in game state
- Whether the decision came from baseline policy, a frozen learned snapshot, or an audit-only witness

## Learning evidence

Learning records are separate from canonical game measurements. Every pairwise example must preserve:

- Example ID, frozen seed, decision index, decision kind, turn, and phase
- Learning-plan ID and SHA-256
- Initial-state, future-RNG, and continuation-policy hashes proving both alternatives differ only in the selected decision
- Policy-visible card identities, zones, and card types; internal object IDs, card-instance IDs, hidden library order, and future event fields are forbidden
- Full legal action signatures, selected alternative signatures, and ordered prior relevant actions
- Mana by symbol, lands in play, land drop remaining, visible combo access, and visible protected access
- Accessible card identities after each alternative
- Generic evaluator feature vectors for each alternative
- The complete frozen `OutcomeVector` for each counterfactual, cumulative Turn 5/6/8/10 access, terminal turn, and earliest legal-attempt turn

Dataset and model evidence must include:

- Exactly 4,800 discovery comparisons (300 seeds × 16) and 1,000 validation comparisons (200 seeds × 5)
- Mining/training partition hash for the first 200 discovery seeds and confirmation-partition hash for the remaining 100
- Discovery, validation, frozen-feature-set, and candidate-report SHA-256 digests
- Parent evaluator identity and SHA-256
- Learned feature schema and fixed-precision weights
- Baseline and learned validation accuracy, paired improvement, tie count, seed-clustered 95% confidence interval, and direct outcome guardrails
- Review-only generic-feature, card-pair, and action-sequence candidates with mining/confirmation support, distinct-seed counts, effect direction, representative example IDs, `REVIEW_REQUIRED` status, and no automatic activation
- Snapshot identity, SHA-256, promotion failures, and final status

No validation example may influence feature generation, candidate selection, thresholds, or fitting. No learning output may alter a discovery run, canonical run, or exploratory run after it begins.

## Second lines

In the baseline, measure independent second-line availability. Report true post-disruption recovery only in a separately configured and reported perturbation analysis.

## Stranded or irrelevant cards

For every card: draw frequency, cast frequency, average turns held, stranded frequency, stranded reason, cast-without-outcome-improvement frequency, and contribution to win, protection, recovery, mana, cards, or takeover.

## Policy and exploratory comparisons

- Cumulative table-win access at Turns 5, 6, 8, and 10
- Paired result difference by seed
- First decision divergence
- Information visible at divergence
- Win-turn change
- Narrow-condition flag
- Search branches, nodes, and depth
- Future-information and post-result-optimization rejection counts

## Reproducibility metadata

Every run manifest must include git commit, dirty-tree flag, Python version, dependency-lock hash, rules-source hash, Oracle-snapshot hash, decklist hash, policy-config hash, evaluator snapshot ID and SHA-256, optional learning-plan SHA-256, seed-list hash, command line, start/end timestamps, worker count, and same-commit test evidence. Aggregation must reject mixed evaluator snapshots or learning plans.
