# MTG Deck Simulator Project Status

> **Last synchronized:** 2026-08-07 16:00 UTC
> **Repository:** `jeffatoney/mtg-deck-simulator`
> **Phase B merge:** PR #37 merged into `main` at `4d1df5a68744864906e337d8ded17d12d7724d37`
> **Active Phase C branch:** `phase-c/pilot-authorization`
> **Active Phase C draft PR:** #49
> **Reviewed Phase C technical implementation:** `7b37e9e2308141160a79e5f6d3d77fbd4ee88db0`
> **Reviewed implementation tree:** `ba09ab45add3df323317a46750e9b28b31ab2ec8`
> **Green certification-current head before this dashboard-only update:** `1e9365158cd6be03c7a9aa356bb056a79484157f`
> **Certification-current exact-head CI:** run 788 / `31194785666` — **SUCCESS**
> **Phase C execution status:** **LOCKED — OWNER DECISION REQUIRED**

Phase C technical implementation, paired-study redesign, and durable certification are complete. The pilot and full study remain locked. No authorized 500/200 pilot result and no full-study result has been produced. `execution_allowed` remains `false`; the machine owner approval record remains pending. The next action after final dashboard-only exact-head CI is the replacement digest-bound owner decision package under issue #51.

## Overview

| Phase | Status | Evidence or control |
|---|---|---|
| Phase A foundation | **Current and durably certified** | 33/33 verifier tests; durable certification-current PASS |
| Phase B deck/policy foundation | **Current and durably certified** | 190/190 verifier tests; 0 unsupported capabilities; 0 strategic-model blockers; 12/12 transcripts; durable certification-current PASS |
| Phase C production runner | **Technically complete** | Exact-deck Turn-10 execution/replay, combat, strategic choices, exploratory expansion, combo detection, replay/rollback, immutable artifacts, and paired analysis gates pass |
| Phase C paired redesign | **Complete** | 200 exploratory environments are a frozen subset of the 500 standard environments with separate exploratory search RNG and paired aggregate validation |
| Phase C authorization controls | **Technically complete and locked** | Owner binds reviewed implementation commit/tree and frozen digests; later activation must be a governance-only descendant with an allowlisted diff |
| Phase C 500/200 pilot | **Not authorized** | `execution_allowed: false`; owner approval pending; 0 authorized pilot results |
| Full 20,000/5,000 study | **Not authorized** | Separate post-pilot owner decision under #52; 0 full-study results |

## Reviewed implementation and certification identity

- Reviewed technical implementation commit: `7b37e9e2308141160a79e5f6d3d77fbd4ee88db0`.
- Reviewed implementation tree: `ba09ab45add3df323317a46750e9b28b31ab2ec8`.
- Technical/candidate CI: run 787 / `31194210410`.
  - Every technical gate, full test suite, Phase A verifier/candidate, Phase B verifier/candidate, and the no-game Phase C dry run passed.
  - The run failed only at the intentionally stale durable Phase B certification gate after covered Phase C files changed.
  - The exact CI-produced Phase B candidate from run 787 was committed unmodified.
- Phase B certification renewal commit / certification-current descendant: `1e9365158cd6be03c7a9aa356bb056a79484157f`.
- Certification-current exact-head CI: run 788 / `31194785666` — **SUCCESS**.
- No technical implementation, policy, pilot configuration, workflow, seed assignment, or analysis contract changed in the certification-only descendant.

## Final certification-current CI evidence

Run **788 / `31194785666` — SUCCESS** on exact head `1e9365158cd6be03c7a9aa356bb056a79484157f`.

- Frozen identity lock: PASS.
- Phase A authority: PASS.
- Phase B evaluator/learning boundary: PASS.
- Clean-engine boundary: PASS; no forbidden findings.
- Legacy `mtg_sim`: not importable.
- Ruff formatting: PASS; **209 files already formatted**.
- Ruff lint: PASS.
- Strict mypy: PASS; **77 source files**.
- Exact-deck Turn-10 production policy/fresh-replay smoke: PASS.
  - controlled turns completed: 10;
  - command count: 458;
  - combo records: 24;
  - fresh-process replay equality: true;
  - actual first combo attempt: Turn 10;
  - attempted package: `malcolm_glint_horn`;
  - errors: none.
- Full repository pytest: **318 passed**.
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
  - full-study execution allowed: false;
  - paired environment smoke: PASS;
  - exploratory production decision-layer depth: exactly 1.
- Durable Phase A certification-current: PASS.
- Durable Phase B certification-current: PASS.

## Executable Phase C readiness evidence

