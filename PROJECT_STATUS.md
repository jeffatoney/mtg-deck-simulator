# MTG Deck Simulator Project Status

> **Last synchronized:** 2026-08-07 05:26 UTC
> **Repository:** `jeffatoney/mtg-deck-simulator`
> **Phase B merge:** PR #37 merged into `main` at `4d1df5a68744864906e337d8ded17d12d7724d37`
> **Active Phase C branch:** `phase-c/pilot-authorization`
> **Active Phase C draft PR:** #49
> **Certified Phase C implementation:** `ec7ce0ad841917fcc8d687db831a8d6db6755535`
> **Certified implementation tree:** `8849363ff5b7e3b678e65b151c4c00b6bef532cb`
> **Green certification-current head before this dashboard-only update:** `a83ae55712b7704959824f1a3bf0f76850c5393e`
> **Final technical/certification CI:** run 775 / `31149836580` — **SUCCESS**
> **Phase C execution status:** **LOCKED — OWNER DECISION REQUIRED**

Phase C technical implementation is complete and durably certified. The pilot and full study remain locked. No pilot or full-study game has been executed. `execution_allowed` remains `false`; the machine owner approval record remains pending. The next action is the explicit owner decision under issue #51.

## Overview

| Phase | Status | Evidence or control |
|---|---|---|
| Phase A foundation | **Current and durably certified** | 33/33 verifier tests; durable certification-current PASS |
| Phase B deck/policy foundation | **Current and durably certified** | 190/190 mapped tests; 0 unsupported capabilities; 0 strategic-model blockers; 12/12 transcripts; durable certification-current PASS |
| Phase C production runner | **Technically complete** | Real Turn-10 policy/replay path, combat, exploratory expansion, combo detection, replay/rollback, and immutable artifacts pass executable gates |
| Phase C authorization controls | **Technically complete and locked** | Owner binds reviewed implementation commit/tree; later activation must be a governance-only descendant with an allowlisted diff |
| Phase C 500/200 pilot | **Not authorized** | `execution_allowed: false`; owner approval pending; 0 pilot games run |
| Full 20,000/5,000 study | **Not authorized** | Separate post-pilot owner decision under #52; 0 full-study games run |

## Certified implementation identity

- Implementation commit: `ec7ce0ad841917fcc8d687db831a8d6db6755535`.
- Implementation tree: `8849363ff5b7e3b678e65b151c4c00b6bef532cb`.
- The certification-current head `a83ae55712b7704959824f1a3bf0f76850c5393e` is three descendants after the implementation commit and changes only the Phase A and Phase B durable certification records.
- No engine, policy, workflow, pilot-config, or approval-config code changed after the certified implementation commit.

## Final CI evidence

Final technical/certification run: **775 / `31149836580` — SUCCESS**.

- Frozen identity lock: PASS.
- Phase A authority: PASS.
- Phase B evaluator/learning boundary: PASS.
- Clean-engine boundary: PASS; no forbidden findings.
- Legacy `mtg_sim`: not importable.
- Ruff formatting: PASS; 206 files formatted.
- Ruff lint: PASS.
- Strict mypy: PASS; 75 source files.
- Exact-deck Turn-10 production policy/replay smoke: PASS.
  - controlled turns completed: 10;
  - command count: 458;
  - fresh-process replay equality: true;
  - actual first combo attempt: Turn 10;
  - attempted package: `malcolm_glint_horn`;
  - errors: none.
- Full repository pytest: **311 passed**.
- Manifest integrity: PASS; 34 frozen files / 18 required paths.
- Phase A verifier: **33 pass, 0 fail, 0 skip, 0 xfail**.
- Phase B verifier: **190 pass, 0 fail, 0 skip, 0 xfail**.
  - unsupported capability count: 0;
  - strategic-model blocker count: 0;
  - golden transcripts: PASS, 12 approved;
  - pilot lock: PASS.
- Phase C no-game dry run: `READY_FOR_OWNER_REVIEW`.
  - `readiness_blockers: []`;
  - `game_results_created: 0`;
  - `execution_allowed: false`;
  - full-study execution allowed: false.
- Durable Phase A certification-current: PASS.
- Durable Phase B certification-current: PASS.

## Executable Phase C readiness evidence

The four former hand-maintained blocker labels are now derived from executable checks and all pass:

1. Controlled Turn-10 driver: PASS with exact fresh-process replay.
2. Legal combat path: PASS through shared `DECLARE_ATTACKERS` broker/executor path, including Malcolm commander damage.
3. Exploratory production expansion: PASS at one audited production decision layer; 6 branches/nodes in the dry-run smoke, first standard/exploratory divergence recorded, exact replay digest recorded.
4. Combo-access detection: PASS for all six frozen deterministic packages.

