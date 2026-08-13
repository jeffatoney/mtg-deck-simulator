# Phase C Pre-Pilot Independent Audit

## Verdict

**READY FOR OWNER PILOT DECISION — NOT AUTHORIZED**

This audit concerns exact `main` commit `150671a8e7a78e5fa14b6b3aca2308f6af647df3` and tree `37cf737691d516a0b7316270364724f91dd28856` only. It does not authorize or execute the pilot or full study.

## Audited repository state

- Repository: `jeffatoney/mtg-deck-simulator`
- Audited main: `150671a8e7a78e5fa14b6b3aca2308f6af647df3`
- Audited tree: `37cf737691d516a0b7316270364724f91dd28856`
- PR #98: merged at `2026-08-13T06:38:16Z`; merge commit `150671a8e7a78e5fa14b6b3aca2308f6af647df3`
- Exact-main CI: run `31674580342` / #1049 / SUCCESS / exact audited SHA
- Full exact-main pytest: 404 passed
- Handoff branch: `handoff/current` at `1016866d44ec7bf124fb780b99cb8e51ac170fb4`
- Handoff subject: exact audited commit/tree; tracked worktree dirty = false; PR #98 absent from `github.open_pull_requests`

## Durable certifications

### Phase A
- Schema: `phase-a-certification-v3`
- Status/environment: PASS / GITHUB_ACTIONS
- Certified content commit: `2bb0791cbda30651d688546e8d3a084ae6487eda`
- Certified repository tree: `28fa269da9b93a0d31c4d05b55fa8ed44776673e`
- Certification run: `31385148178`
- Covered-content digest: `sha256:a1e441d0293c1231cead8e194f55e4f1a396409c1f1c56c065006ace939f9e31`
- Current reconstructed covered-content digest: `sha256:a1e441d0293c1231cead8e194f55e4f1a396409c1f1c56c065006ace939f9e31`
- Covered-path digest values inspected: 26; malformed: 0
- Current checker: PASS; pilot lock: PASS; legacy evidence prohibited and unused.

### Phase B
- Schema: `phase-b-certification-v1`
- Status/environment: PASS / GITHUB_ACTIONS
- Certified content commit: `563e0becc0870efa539726ef9ab4884370cc48bc`
- Certified repository tree: `bc165b11b0856f27d44a0f0c4556fbdfbe3e55c8`
- Certification run: `31653244841`
- Covered-content digest: `sha256:4ae2c3b7897f88388fb3ae77b49b8529ecbeda9f23082cbf56726a57899532cb`
- Current reconstructed covered-content digest: `sha256:4ae2c3b7897f88388fb3ae77b49b8529ecbeda9f23082cbf56726a57899532cb`
- Covered-path digest values inspected: 45; malformed: 0
- Current checker: PASS; pilot lock: PASS; legacy evidence prohibited and unused.
- `NO_OPPONENT_POLICY_GUARDRAIL.json` is covered.
- `PHASE_C_PILOT_CONFIG.json` is outside Phase B `COVERED_PATHS`.
- Phase B `COVERED_PATHS` and the activation allowlist are disjoint.
- CI-produced Phase B candidate from run `31653244841` is byte-for-byte identical to the promoted durable record: 6,563 bytes, SHA-256 `1e9c58c95d4df081d6c528d4a1c9ca9b5699ed3c3e77396df195dcd4236ad8b2`, Git blob `db1f2ad6baa64ae1cf7d22e6ca392f6339025d1e`.

## Frozen Phase C identity

The audited config remains frozen at SHA-256 `c609c9a39e3187297fd83d275db4c94b5b5601a72918bd822a330bff1bfdfaca`.

- Deck: exact 98-card library from `docs/source/decklist.txt`; Malcolm, Keen-Eyed Navigator and Breeches, Brazen Plunderer in the command zone; 100 physical cards.
- Game model: four players, three opponents, controlled player draws on Turn 1, ends after controlled Turn 10; opponent interaction, blocking, and opponent wins are not modeled; Malcolm may connect and Glint-Horn may attack when legal; unknown Breeches cards are excluded from deterministic resources.
- Mulligan: `[7, 7, 6, 5, 4]`; kept hand refills to seven; rejected hands return and shuffle; no candidate below four.
- Measurement: checkpoints T5/T6/T8/T10; T8 primary; objective `MAXIMIZE_LEGAL_DETERMINISTIC_TABLE_WIN_ACCESS`; required outputs unchanged.
- Pilot: 500 STANDARD, 200 paired EXPLORATORY, 10+10 shards, exploratory production decision-layer depth 1.
- Information boundaries: no future information, no post-result optimization or policy mutation, bounded rules-validated exploratory search.
- Pairing: 200 pairs, `FIRST_20_OF_EACH_STANDARD_SHARD`, T8 paired checkpoint, exact two-sided McNemar, 95% deterministic paired-bootstrap percentile CI, 10,000 resamples, required reporting sentence unchanged.
- Namespaces/policy/evaluator/learning bindings remain unchanged and exact.

## Diagnostic run 31679471162

Workflow: `Phase C Pre-Pilot Diagnostic — 700 Seeds`, event `workflow_dispatch`, head `150671a8e7a78e5fa14b6b3aca2308f6af647df3`, tree `37cf737691d516a0b7316270364724f91dd28856`, conclusion SUCCESS.

Artifact inventory: exactly 21 GitHub Actions artifacts:
- 10 STANDARD shard artifacts, shard indexes 0-9 exactly once;
- 10 EXPLORATORY shard artifacts, shard indexes 0-9 exactly once;
- 1 aggregate summary artifact;
- every artifact belongs to run `31679471162` and head `150671a8e7a78e5fa14b6b3aca2308f6af647df3`;
- no artifact from another run or SHA was included.

