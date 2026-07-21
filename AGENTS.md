# Project mission

Build a reproducible, deck-scoped Magic: The Gathering Commander simulator for the exact Malcolm and Breeches deck in `docs/source/`. The simulator measures legal deterministic table-win access under the fixed goldfish assumptions in `docs/spec/PROJECT_BRIEF.md` and compares candidate policies rather than assuming one is correct.

# Source precedence

When sources conflict, use this order and stop for an explicit decision rather than silently guessing:

1. `docs/source/MagicCompRules_2026-06-19.txt`
2. Frozen Oracle snapshot committed under `docs/source/oracle/`
3. `docs/spec/LEAGUE_MULLIGAN.md` as the only league rules override
4. Fixed baseline and exploratory specifications under `docs/spec/`
5. Architecture decision records under `docs/architecture/decisions/`
6. Implementation

# Non-negotiable correctness rules

- Never claim a test, simulation, audit, or command ran unless it actually completed in the current repository state and its output was saved.
- Never fabricate pass counts, game results, decoded replays, audit rates, or performance percentages.
- Unsupported card behavior, rules ambiguity, invalid state, or unimplemented legal action is a hard failure. Do not approximate silently.
- This is a complete engine for this exact deck and modeled environment, not a general-purpose implementation of all Magic cards.
- Every deck card must have an explicit coverage status and reviewed behavior. There is no generic silent no-op fallback.
- All game actions must pass the same legality validator used by standard play, exploratory search, and replay validation.
- Policies receive an `Observation` that excludes the hidden library order and future random outcomes. Only the game executor may access hidden state.
- Future information, favorable hidden assumptions, selective replay, and unreported post-result optimization are prohibited.
- Opponent choices required by a card are resolved by the documented opponent-choice policy, never by a favorable choice for this deck.
- A line is not deterministic unless the engine executes the finite sequence legally to table elimination or another defined terminal state.
- Do not run the pilot until all competency tests pass on the same commit.
- Do not run the full 25,000-game study without explicit user authorization after the pilot report.

# Engineering workflow

- Read the relevant specifications and traceability matrix before editing.
- Use focused branches or pull requests. Do not implement the whole simulator in one task.
- Prefer tests first for rules-critical changes.
- Preserve deterministic seeds and complete event logs.
- Keep raw run artifacts immutable. Corrections create a new run ID; they do not overwrite failed or quarantined runs.
- Any repeated audit error requires a regression test, an engine correction, and a complete pilot rerun.
- Optimize only after correctness gates pass and a profiler identifies a bottleneck.

# Required local commands

These commands are the intended interface. Update this section if the repository uses different commands.

- Install: `uv sync --all-extras`
- Format check: `uv run ruff format --check .`
- Lint: `uv run ruff check .`
- Type check: `uv run mypy src`
- Unit and integration tests: `uv run pytest -q`
- Rules competency report: `uv run mtg-sim verify-rules --output artifacts/rules/`
- Source validation: `uv run mtg-sim validate-sources`
- Pilot dry run: `uv run mtg-sim pilot --config configs/pilot.toml --dry-run`
- Pilot: `uv run mtg-sim pilot --config configs/pilot.toml`

# Evidence required in every implementation response

Report:

1. Files changed
2. Commands actually run
3. Exact pass/fail results
4. Remaining unsupported or uncertain behavior
5. Artifact paths
6. Whether the repository was clean and which commit was tested

# Review guidelines

Treat the following as high-severity defects:

- A policy can read the actual future library order.
- A simulation continues after a terminal win or loss.
- State-based actions are checked during object resolution.
- Mana, targets, timing, commander tax, or zone movement can be bypassed.
- One tutor is counted as simultaneous access to several targets.
- Copied spells are counted as cast.
- Opponent-dependent Treasure production is hard-coded.
- A failed or partial run is summarized as complete.
- Discovery and validation seeds are mixed after policy results are observed.
