Build the pilot runner, reports, audit sampling, and run-manifest system. Perform a dry run only; do not execute randomized games.

The dry run must print and save:

- Exact source/config/commit hashes
- 500 base standard seed IDs and the frozen 300/200 discovery-validation split
- Candidate policy matrix and planned policy-evaluation counts
- Finalist advancement rule
- Planned 500 canonical standard games
- Planned 200 exploratory games paired with Standard Games 1–200
- Audit selection rules and supplemental audit-only procedure
- Search limits and expected maximum node count
- Output paths and shard plan
- Blocking open decisions

The runner must refuse to execute if the tree is dirty, sources changed, any competency test failed on the same commit, card coverage is incomplete, or open decisions marked blocking remain unresolved.

Return the dry-run manifest and a go/no-go recommendation. Do not run the pilot.
