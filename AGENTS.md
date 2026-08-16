# Project mission

Build a reproducible, deck-scoped Magic: The Gathering Commander simulator for the exact Malcolm and Breeches deck in `docs/source/`. The simulator measures legal deterministic table-win access under the fixed project assumptions and compares candidate policies rather than assuming one is correct.

# Current development phase

The current task is Phase B: migrate the complete exact deck and build the standard-policy, bounded-search, measurement, replay, and manifest framework on the clean Phase A engine.

Work only on `engine/phase-b-full-deck-policy` and existing draft PR #37. Use `docs/spec/ENGINE_BUILD_PHASE_B.md` and `prompts/recovery/PHASE_B_FULL_DECK_POLICY.md`.

Phase A is a standing regression contract. Every pull request and push to `main` reruns its verifier, and changes to the certified content surface require a new CI-produced durable certification candidate before merge.

`legacy/mtg_sim/` and `legacy/tests/` are archival reference only. They are not installed and may not be imported, executed, translated, copied, or used as implementation or acceptance evidence. Preserve them unless the owner separately authorizes deletion.

Do not run or resume the older numbered Codex prompt sequence.

# Source precedence

When sources conflict, use this order. Fail closed and report a conflict instead of silently guessing.

1. `docs/source/MagicCompRules_2026-06-19.txt`
2. Frozen Oracle snapshot committed under `docs/source/oracle/`
3. `docs/spec/LEAGUE_MULLIGAN.md` as the only league rules override
4. `docs/spec/identity/IDENTITY_MODEL_V2.0.0.md`, bound by its approval record and lock manifest
5. `docs/spec/ENGINE_BUILD_PHASE_B.md`
6. Fixed baseline, policy, exploratory, measurement, open-decision, rules-acceptance, and pilot specifications under `docs/spec/`
7. Architecture decision records under `docs/architecture/decisions/`
8. Implementation

The identity specification is frozen. Do not edit it in an implementation pull request. A binding correction requires a new version, a new digest, and owner approval.

# Non-negotiable correctness rules

- Never claim a test, simulation, audit, or command ran unless it completed on the reported repository state and its output was saved when an artifact is required.
- Never fabricate pass counts, game results, decoded replays, audit rates, or performance percentages.
- Unsupported card behavior, rules ambiguity, invalid state, or unimplemented legal action is a hard failure. Do not approximate silently.
- This is a complete engine for this exact deck and modeled environment, not a general-purpose implementation of every Magic card.
- Every deck card must have an explicit reviewed `IMPLEMENTED` coverage status. Missing, partial, blocked, or fallback behavior prevents Phase B acceptance.
- All game actions must pass the same legality generator and executor used by standard play, exploratory search, competency scenarios, and replay validation.
- Policies and search receive the same observation excluding hidden library order, hidden internal identities, and future random outcomes. Only the rules executor may access hidden state.
- Candidate policy configurations are hypotheses to compare. Do not turn owner-supplied tendencies into assumed strategic truth.
- Future information, favorable hidden assumptions, selective replay, and unreported post-result optimization are prohibited.
- Opponent choices required by a card are resolved by the documented opponent-choice policy, never by a favorable choice for this deck.
- A line is not deterministic unless the engine executes the finite sequence legally to table elimination or another defined terminal state.
- Standard and exploratory results, seeds, manifests, and measurements remain structurally separate.
- Do not run policy discovery, the 500/200 pilot, or the full 25,000-game study during Phase B.
- Do not run a production pilot until the clean engine, complete deck migration, competency tests, Phase B verifier, durable Phase A recertification, and explicit pilot authorization are all satisfied on the same commit.
- Do not run the full study without explicit owner authorization after review of the pilot.

# Clean-engine architecture boundary

- `src/mtg_kernel/` contains card-agnostic state and rules services.
- `src/mtg_cards/` contains structured Oracle-backed card specifications and compositions of universal primitives.
- Phase B policy, search, measurement, and manifest packages must be separately installed, typed, testable, and assigned to the documented boundary tier.
- No installed package may import from `mtg_sim`, reach into legacy state, or delegate execution to the legacy `GameExecutor`.
- Zones store object identifiers, not card-name strings.
- Rules-object identity changes exactly as required by frozen `IDENTITY_MODEL_V2.0.0`.
- A card name may select data for display or lookup, but kernel control flow may not branch on a card name.
- Event logs are evidence produced by state transitions; they are never substitutes for stack objects, triggers, choices, targets, or zone movement.
- Replay reconstructs and re-executes through the same production rules path. It may not trust a transcript's claimed terminal result.
- Search must consume observations and legal actions rather than full game state.

# Engineering workflow