All formerly hand-maintained readiness blockers are now derived from executable checks and pass:

1. Controlled Turn-10 driver: PASS with exact fresh-process replay.
2. Legal combat path: PASS through the shared `DECLARE_ATTACKERS` broker/executor path, including Malcolm commander damage.
3. Exploratory production expansion: PASS at exactly one audited production decision layer; the smoke records deterministic branches/nodes and a real standard/exploratory decision divergence.
4. Combo-access detection: PASS for all six frozen deterministic packages.
5. Paired environment design: PASS; STANDARD and EXPLORATORY paired runs begin from the same environment seed and initial environment-state hash while exploratory search alone consumes the separate search seed.
6. Deterministic `ORDER_LIBRARY_BOTTOM`: PASS through the public-candidate strategic-choice/replay boundary.

Technical issue #50 and its focused children are complete. Study-design issue #76 and runtime issue #78 were closed as completed after exact-head certification-current evidence supported their acceptance criteria.

## Frozen paired pilot definition

- Exact 98-card library plus Malcolm and Breeches in the command zone.
- Three opponents.
- Controlled player draws on Turn 1.
- League mulligan: 7, free 7, 6, 5, 4; never below four; refill a kept sub-seven hand to seven.
- Simulate through the end of controlled Turn 10.
- Opponent interaction: none modeled.
- Blocking: none modeled.
- Opponent wins: none modeled.
- Malcolm may connect and Glint-Horn may attack when legal.
- Unknown Breeches cards do not become deterministic resources.
- Objective: maximize legal deterministic table-win access.
- Standard pilot: **500 games**, 10 shards of 50, from the frozen standard environment namespace.
- Exploratory pilot: **200 games**, 10 shards of 20.
- The 200 exploratory environments are not an independent environment sample: they reuse exactly the first 20 environments of each 50-game standard shard, for 200 paired STANDARD/EXPLORATORY comparisons.
- Exploratory search randomness uses a separate frozen search-seed namespace and may not perturb environment RNG.
- Standard policy: `anchor_balanced` with exact evaluator and learning-plan bindings.
- Future information: prohibited.
- Post-result optimization/policy mutation: prohibited.
- Exploratory production decision-layer depth: exactly 1; actual branches, nodes, and depth are reported.

### Primary paired outcome

The primary exploratory comparison is **paired Turn-8 legal deterministic table-win access** across the 200 matched environments.

Required aggregate output:

- `BOTH_ACCESS`;
- `STANDARD_ONLY_ACCESS`;
- `EXPLORATORY_ONLY_ACCESS`;
- `NEITHER_ACCESS`;
- standard and exploratory paired access counts/rates;
- paired access-rate difference `(EXPLORATORY_ONLY - STANDARD_ONLY) / 200`;
- exact two-sided McNemar test on discordant pairs;
- 95% deterministic paired-bootstrap percentile interval using 10,000 preregistered resamples;
- the four raw cells and discordant-pair count alongside any p-value or interval.

A null or inconclusive primary result may not be described as evidence that the standard policy is already optimal.

### Secondary paired timing outcome

Earliest legal deterministic table-win access timing through Turn 10 is **secondary descriptive evidence** with explicit censoring.

For all 200 pairs the report distinguishes:

- both arms accessed by Turn 10;
- STANDARD-only access by Turn 10;
- EXPLORATORY-only access by Turn 10;
- neither arm accessed by Turn 10.

A numeric exploratory-minus-standard turn shift is computed only for pairs in which both arms have an observed access turn from Turn 1 through Turn 10. Pairs with one or both arms censored are reported as counts and excluded from the numeric turn-shift mean. **No Turn-11 or other synthetic access turn is imputed.**

The pilot precommits **no numeric action threshold**, including no 0.25-turn threshold. Issue #52 must use the observed primary discordance, paired access difference, censored timing categories, both-access turn shifts, and actual exploratory depth/node evidence to decide whether and how a later full study should be sized or authorized.

### Required reporting language

Every results summary must include exactly:

> These figures measure combo assembly speed against opponents who take no actions. They are not win rates and do not predict performance against interactive opponents.

Findings are stated as **table-win access by Turn N** or **combo access by Turn N**, never as win rate, wins by Turn N, or real-table performance.

Binding files:

- `docs/spec/phase-c/PHASE_C_PILOT_CONFIG.json`
- `docs/spec/phase-c/PHASE_C_PILOT_AUTHORIZATION.md`
- `docs/spec/phase-c/PHASE_C_PILOT_APPROVAL.json`
- `.github/workflows/phase-c-pilot.yml`

## Locked owner-review values