Technical issue #50 and child issues #54–#63 and #67–#70 are completed and closed.

## Frozen pilot definition

- Exact 98-card library plus Malcolm and Breeches in the command zone.
- Three opponents.
- Controlled player draws on Turn 1.
- League mulligan: 7, free 7, 6, 5, 4; never below four; refill to seven.
- Simulate through the end of controlled Turn 10.
- Primary checkpoint: Turn 8; additional checkpoints: Turns 5, 6, and 10.
- Opponent interaction: none modeled.
- Blocking: none modeled.
- Opponent wins: none modeled.
- Malcolm may connect and Glint-Horn may attack when legal.
- Unknown Breeches cards do not become deterministic resources.
- Objective: maximize legal deterministic table-win access.
- Standard pilot: 500 games, 10 shards of 50.
- Exploratory pilot: 200 games, 10 shards of 20, reported separately.
- Standard policy: `anchor_balanced` with exact evaluator and learning-plan bindings.
- Future information: prohibited.
- Post-result optimization/policy mutation: prohibited.
- Exploratory production decision-layer depth: exactly 1; existing hard search caps remain upper bounds and actual depth/nodes are reported honestly.

Binding files:

- `docs/spec/phase-c/PHASE_C_PILOT_CONFIG.json`
- `docs/spec/phase-c/PHASE_C_PILOT_AUTHORIZATION.md`
- `docs/spec/phase-c/PHASE_C_PILOT_APPROVAL.json`
- `.github/workflows/phase-c-pilot.yml`

## Locked owner-review values

- Pilot config SHA-256: `9911d4cd328d0970a316fbdf164124f87fc8e593a27240f165d17eaf6d55d0e2`.
- Pilot workflow SHA-256: `1b94e613e870904f139d4dc2f9a4641e097f791bb6cdff7c28acec0679819680`.
- Pending approval-record SHA-256: `8bbd61f813e1fefa4cf60ae96fa1d409dbb612a645d4bca2b970ad661c2e3287`.
- Confirmation token: `AUTHORIZE_PHASE_C_500_STANDARD_200_EXPLORATORY`.
- Standard seed-plan SHA-256: `177086231a5e5e8a489cf1433929a092febc761d2d5865ab3bdd663381a3adff`.
- Exploratory seed-plan SHA-256: `2e7c78fbc9ff6c4d2eb9bbce8da54bf75d2afabd48d6f24f36fbadabe5691f06`.
- Evaluator: `contextual_combo_v1` / `86c5e07daaa86362a38fad7a66d712443e32ba8af743bcaaa15576207264eca2`.
- Learning-plan SHA-256: `4884586c492c62cfd009c0a53c6d4ddd888274771c10efddc2b1853745a685e2`.
- Transcript approval-document SHA-256: `242a43347f3d73405872b43820048497cf06101b4b02a637b009f0143200c53d`.

## Authorization model

The owner approves or holds/rejects the exact certified implementation package under issue #51. Approval does **not** retroactively approve an unknown future code commit. If approved, a later activation commit may change only the allowlisted Phase C pilot config and approval record. The activation workflow proves that the activation commit descends from the reviewed implementation and contains no unexpected code changes before any output path or game result can be created.

Until the owner explicitly approves:

- `execution_allowed` stays `false`;
- approval status stays pending;
- no 500/200 pilot is run;
- no 20,000/5,000 full study is run.

## Remaining work

1. Require this dashboard-only PR head to pass CI without changing the certified implementation surface.
2. Present the complete digest-bound **OWNER DECISION REQUIRED** package under issue #51.
3. Stop for the owner's APPROVE / HOLD / REJECT decision.
4. Only after an explicit APPROVE: create the governance-only activation commit and use the locked manual workflow for the 500/200 pilot.
5. After the pilot is audited, handle the separate full-study decision under issue #52.

## Repository health

| Item | Current state |
|---|---|
| `main` protection | Active `Protect main`; redundant Phase A ruleset disabled |
| Phase B PR | #37 merged |
| Active Phase C PR | #49 draft |
| Recovery PRs | #64, #65, #66 closed as superseded; none merged |
| Phase C runner issue | #50 closed as technically complete |
| Technical child issues | #54–#63 and #67–#70 closed as completed |
| Phase C parent authorization | #48 remains open until the authorized pilot is executed and audited |
| Owner decision | #51 open and next |
| Full-study decision | #52 open and post-pilot only |
| Pilot execution | Locked; 0 games executed |
| Full study | Locked; 0 games executed |
