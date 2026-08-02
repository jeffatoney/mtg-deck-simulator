# Candidate policies

Policy choices must be composable, versioned configuration rather than scattered hard-coded conditionals. Candidate bundles and evaluator snapshots must be frozen before their results are inspected.

Compare at minimum:

- Aggressive versus selective mulligans at 7, 6, 5, and 4
- Malcolm-first versus tutor-first development
- Malcolm-first versus mana-rock-first sequencing
- Casting Breeches early versus only when he can trigger immediately
- Glint-Horn-first versus Dualcaster-first tutor priorities
- Earliest legal combo versus lowest-mana combo
- Protected combo versus earliest unprotected combo
- Immediate combo attempt versus waiting one turn for protection
- Cantrip-first versus ramp-first sequencing
- Preserving Muddle the Mixture as interaction versus transmuting it
- Holding Glint-Horn Buccaneer versus casting it for value
- Human-designed contextual evaluator versus any separately validated learned evaluator snapshot

Additional legal policies may be proposed, but they must be documented and hashed before evaluation.

## Strategic evaluator boundary

The rules engine enumerates and applies legal choices. Policy configuration decides strategic preferences. Tutor selection occurs during resolution. Fact or Fiction split and pile selection use an injected evaluator. Copy-target choices use the same observation-only boundary.

Every evaluator snapshot must declare:

- Evaluator ID and SHA-256
- Algorithm version
- Land-development assumptions
- Exact effect-to-feature classifications
- Combo-package definitions
- Feature weights or learned coefficients
- Tie-breaking rules
- Unknown-feature handling
- Dualcaster-loop handling

Missing required classifications fail closed. Intentional neutral values must be explicit.

## Adjustable evaluator buttons

An evaluator snapshot is a selectable policy input. Changing a land threshold, protection preference, combo-completion value, opponent severity, or learned snapshot selects a different content-addressed configuration; it does not alter Magic rules or silently rewrite an active run.

## Discovery-only learning

The frozen learning plan uses exactly 4,800 discovery comparisons and 1,000 untouched validation comparisons:

- 300 precommitted discovery seeds × 16 comparisons each;
- the first 200 discovery seeds (3,200 comparisons) for initial fitting and candidate mining;
- the remaining 100 discovery seeds (1,600 comparisons) for candidate confirmation;
- feature identities, transformations, support thresholds, and the accepted/rejected candidate list freeze before refitting on all 4,800 discovery comparisons;
- 200 untouched validation seeds × 5 comparisons each for one final promotion decision.

Each pairwise label must hold constant the initial state, hidden-information boundary, future RNG streams, continuation policy, and Turn-10-or-terminal evaluation horizon. The frozen lexicographic label order is full table kill, legal table-win access, protected access, independent second line, earlier terminal turn, then earlier legal-attempt turn. Exact ties are excluded from accuracy and reported separately.

Learning requirements:

- Discovery and validation IDs and seeds do not overlap.
- Validation results do not influence candidate generation, feature selection, thresholds, or fitting.
- Raw records preserve policy-visible card identities and zones, legal action signatures, ordered prior actions, mana/land context, combo/protection access, and both counterfactual outcomes. Internal object IDs, physical card-instance IDs, hidden library order, and future events are prohibited.
- Generic feature pairs, card pairs, and action sequences may be ranked as `REVIEW_REQUIRED` hypotheses only. The miner makes no uncorrected significance claim and may not add a weight, combo package, or policy rule.
- Candidate ranking requires at least 50 comparisons across at least 20 distinct discovery seeds, at least 34 mining examples, at least 16 confirmation examples, the same effect direction in mining and confirmation, and a maximum report of 20 candidates.
- A learned snapshot may be promoted only if it beats the human-designed evaluator by at least 3.0 percentage points on paired validation decisions, the seed-clustered 95% confidence lower bound is above zero, and direct outcome guardrails show no regression.
- The learned snapshot is immutable and content-addressed. Only `FROZEN_VALIDATED` snapshots may become policy buttons.
- Canonical and exploratory runs never update the selected snapshot.

## Recommended screening design

Do not run the full factorial combination of every axis. Create balanced anchor policies and one-axis or fractional-factorial variants. Record the exact policy matrix and selected evaluator snapshot before the discovery run. Use paired seeds and report learning examples, policy-evaluation runs, validation runs, canonical games, and exploratory games separately.
