# Project mission

Build a reproducible, deck-scoped Magic: The Gathering Commander simulator for the exact Malcolm and Breeches deck in `docs/source/`. The simulator measures legal deterministic table-win access under the fixed project assumptions and compares candidate policies rather than assuming one is correct.

# Current development phase

The current task is Phase A: build a clean rules kernel and representative Oracle-backed production-card slice under `src/mtg_kernel/` and `src/mtg_cards/`.

`legacy/mtg_sim/` is legacy reference code during the transition. It is not an installed package and cannot be imported. New clean-engine packages must not import it, execute it, copy its event-log shortcuts, or treat its tests as proof of Phase A correctness. The legacy package remains present only to preserve repository history and existing checks until its removal is separately approved.

Do not run or resume the older numbered Codex prompt sequence. Use `docs/spec/ENGINE_BUILD_PHASE_A.md` and `prompts/recovery/PHASE_A_ENGINE_BUILD.md`.

# Source precedence

When sources conflict, use this order. Fail closed and report a conflict instead of silently guessing.

1. `docs/source/MagicCompRules_2026-06-19.txt`
2. Frozen Oracle snapshot committed under `docs/source/oracle/`
3. `docs/spec/LEAGUE_MULLIGAN.md` as the only league rules override
4. `docs/spec/identity/IDENTITY_MODEL_V2.0.0.md`, bound by its approval record and lock manifest
5. `docs/spec/ENGINE_BUILD_PHASE_A.md`
6. Fixed baseline and exploratory specifications under `docs/spec/`
7. Architecture decision records under `docs/architecture/decisions/`
8. Implementation

The identity specification is frozen. Do not edit it in an implementation pull request. A binding correction requires a new version, a new digest, and owner approval.

# Non-negotiable correctness rules

- Never claim a test, simulation, audit, or command ran unless it completed on the reported repository state and its output was saved when an artifact is required.
- Never fabricate pass counts, game results, decoded replays, audit rates, or performance percentages.
- Unsupported card behavior, rules ambiguity, invalid state, or unimplemented legal action is a hard failure. Do not approximate silently.
- This is a complete engine for this exact deck and modeled environment, not a general-purpose implementation of every Magic card.
- Every deck card must have an explicit coverage status and reviewed behavior. There is no generic silent no-op fallback.
- All game actions must pass the same legality validator used by standard play, exploratory search, and replay validation.
- Policies receive an observation that excludes hidden library order, hidden internal identities, and future random outcomes. Only the rules executor may access hidden state.
- Future information, favorable hidden assumptions, selective replay, and unreported post-result optimization are prohibited.
- Opponent choices required by a card are resolved by the documented opponent-choice policy, never by a favorable choice for this deck.
- A line is not deterministic unless the engine executes the finite sequence legally to table elimination or another defined terminal state.
- Do not run a production pilot until the clean engine, complete deck migration, competency tests, and pilot authorization are all satisfied on the same commit.
- Do not run the full 25,000-game study without explicit owner authorization after review of the pilot.

# Clean-engine architecture boundary

- `src/mtg_kernel/` contains card-agnostic state and rules services.
- `src/mtg_cards/` contains structured Oracle-backed card specifications and compositions of universal primitives.
- Neither package may import from `mtg_sim`, reach into legacy state, or delegate execution to the legacy `GameExecutor`.
- Zones store object identifiers, not card-name strings.
- Rules-object identity changes exactly as required by frozen `IDENTITY_MODEL_V2.0.0`.
- A card name may select data for display or lookup, but kernel control flow may not branch on a card name.
- Event logs are evidence produced by state transitions; they are never substitutes for stack objects, triggers, choices, targets, or zone movement.
- Replay reconstructs and re-executes through the same production rules path. It may not trust a transcript's claimed terminal result.
- New packages must remain independently importable and testable while the legacy package is quarantined.

# Engineering workflow

- Read the relevant specifications and traceability material before editing.
- Use focused branches and pull requests. Do not implement the entire simulator in one undifferentiated change.
- Prefer tests first for rules-critical behavior.
- Preserve deterministic seeds, named RNG streams, state hashes, and complete causal event logs.
- Keep raw run artifacts immutable. Corrections create a new run ID; they do not overwrite failed or quarantined runs.
- Any repeated audit error requires a regression test, an engine correction, and a complete affected-run rerun.
- Optimize only after correctness gates pass and a profiler identifies a bottleneck.
- Do not delete, rename, or close legacy files, branches, or pull requests without explicit owner approval.

# Required repository checks

These checks apply during preparation and remain part of the implementation gate:

- Install: `uv sync --frozen --all-extras`
- Frozen identity integrity: `uv run python scripts/check_identity_lock.py`
- Clean-package boundary: `uv run python scripts/check_clean_engine_boundary.py`
- Format check: `uv run ruff format --check .`
- Lint: `uv run ruff check .`
- Type check: `uv run mypy src`
- Unit and integration tests: `uv run pytest -q`
- Manifest integrity: `uv run python scripts/check_manifest.py`
- Source validation: `uv run mtg-sources validate-sources`

Phase A must add a dedicated clean-engine acceptance command and immutable result artifact before it may merge. Existing legacy commands are not Phase A evidence.

# Evidence required in every implementation response

Report:

1. Files changed
2. Commands actually run
3. Exact pass/fail results
4. Remaining unsupported or uncertain behavior
5. Artifact paths
6. Whether the repository was clean and which commit was tested
7. Whether any evidence came from the legacy package

# Review guidelines

Treat the following as high-severity defects:

- A policy can read the actual future library order or stable identities for hidden objects.
- A simulation continues after a terminal win or loss.
- State-based actions are checked during the resolution of a spell or ability rather than at the rules-required time.
- Mana, targets, timing, commander tax, priority, stack use, or zone movement can be bypassed.
- A retired object reference silently follows a physical card or successor object without an authorized reference mode.
- One tutor is counted as simultaneous access to several targets.
- Copied spells are counted as cast.
- Opponent-dependent Treasure production is hard-coded.
- A failed or partial run is summarized as complete.
- Discovery and validation seeds are mixed after policy results are observed.
- Clean-engine code imports or delegates to `mtg_sim`.
- A real card is implemented from abbreviated remembered text instead of the frozen Oracle record.