Execution result:
- STANDARD: 500 attempted / 500 passed / 0 failed
- EXPLORATORY: 200 attempted / 200 passed / 0 failed
- Total: 700 attempted / 700 passed / 0 failed
- Observed fresh replay matches: 700 / 700
- Distinct technical errors: 0
- Pilot measurement artifacts: 0
- Authorized execution: false
- Pilot result: false

### Execution path evidence

Exact source:
- Path: `src/mtg_runs/phase_c_diagnostic.py`
- Git blob: `4a5d7f61906a88176dc2b75b76ee356b038bdc4b`
- Bytes: 19,460
- Independently computed SHA-256: `5004625e532f39b774a37c8f613a75bbb4eb592fe05711289b494f0098f8635a`
- Containing commit/tree: `150671a8e7a78e5fa14b6b3aca2308f6af647df3` / `37cf737691d516a0b7316270364724f91dd28856`

The exact diagnostic call explicitly passes `policy_actions=True` and `validate_fresh_replay=True`. This matters because `run_phase_c_game_execution` defaults `policy_actions` to false. The workflow checks out the exact audited implementation and invokes `python -m mtg_runs.phase_c_diagnostic`.

Evidence classification:
- `production_equivalent_execution`: `ASSERTED_LITERAL_NOT_PRIMARY_EVIDENCE`
- `fresh_replay_required`: `ASSERTED_CONFIGURATION_NOT_PRIMARY_EVIDENCE`
- `fresh_replay_pass_count`: `DERIVED_OBSERVED_EVIDENCE`

A PASS diagnostic record requires matching original and fresh-replay final-state hashes. The aggregate reconstructs the records and derives the replay-pass count rather than unconditionally assigning 700.

### Environment assignments

The diagnostic used the frozen seed-plan and shard assignment implementation. STANDARD indexes are 1-500 exactly once. EXPLORATORY indexes are 1-200 exactly once with 200 unique search seeds and pair IDs. Paired STANDARD indexes are 1-20, 51-70, 101-120, 151-170, 201-220, 251-270, 301-320, 351-370, 401-420, and 451-470, exactly matching `FIRST_20_OF_EACH_STANDARD_SHARD`. No mode mixing, missing assignments, or duplicates were observed. Workflow `fail-fast` is false.

## Fail-closed falsification audit

The exact-main CI's permanent test suite executed the repository's non-persistent mutation tests and all 404 tests passed. The audit mapped 44 non-vacuous violating mutations to their responsible tests/gates. These cover activation/coverage disjointness, frozen config semantics, unknown keys, activation allowlist, code-change rejection, certification currentness, artifact/replay/provenance boundaries, and the diagnostic execution contract.

Most importantly, permanent diagnostic tests fail if:
- `policy_actions=True` is changed to false;
- the explicit `policy_actions` override is removed;
- `validate_fresh_replay=True` is changed to false;
- diagnostic workflow `fail-fast: false` is changed to true.

No material uncovered fail-closed governance gap was found. Two non-material coverage observations are recorded in the machine-readable record: representative rather than bespoke negative tests are used for generic provenance fields, and the activation non-authorization equality guard is source-contract protected while individual frozen fields are independently mutation-tested by the config loader.

## Exact-main repository gates

All required exact-main gates are PASS. The machine-readable audit maps every gate to command/checker, commit/tree, run `31674580342`, job `94366258407`, and CI step. This includes identity lock, Phase A authority, clean-engine/support boundary, legacy import prohibition, Ruff format/lint, strict mypy, Turn-10 production/fresh-replay smoke, Phase A/Phase B verifiers, Phase B authority/evaluator/learning/golden/full-deck checks, manifest integrity, full pytest, Phase C no-game dry run, and durable certification-current checks.

## Historical 64-seed holdout

**HISTORICAL TECHNICAL CONFORMANCE EVIDENCE — NOT CURRENT-SHA ACCEPTANCE EVIDENCE**

- Implementation: `b04b2ec7dc622a7afe4a6432f5f466926333c87f`
- Tree: `893f1fa541ab00e3e35fc7fcf70f9f9a6cb2d7ab`
- Run: `31518902524`
- Result: 64/64 technical PASS, 0 failures, 0 distinct errors, fresh replay required/matched
- Precommitted namespace: `phase-c-prepilot-holdout-v1`
- Seed domain: disjoint from the frozen pilot namespaces
- Current-SHA acceptance evidence: false
- Current classification: `STALE_FOR_CURRENT_IMPLEMENTATION`

Repeating those 64 seeds on current main would be **OPTIONAL ADDITIONAL DISJOINT REGRESSION**, not a frozen prerequisite.

## Authorization state

Pilot:
- `execution_allowed = false`
- `LOCKED_PENDING_OWNER_APPROVAL`
- approval record `PENDING_OWNER_APPROVAL`
- owner/timestamp/statement and implementation/tree/config/workflow approval bindings remain unset.

Full study:
- `execution_allowed = false`
- `LOCKED_PENDING_POST_PILOT_REVIEW`
- separate later authorization remains required.

## Interpretive limit

The 700 diagnostic is technical execution, legality, completion, replay, provenance, and artifact-boundary acceptance evidence. It is not deck-performance evidence. It does not establish 700 wins, a 100% win rate, STANDARD or EXPLORATORY superiority, the Turn-8 pilot result, earliest-access performance, a policy-performance conclusion, or performance against interactive opponents, blockers, or modeled opponent wins.

## Final audit conclusion

All required audit conditions are clean for exact `150671a8e7a78e5fa14b6b3aca2308f6af647df3` / `37cf737691d516a0b7316270364724f91dd28856`. The pilot and full study remain locked.

**READY FOR OWNER PILOT DECISION — NOT AUTHORIZED**
