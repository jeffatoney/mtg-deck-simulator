# Candidate policies

The implementation must represent policy choices as composable configuration, not scattered hard-coded conditionals. Candidate policy bundles must be frozen before their results are inspected.

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

Codex may propose additional legal policies, but it must document them before evaluation.

## Recommended screening design

Do not run the full factorial combination of every axis. Create a balanced, precommitted set of anchor policies and one-axis or fractional-factorial variants. Record the exact policy matrix in `configs/policies.yaml` before the discovery run. Use paired seeds and report actual policy-evaluation counts separately from canonical game counts.
