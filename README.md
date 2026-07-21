# Malcolm and Breeches Simulator — Codex Handoff Pack

This package transfers the simulator requirements into repository files that Codex can read repeatedly. The repository, not a chat transcript, should become the source of truth.

## Recommended order

1. Copy this package into the root of the connected GitHub repository.
2. Review `docs/spec/OPEN_DECISIONS.md`; resolve the primary baseline settings before any pilot run.
3. Review and edit `AGENTS.md` only if repository commands differ.
4. In Codex, run the prompts in `prompts/` in numerical order. Use one branch or pull request per prompt.
5. Do not skip the source-freeze, architecture, competency-test, or pilot-dry-run gates.
6. Do not run the full 25,000-game study until the user explicitly authorizes it after reviewing the pilot.

## What is already included

- Exact 98-card library and two commanders
- June 19, 2026 Comprehensive Rules source supplied by the user
- League mulligan override
- Fixed baseline conditions
- Exploratory-search specification
- Required rules tests
- Policy candidates
- Pilot protocol and audit requirements
- Proposed architecture
- Copy/paste Codex prompts

## What Codex must create

Codex should create the Python package, tests, card-data snapshot, CI, simulation runners, audit/replay tools, and reports. It must not claim empirical results unless the corresponding command completed and raw artifacts were written.

## Counts terminology

Keep these quantities separate:

- **Base seeds/scenarios:** random environments used for paired comparisons.
- **Policy-evaluation runs:** repeated executions of policies on the same base seeds.
- **Canonical standard games:** the 500 designated pilot outcomes after a preliminary policy is locked.
- **Exploratory games:** the 200 bounded-search outcomes paired with canonical Standard Games 1–200.

The policy-discovery process will produce more than 500 executions. Report that number explicitly; never label all policy evaluations as only “500 games.”