- Pilot config SHA-256: `c609c9a39e3187297fd83d275db4c94b5b5601a72918bd822a330bff1bfdfaca`.
- Pilot workflow SHA-256: `5346ea3d67dd7b38199fea2c10e2b9ca4a538142ea6653f4dfead6fa5d87b10b`.
- Pending approval-record SHA-256: `8bbd61f813e1fefa4cf60ae96fa1d409dbb612a645d4bca2b970ad661c2e3287`.
- Confirmation token: `AUTHORIZE_PHASE_C_500_STANDARD_200_EXPLORATORY`.
- Standard environment seed-plan SHA-256: `177086231a5e5e8a489cf1433929a092febc761d2d5865ab3bdd663381a3adff`.
- Paired exploratory environment-subset SHA-256: `f9d194bfba7ab83ca94fd17e4fff6b1b25c206a2dc150d7d65f384616436201c`.
- Exploratory search-seed SHA-256: `9cb1ddd5704d113029021285bfd8400a47975fde5499ce143437e471b70129dc`.
- Pair-assignment SHA-256: `149fa564e66ad70d05da116cd2c763f0e404df6733ae6c518be8fe3024f52a23`.
- Evaluator: `contextual_combo_v1` / `86c5e07daaa86362a38fad7a66d712443e32ba8af743bcaaa15576207264eca2`.
- Learning-plan SHA-256: `4884586c492c62cfd009c0a53c6d4ddd888274771c10efddc2b1853745a685e2`.
- Transcript approval-document SHA-256: `242a43347f3d73405872b43820048497cf06101b4b02a637b009f0143200c53d`.

## Durable certification provenance

### Phase A

- Durable certification file SHA-256: `3b47e516a588c1c3fda4b47ccd06b8e34c1c86ba8f025558c537f14b53eaa1c5`.
- Certified covered-content SHA-256: `sha256:33cb9af52b241372408605d9bb3d22b43bbf4560d84ad0aa78b3b3c7a74f62ef`.
- Tracked certification content commit: `ec7ce0ad841917fcc8d687db831a8d6db6755535`.
- Proven current on the final certification descendant by run 788.

### Phase B

- Durable certification file SHA-256: `9ceb04f281bf1e3de9359038e14d306b415cfb0d87ecb802ce6844606017464c`.
- Certified covered-content SHA-256: `sha256:ad75333e78300c54eca2bc79628d9340d7a819e582d1a7e18805390b8abf925c`.
- Certified technical implementation commit: `7b37e9e2308141160a79e5f6d3d77fbd4ee88db0`.
- CI provenance: run 787 / `31194210410`.
- Proven current on the certification descendant by run 788.

## Authorization model

The owner approves, holds, or rejects the exact reviewed implementation package under issue #51. Approval does **not** approve an unknown future code commit and does not authorize the 20,000/5,000 study.

If APPROVE is later recorded, a separate governance-only activation commit may change only the allowlisted Phase C pilot config and approval record. The activation workflow must prove implementation ancestry, the allowlisted diff, exact frozen digests, certifications, and all preflight gates before any pilot output path or game result can be created.

Until the owner explicitly approves:

- `execution_allowed` stays `false`;
- approval status stays pending;
- no 500/200 pilot is run;
- no 20,000/5,000 full study is run.

## Remaining work

1. Require this dashboard-only descendant to pass exact-head CI without changing the reviewed technical implementation or certification surfaces.
2. Update PR #49 to the final exact-head evidence.
3. Post a replacement digest-bound **OWNER DECISION REQUIRED** package under issue #51 that supersedes the prior stale package.
4. Stop for the owner's **APPROVE / HOLD / REJECT** decision.
5. Only after an explicit APPROVE: create the governance-only activation commit and invoke the locked manual 500/200 workflow.
6. After the pilot is audited, handle the separate full-study decision under issue #52.

## Repository health

| Item | Current state |
|---|---|
| `main` protection | Active `Protect main`; redundant Phase A ruleset disabled |
| Phase B PR | #37 merged |
| Active Phase C PR | #49 draft |
| Recovery PRs | #64, #65, #66 closed as superseded; none merged |
| Phase C technical runner | #50 completed |
| Paired study redesign | #76 closed as completed |
| `ORDER_LIBRARY_BOTTOM` runtime capability | #78 closed as completed |
| Phase C parent authorization | #48 remains open until the authorized pilot is executed and audited |
| Owner decision | #51 open and next |
| Full-study decision | #52 open and post-pilot only |
| Pilot execution | Locked; 0 authorized pilot results |
| Full study | Locked; 0 results |
