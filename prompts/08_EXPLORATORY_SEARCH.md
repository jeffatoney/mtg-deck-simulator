Implement the bounded exploratory search specified in `docs/spec/EXPLORATORY_BRANCH.md` and `docs/spec/EXPLORATORY_SEARCH_LIMITS.md`. Do not run the pilot.

Requirements:

- Generate only actions accepted by the shared legality validator.
- Enforce 12 branches per major decision, three player turns of look-ahead, 5,000 nodes per game, beam width eight, and the frozen lexicographic ranking.
- Unknown draws must be sampled from the policy-visible remaining-card belief state using separate common-random-number streams. The actual hidden future library order must be structurally unavailable to search code.
- Log branches, nodes, depth, pruning, rollout sample seeds, first standard/exploratory divergence, and all safeguards.
- Distinguish first-policy result, bounded-search result, and later manual replay.
- Reject unspecified opponent resources, favorable choices, illegal shortcuts, future information, and selective replay.

Add adversarial tests that intentionally attempt to leak the real library order or replay only failed seeds. The tests must fail the prohibited behavior.
