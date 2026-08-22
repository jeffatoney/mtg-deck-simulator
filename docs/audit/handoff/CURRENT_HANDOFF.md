# Current Repository Handoff

> **Machine generated. Do not hand edit.** Regenerate from repository/GitHub state.

- Generated: `2026-08-22T05:28:24+00:00`
- Repository: `jeffatoney/mtg-deck-simulator`
- Subject ref: `8b69b0aa3c3896c26f9c0823fd102dfa9a87f41f`
- Subject commit: `8b69b0aa3c3896c26f9c0823fd102dfa9a87f41f`
- Subject tree: `99514db84eb8169c7795f7c367d6516ef12265eb`
- Tracked worktree dirty: `false`

## Governance locks

- Pilot execution allowed: `false`
- Pilot authorization status: `LOCKED_PENDING_OWNER_APPROVAL`
- Approval status: `PENDING_OWNER_APPROVAL`
- Full-study execution allowed: `false`
- Full-study authorization status: `LOCKED_PENDING_POST_PILOT_REVIEW`

## Frozen study model

- STANDARD / EXPLORATORY: `500 / 200`
- Shards: `10 / 10`
- Opponent interaction modeled: `false`
- Blocking modeled: `false`
- Opponent wins modeled: `false`
- Through controlled turn: `10`
- Paired environments: `200`
- Primary outcome: `LEGAL_DETERMINISTIC_TABLE_WIN_ACCESS_BY_TURN_8`

## Durable certifications

- Phase A: `PASS`; certified content `511e0587a750f7b8b20059c0230c055160d2c135`; run `32521764886`
- Phase B: `PASS`; certified content `511e0587a750f7b8b20059c0230c055160d2c135`; run `32521764886`

## GitHub machine state

- Default branch: `main`
- Workflow runs for subject commit:
  - `Regenerate Repository Handoff` #6 — `in_progress` / `None` — https://github.com/jeffatoney/mtg-deck-simulator/actions/runs/32554424710
  - `CI` #1258 — `completed` / `success` — https://github.com/jeffatoney/mtg-deck-simulator/actions/runs/32551675276

### Open pull requests

- #77 `staging/phase-c-paired-source` -> `phase-c/pilot-authorization` at `d8363850a55a587dd1b13203cf43a94fdd7b2b4d` — draft — TEMP: validate paired Phase C redesign
- #88 `agent/interaction-coverage-contract` -> `main` at `0a6e90d6a0346b837986bfe54ac5e676f22bd5c4` — draft — Coordinator: freeze interaction-level coverage contract
- #90 `agent/policy-choice-replay-conformance` -> `agent/interaction-coverage-contract` at `490960781ba8770cf5e0e9ac4f7bd69e58f5ae4a` — draft — Agent C: enforce policy choice replay conformance
- #91 `agent/engine-rules-conformance` -> `agent/interaction-coverage-contract` at `8447444dc6b40f9315c99f5e153bd21166d3341b` — draft — Agent B: tighten engine rules conformance
- #92 `agent/integration-interaction-coverage` -> `main` at `efed1d84296f24bb34c03d131192866205666b42` — draft — Integration: reconcile interaction coverage lanes
- #99 `codex/phase-c-exploratory-v2` -> `main` at `4c9a404fc9308ecc281711b4b9b48eef6dfd441b` — draft — Phase C: directed exploratory V2 redesign
- #102 `feature/lovable-health-api` -> `main` at `dd35b269ecaaf7899bdaa58dcf6c97ec0546a60d` — ready — Add read-only Lovable health API
- #103 `feature/lovable-deck-api` -> `feature/lovable-health-api` at `29b89d050f54d704ba33fb9ee73b1b91b329aaf2` — draft — Add exact read-only Lovable deck API

### Owner review issue

- #51 `open` — [Phase C][Human Review] Approve the exact 500/200 pilot execution
- Updated: `2026-08-13T21:36:22Z`
- URL: https://github.com/jeffatoney/mtg-deck-simulator/issues/51
- Latest comment IDs: 5239383415, 5249019943, 5249085311, 5256942751, 5286665548

## Binding digests

- `docs/spec/phase-c/PHASE_C_PILOT_CONFIG.json`: `c609c9a39e3187297fd83d275db4c94b5b5601a72918bd822a330bff1bfdfaca`
- `docs/spec/phase-c/PHASE_C_PILOT_APPROVAL.json`: `8bbd61f813e1fefa4cf60ae96fa1d409dbb612a645d4bca2b970ad661c2e3287`
- `docs/spec/phase-c/PHASE_C_PILOT_AUTHORIZATION.md`: `b72122bfb363b2b357e467dbef40d731ac63e56fb19e25b26b74598775787174`
- `.github/workflows/phase-c-pilot.yml`: `e9525ce182a1914b53e25d771f8fa097cb657c23f863f0c437aaac2a337914fd`
- `.github/workflows/phase-c-diagnostic.yml`: `2120ec387bdc232d12155afbb8560a5141bf8f9a8f8066c05d0772bf4a4207e2`
- `docs/audit/phase-a-certification/CERTIFICATION.json`: `91ea467ddf747a279dd823b6576f8dfe554f184cbb6576ae85177ecb99844d59`
- `docs/audit/phase-b-certification/CERTIFICATION.json`: `7237a44a54865a1b5a52e581e425ba3f767eea1671285fae98afdca335751d40`

## Audit rule

This handoff is evidence, not authorization and not a substitute for an independent repository refresh. An auditor must verify current main/PR heads, CI, certifications, governance locks, and owner decisions before recommending the next action.