- Read the relevant specifications and traceability material before editing.
- Phase B is one branch and PR with internal B1–B7 gates; keep changes reviewable and milestone-oriented.
- Prefer tests first for rules-critical behavior.
- Preserve deterministic seeds, named RNG streams, state hashes, and complete causal event logs.
- Keep raw run artifacts immutable. Corrections create a new run ID; they do not overwrite failed or quarantined runs.
- Any repeated audit error requires a regression test, an engine correction, and a complete affected-run rerun.
- Optimize only after correctness gates pass and a profiler identifies a bottleneck.
- Do not delete, rename, or close legacy files, branches, or pull requests without explicit owner approval.
- Stop only for a genuine owner decision that cannot be resolved by the authority chain or reliability requirements. Publish safe blocker evidence and an `OWNER DECISION REQUIRED` PR comment before pausing.

# Repository evidence preservation

- A repository report or artifact does not exist as a durable deliverable until its actual bytes are committed, indexed in `docs/audit/EVIDENCE_INDEX.json` when applicable, and verified at an exact Git SHA.
- Do not describe a local file, generated string, workflow workspace file, or expiring GitHub Actions artifact as saved, committed, published, durable, or complete.
- Before using those completion words, identify the exact Git SHA, verify the path exists at that SHA, verify the bytes or content-addressed blob from GitHub, and verify the indexed SHA-256 digest.
- Preserve load-bearing raw evidence in a static repository location before an ephemeral Actions artifact expires.
- Every file under a tracked evidence root must be listed in the evidence index and pass `scripts/check_repository_evidence.py`.
- No committed tool may generate or overwrite a certification-covered gate, regression test, assertion, authority map, test map, certification record, or expected value from the same observed run output that the generated content is supposed to check.
- If a covered expected value changes, use a human-authored diff that records what changed, why, and the independent authority for the new expectation.
- Remove PR-scoped diagnostic and source-mutation scaffolding before proposing the branch for certification.
- If a historical positive regression conflicts with repaired behavior and methodology is unresolved, keep the conflict visible. Do not rewrite the regression from the new observation merely to make the branch pass.
- Follow `docs/audit/REPOSITORY_EVIDENCE_POLICY.md` for the complete preservation and reporting contract.

# Required repository checks

These checks apply throughout Phase B:

- Install: `uv sync --frozen --all-extras`
- Frozen identity integrity: `uv run python scripts/check_identity_lock.py`
- Repository evidence integrity: `uv run python scripts/check_repository_evidence.py`
- Phase A authority and durable certification gates
- Clean installed-package boundary: `uv run python scripts/check_clean_engine_boundary.py`
- Format check: `uv run ruff format --check .`
- Lint: `uv run ruff check .`
- Type check: `uv run mypy src`
- Unit and integration tests: `uv run pytest -q`
- Manifest integrity: `uv run python scripts/check_manifest.py`
- Source validation: `uv run mtg-sources validate-sources`
- Standing Phase A verifier: `uv run mtg-engine verify-phase-a`
- Phase B verifier when added: `uv run mtg-engine verify-phase-b`

Phase B must add its own authority checker, complete-deck coverage gate, competency gate, verification command, immutable exact-head result artifact, and renewed durable Phase A certification before merge.

# Evidence required in every implementation response

Report:

1. Files changed
2. Commands actually run
3. Exact pass/fail results
4. Deck and Oracle coverage counts
5. Competency, policy, search, measurement, replay, and manifest counts
6. Remaining unsupported or uncertain behavior
7. Artifact paths and hashes
8. Whether the repository was clean and which commit was tested
9. Whether any evidence came from the legacy package
10. Standing Phase A verification and durable-certification status
11. Pilot and full-study lock status

# Review guidelines

Treat the following as high-severity defects:

- A policy or search can read the actual future library order, future event stream, or stable identities for hidden objects.
- Standard and exploratory paths use different legality rules or executors.
- A simulation continues after a terminal win or loss.
- State-based actions are checked during the resolution of a spell or ability rather than at the rules-required time.
- Mana, targets, timing, commander tax, priority, stack use, additional costs, or zone movement can be bypassed.
- A retired object reference silently follows a physical card or successor object without an authorized reference mode.
- One tutor is counted as simultaneous access to several targets.
- Copied spells are counted as cast.
- Opponent-dependent Treasure or mana production is hard-coded rather than derived from modeled opponents.
- Opponent choices are favorable or unspecified.
- A card coverage entry is missing, partial, fallback, or unsupported while verification continues.
- A failed or partial run is summarized as complete.
- Discovery and validation seeds are mixed after policy results are observed.
- Search sees the real hidden future or selectively replays failed seeds.
- Aggregation accepts mixed commits/configs/sources, duplicate seeds, or gaps.
- A covered Phase A change merges with stale durable certification.
- Clean-engine or support code imports, loads, executes, or delegates to `mtg_sim`.
- A real card is implemented from abbreviated remembered text instead of the frozen Oracle record.
