# Exploratory search limits

- Maximum 12 candidate branches per major decision
- Maximum three player turns of look-ahead
- Maximum 5,000 evaluated nodes per exploratory game
- Maximum eight candidate actions retained after each search layer
- Unknown future draws are evaluated through sampled expected value from the policy-visible belief state, never from the actual future order assigned to the game seed
- Recommended initial common-random-number sample cap: eight samples per unknown-draw evaluation, with every sampled successor counting against the 5,000-node limit

## Lexicographic ranking

1. Immediate legal table win
2. Protected table win
3. Earliest expected win turn
4. Independent second-line availability
5. Cards accessed
6. Net usable mana
7. Resilient board position

## Required search logging

For every major exploratory decision, record candidate count, branches searched, nodes evaluated, depth reached, pruning reason, belief-state sample seeds, selected action, and whether the actual hidden future order was inaccessible to the policy.
