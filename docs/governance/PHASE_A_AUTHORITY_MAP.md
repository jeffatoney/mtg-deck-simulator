# Phase A Authority Map

**Status:** Binding repository-governance rule for Phase A after this pull request merges.

## Purpose

This map prevents superseded implementation assumptions, tests, prompts, reports, and workflows from becoming accidental requirements or evidence for the clean rules engine.

A file may be useful historical context without being authoritative. Inclusion in Git history or `HANDOFF_MANIFEST.json` proves preservation only; it does not make the file current, binding, approved for execution, or valid as Phase A evidence.

## Classification order

When two materials conflict, use the highest applicable classification below and fail closed rather than combining incompatible instructions.

### 1. `ACTIVE_BINDING`

These materials determine Phase A behavior or project inputs:

- `docs/source/MagicCompRules_2026-06-19.txt`
- `docs/source/decklist.txt`
- `docs/source/commanders.txt`
- the frozen Oracle records under `docs/source/oracle/`
- `docs/spec/LEAGUE_MULLIGAN.md`, only as the documented league override
- `docs/spec/identity/IDENTITY_MODEL_V2.0.0.md`
- `docs/spec/identity/IDENTITY_MODEL_V2.0.0_APPROVAL_RECORD.json`
- `docs/spec/identity/IDENTITY_MODEL_V2.0.0_LOCK_MANIFEST.txt`
- `docs/spec/ENGINE_BUILD_PHASE_A.md`
- `prompts/recovery/PHASE_A_ENGINE_BUILD.md`, as the active implementation procedure

The Comprehensive Rules govern Magic behavior. Frozen Oracle records govern real card text. The league mulligan file governs only the stated league override. The frozen identity model governs object identity, references, visibility, continuity scope, replay hashing, and related implementation invariants.

### 2. `CONDITIONAL_PROJECT_INPUT`

Baseline, exploratory, measurement, opponent-policy, and pilot specifications under `docs/spec/` and `configs/` apply only when the current Phase A contract explicitly invokes them. They cannot override `ACTIVE_BINDING` materials and do not authorize a pilot during Phase A.

### 3. `SOURCE_VALIDATION_ONLY`

Legacy source loaders, inventories, and source-validation tests may continue to verify that frozen inputs exist and match their hashes. Their engine models, object representations, card handlers, and game results are not authoritative.

### 4. `ARCHIVAL_REFERENCE_ONLY`

The following may be read for history, prior scenarios, and known failure modes, but must be revalidated before any idea is implemented:

- pre-V2 architecture documents and ADRs
- the numbered prompts under `prompts/00_...` through `prompts/12_...`
- legacy traceability and card-coverage claims
- old smoke, rules-competency, pilot, and audit reports
- closed or unmerged recovery branches and pull requests
- legacy tests whose production path imports or executes `mtg_sim`

No statement such as “normative,” “accepted,” “complete,” “covered,” or “validated” inside an archival file overrides this classification.

### 5. `PROHIBITED_AS_PHASE_A_EVIDENCE`

None of the following may satisfy a Phase A acceptance claim:

- execution through `src/mtg_sim/` or its `GameExecutor`
- legacy replay or state hashes
- legacy adapter or coverage counts
- legacy pilot or smoke outcomes
- event-log strings used instead of rules objects and state transitions
- a test that bypasses the clean production executor
- a result copied from an old artifact, branch, pull request, or chat transcript

Every Phase A result must label its evidence path as `CLEAN_ENGINE_PRODUCTION_PATH`, `SOURCE_VALIDATION_ONLY`, or `LEGACY_REFERENCE_PATH`. Only `CLEAN_ENGINE_PRODUCTION_PATH` may satisfy a Phase A implementation requirement.

## Active pilot prohibition

During Phases A and B:

- `.github/workflows/pilot-simulation.yml` must not exist.
- The former workflow is preserved only at `docs/workflows/pilot-simulation.phase-c.yml.template`.
- The template is archival and must be rewritten against the clean engine, independently reviewed, and explicitly authorized before activation in Phase C.

## Change control

Changing an `ACTIVE_BINDING` source, promoting an archival item to binding status, reactivating a pilot workflow, or allowing legacy execution as acceptance evidence requires an explicit reviewed repository change. Changes to the frozen identity model additionally require a new version, digest, and owner approval.
