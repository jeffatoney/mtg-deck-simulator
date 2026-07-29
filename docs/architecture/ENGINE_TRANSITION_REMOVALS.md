# Engine Transition Removal Plan

**Status:** `PENDING_OWNER_APPROVAL`

This file separates preparation changes from destructive cleanup. Nothing listed here is authorized for deletion or closure merely because it appears in this plan.

## A. Immediate cleanup proposed before the engine branch starts

### A1. Close stale draft PR #31

**Target:** `Phase A setup: freeze clean-kernel recovery gates` (`#31`)

**Reason:** It was created before `IDENTITY_MODEL_V2.0.0` was frozen on `main`, contains an older independently frozen acceptance specification, and adds a large 49-file control package. Merging it now would create competing authorities and reintroduce the control-plane expansion the V2 review rejected.

**Proposed action:** Close without merging. Retain its discussion and commits as historical reference. Do not copy its frozen acceptance file or its candidate-owned referee framework into the new engine branch.

**Owner approval required:** Yes.

### A2. Retire the old numbered-prompt instruction

**Target:** The prior `README.md` direction to execute prompts in numerical order.

**Reason:** It points new work back toward the legacy sequence rather than the frozen V2 engine build.

**Proposed action:** Replace the instruction with the current Phase A start order. This is already prepared on `agent/prepare-engine-build`; it does not delete repository history.

**Owner approval required:** No separate destructive approval; the change remains reviewable in the preparation pull request.

### A3. Preserve legacy code under quarantine

**Target:** `src/mtg_sim/` and its current tests, pilot scaffold, adapters, and reports.

**Reason:** Immediate deletion would remove useful historical evidence before clean replacements exist and could break current CI.

**Proposed action:** Do not delete now. Enforce a one-way boundary: new packages may not import or delegate to it.

**Owner approval required:** No deletion is proposed at this stage.

## B. Cleanup proposed only after Phase A passes

The following are candidates for removal or relocation only after the clean Phase A engine passes and each dependency is inventoried:

- legacy rules-execution modules under `src/mtg_sim/`;
- legacy `GameExecutor` and replay shortcuts;
- card adapters that duplicate migrated `mtg_cards` specifications;
- legacy rules-competency tests replaced by production-path tests;
- obsolete engine-specific prompts and setup guides;
- workflows that test only the superseded engine;
- pilot commands or configurations that bypass the clean readiness gate.

**Owner approval required:** Yes, based on an exact file list and dependency report.

## C. Cleanup proposed only after Phase B completes

After all 98 library cards and both commanders run through the clean engine, consider removing:

- remaining compatibility wrappers around `mtg_sim`;
- legacy coverage registries replaced by clean card-capability manifests;
- legacy policy and pilot integration code replaced by clean-engine equivalents;
- obsolete smoke artifacts and reports that are not required for audit history.

**Owner approval required:** Yes, based on an exact file list and proof that no current command, workflow, or artifact reader depends on them.

## D. Never remove as transition cleanup

The following remain retained, versioned project evidence:

- `docs/source/MagicCompRules_2026-06-19.txt`;
- the exact deck and commander source files;
- the frozen Oracle snapshot and source hashes;
- `docs/spec/LEAGUE_MULLIGAN.md`;
- the frozen V2 identity document, approval record, and lock manifest;
- fixed baseline and exploratory specifications;
- immutable raw run and audit artifacts required to understand historical results;
- merged commit and pull-request history.

## Approval record

```yaml
owner_decisions:
  close_pr_31:
    status: PENDING
    approved_by: null
    approved_at: null

  delete_legacy_before_phase_a:
    status: REJECTED_BY_PLAN
    reason: quarantine is safer until clean replacements exist

  later_exact_file_removal:
    status: PENDING_FUTURE_INVENTORY
```
