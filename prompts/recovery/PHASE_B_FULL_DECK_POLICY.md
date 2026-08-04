# Recovery prompt — Phase B complete deck and policy framework

Execute `docs/spec/ENGINE_BUILD_PHASE_B.md` exactly on the existing branch `engine/phase-b-full-deck-policy` and existing draft PR #37.

## Read order

1. `AGENTS.md`
2. `docs/source/MagicCompRules_2026-06-19.txt`
3. `docs/source/oracle/snapshot_v1.json`
4. `docs/spec/LEAGUE_MULLIGAN.md`
5. frozen identity V2.0.0 document, approval record, and lock manifest
6. `docs/spec/ENGINE_BUILD_PHASE_B.md`
7. `PROJECT_BRIEF.md`, `BASELINE_BLOCKING_ASSUMPTIONS.md`, `POLICY_CANDIDATES.md`, `EXPLORATORY_BRANCH.md`, `EXPLORATORY_SEARCH_LIMITS.md`, `MEASUREMENTS.md`, `OPEN_DECISIONS.md`, `RULES_ACCEPTANCE.md`, and `PILOT_PROTOCOL.md`
8. ADRs 0006–0014
9. Phase A implementation and acceptance tests

## Execution rules

- Keep all work in PR #37. Do not create a competing branch or pull request.
- Do not import, execute, translate, or use `legacy/mtg_sim` or `legacy/tests` as implementation evidence.
- Do not edit frozen identity V2.0.0.
- Card behavior is keyed by immutable Oracle identity and composed from universal primitives. Kernel control flow may not branch on card names.
- Implement the complete exact deck and modeled environment, not general Magic.
- Treat every unsupported required capability as a hard failure.
- Use tests first for rules-critical behavior.
- Standard policy, exploratory search, replay, and competency scenarios use one legal-action generator and executor.
- Policies/search receive only restricted observations and legal actions; actual future library order is unavailable.
- Candidate policies are hypotheses to compare. Do not encode the owner's guesses as strategic truth.
- Keep standard and exploratory results structurally separate.
- Do not run policy discovery, the 500/200 pilot, or the 20,000/5,000 study.
- Run and record every repository, Phase A, Phase B, coverage, competency, replay, search, and manifest gate.
- Renew durable Phase A certification through the CI-produced candidate process whenever covered content changes.
- Continue through B1–B7 until complete or a genuine owner decision is required.

## Genuine owner-decision standard

Stop only when a material choice cannot be resolved by the Comprehensive Rules, frozen Oracle text, league rule, frozen identity model, fixed project assumptions, resolved open decisions, accepted reliability defaults, or the user's standing instruction to compare policies objectively.

Before stopping:

- preserve safe blocker evidence;
- commit and push it to PR #37;
- post a PR comment headed `OWNER DECISION REQUIRED`;
- explain the exact alternatives and how each changes the experiment.

Ordinary implementation choices, rules-required translations, fail-closed reliability choices, and defect corrections are not owner decisions.

## Completion response

Report exact tested commit, clean-tree status, files changed, commands actually run, full pass/fail counts, coverage count, competency count, Phase A certification lineage, result artifacts and hashes, unsupported capabilities, legacy-evidence status, and pilot-lock status. Do not self-approve Phase B; leave final GO/NO-GO for independent review.
