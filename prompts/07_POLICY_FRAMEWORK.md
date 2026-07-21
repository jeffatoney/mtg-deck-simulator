Implement the composable candidate-policy framework without running the pilot.

Requirements:

- Represent every axis in `docs/spec/POLICY_CANDIDATES.md` as explicit configuration.
- Create a frozen, balanced screening matrix of anchor and variant policies; do not use the full factorial unless justified.
- Define hand features, keep decisions at 7/6/5/4, development ordering, commander timing, Breeches timing, tutor priorities, combo choice, cantrip/ramp sequencing, protection delay, Muddle use, and Glint-Horn value timing.
- Policies may inspect only Observation, never hidden state.
- Create a precommitted 500-seed list and a 300/200 discovery-validation split before any policy result exists.
- Implement paired-comparison records and first-divergence logging.
- Add tests proving no validation seed influences candidate creation or discovery advancement.

Run only deterministic policy unit tests and hand-authored scenarios. Do not run policy discovery or canonical pilot games yet.
