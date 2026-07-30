# ENGINE BUILD PHASE B — COMPLETE DECK AND POLICY FRAMEWORK

## Status

**ACTIVE BINDING CONTRACT FOR PHASE B**

Phase A and its durable-certification closeout are complete. Phase B begins from merge commit `f31c9c799c175960b188a6a10fb496168b038aee` and must remain on `engine/phase-b-full-deck-policy` and draft PR #37 until every Phase B gate passes.

This contract does not authorize the 500/200 pilot or the 20,000/5,000 study.

## Authority order

1. `docs/source/MagicCompRules_2026-06-19.txt`
2. `docs/source/oracle/snapshot_v1.json`
3. `docs/spec/LEAGUE_MULLIGAN.md`
4. frozen `IDENTITY_MODEL_V2.0.0` and its approval/lock records
5. this contract
6. fixed project, policy, search, measurement, and open-decision specifications under `docs/spec/`
7. accepted architecture decision records
8. implementation

Conflicts fail closed. Frozen identity V2.0.0 may not be edited in this pull request.

## Required outcome

Phase B is complete only when the exact 98-card library and both commanders can be constructed, observed, acted upon, replayed, searched, and measured through the clean production engine with no missing, partial, or silent behavior fallback.

The implementation must provide:

- complete frozen-Oracle specifications and reviewed behavior compositions for all 80 exact card names and all 100 physical deck cards;
- every rules capability required by those cards under the modeled environment;
- an exact deck builder preserving deck-slot and physical-card identity, including basic-land multiplicity and two independent commanders;
- a shared legal-action generator and executor used by standard policies, exploratory search, replay, and competency scenarios;
- composable standard policy bundles representing the precommitted candidate axes;
- bounded exploratory search using only policy-visible observations and belief-state samples;
- opponent metadata and minimizing/adversarial choices exactly as resolved in `OPEN_DECISIONS.md`;
- complete measurements, divergence records, manifests, deterministic aggregation contracts, and immutable Phase B verification artifacts;
- continuous standing Phase A verification and renewed durable Phase A certification whenever covered content changes.

## Implementation milestones inside one branch and pull request

### B1 — Authority, inventory, and deck construction

- Resolve all 80 frozen Oracle records and the exact 100-card deck package.
- Validate 98 library cards plus Malcolm and Breeches in the command zone.
- Build unique `DeckSlot` and `CardInstance` records for every physical card.
- Add explicit coverage records: `IMPLEMENTED`, `BLOCKED`, or `UNSUPPORTED` with no implicit default.
- Reject a deck package containing any non-`IMPLEMENTED` entry.

### B2 — Required kernel primitives

Implement only capabilities required by the exact deck and modeled opponent boundary, including:

- land plays, tapped entry, reveal/as-enters choices, fixed chosen colors, bounce-land return choices, land sacrifice and basic-land search;
- colored/colorless mana, filtering, conditional opponent-color mana, commander-identity mana, life-payment mana, Treasure, tap/untap, summoning sickness, attacking status, and phase status;
- draw, failed draw, optional draw, scry, reveal/look/select, loot/rummage, discard as cost/effect, shuffle, top/bottom/third-from-top placement, and Fact or Fiction pile choices;
- generic search, basic landcycling, cycling, transmute, Wizardcycling, split-card face and mana-value rules;
- modal spells, X costs/targets, kicker, overload, cleave, foretell, flashback, aftermath, and strive;
- damage, life loss, prevention metadata, lethal processing, commander damage, creature damage, power/toughness modifications, marked damage, and dynamic characteristic values;
- countering, conditional counters, replacement destinations, bounce, destroy, exile, phasing, manifest, amass, token creation, Aura attachment, umbra armor, hexproof, and temporary effects;
- cast, ETB, draw, discard, damage, Pirate-damage, beginning-step, and delayed triggers with recorded optional and opponent choices;
- spell/ability/token copies, target retention/new-target choices, and copied-spell-not-cast invariants;
- cleanup repetition, empty-library loss, and terminal short-circuiting.

Unsupported rules requirements must block the affected card/action/scenario. They may not silently no-op.

### B3 — Complete card migration and competency

- Every exact deck entry must execute through Oracle-ID keyed data and universal primitives.
- Card names may be lookup/display values but may not select kernel control flow.
- Implement every competency ID in `docs/spec/RULES_ACCEPTANCE.md`, including CR-001–CR-022, EL-001–EL-007, OT-001–OT-012, PROP-001–PROP-010, and all listed card-specific boundaries.
- Every test records its authority reference and stable test ID.
- Complete coverage must be machine-readable and reject missing or unreviewed entries.

### B4 — Standard policy framework

- Policy bundles are configuration, not scattered card-name conditionals.
- Candidate axes come from `POLICY_CANDIDATES.md` and the precommitted matrix in `configs/policies.yaml`.
- Candidate definitions are hypotheses to compare, not strategic truths supplied by the owner.
- Policies receive only `Observation` and legal action descriptions.
- Implement mulligan decisions at 7, 6, 5, and 4; development ordering; commander/Breeches timing; tutor priorities; combo choice; cantrip/ramp ordering; protection delay; Muddle use; and Glint-Horn value timing.
- Create immutable discovery and validation seed lists before any policy evaluation result exists.
- Implement paired-comparison and first-divergence records.
- Do not run policy discovery or pilot games in Phase B acceptance.

### B5 — Bounded exploratory search

Enforce exactly:

- at most 12 branches per major decision;
- at most three simulated player turns of look-ahead;
- at most 5,000 nodes per game;
- beam width of eight retained actions per layer;
- no more than eight common-random belief samples per unknown event;
- the frozen lexicographic ranking in `EXPLORATORY_SEARCH_LIMITS.md`.

The search receives the same restricted observation as policy code. Actual hidden library order and future random outcomes must be structurally unavailable. Search logs candidate count, branch count, nodes, depth, pruning, sample seeds, selected action, and first standard/exploratory divergence. Manual replay results remain separately classified.

### B6 — Measurements, replay, and manifests

Implement all fields in `MEASUREMENTS.md`, including:

- opening hands, mulligan counts, mana/action-density failures;
- combo access and first legal attempt by checkpoint;
- protection availability/payability and independent second lines;
- card draw/cast/held/stranded/contribution records;
- paired standard/exploratory differences and safeguard rejection counts;
- exact denominators and uncertainty-ready raw records.

Run manifests bind commit, dirty flag, Python/dependency/rules/Oracle/deck/config/seed hashes, command, timestamps, worker count, and same-commit test evidence. Aggregation rejects mixed commits/configs/sources, duplicate seeds, and gaps. Replay and audit do not call policy decision code.

### B7 — Verification and review

Provide `mtg-engine verify-phase-b`, which must:

- run the full Phase A standing verifier;
- validate all 100 deck cards and 80 Oracle records;
- execute all Phase B competency, property, policy, search, measurement, replay, and manifest tests;
- verify hidden-information and seed-separation boundaries;
- verify the pilot/full-study locks;
- map every blocking Phase B requirement to named tests;
- write an immutable `CLEAN_ENGINE_PRODUCTION_PATH` result artifact bound to the exact tested commit;
- report unsupported capabilities and fail when any affects the exact deck or modeled scenarios.

Phase B remains NO-GO until independent review finds no unresolved P1 or P2 correctness issue and all CI/durable-certification gates pass on one exact commit.

## Blocking requirements

| ID | Requirement |
|---|---|
| B-SOURCE-001 | All 80 exact names resolve to complete frozen Oracle records and all 100 deck cards resolve to unique deck slots/instances. |
| B-COVERAGE-001 | Every deck entry has reviewed `IMPLEMENTED` coverage; missing, partial, blocked, or fallback behavior prevents verification. |
| B-DECK-001 | The exact 98-card library and two command-zone commanders are constructed with correct quantities and identities. |
| B-RULES-001 | Every competency and card-specific boundary in `RULES_ACCEPTANCE.md` passes through the clean production path. |
| B-LEGALITY-001 | Standard policy, search, replay, and scenarios use the same legal-action generator and executor. |
| B-HIDDEN-001 | Policy/search cannot access hidden identities, actual future order, or future events. |
| B-OPPONENT-001 | Opponent metadata and choices follow frozen baseline decisions and never assume favorable or unspecified resources. |
| B-POLICY-001 | All required policy axes are explicit, immutable, observation-only configurations with discovery/validation separation. |
| B-SEARCH-001 | Exploratory search enforces all frozen bounds, belief sampling, logging, and no-selective-replay safeguards. |
| B-MEASURE-001 | Every required raw measurement and denominator is emitted deterministically. |
| B-REPLAY-001 | Replay/audit independently reconstructs legal execution and is invariant to worker count. |
| B-MANIFEST-001 | Run manifests and aggregation are immutable, complete, and reject mixed/duplicate/gapped inputs. |
| B-PHASE-A-001 | Standing Phase A verification remains PASS and durable Phase A certification is renewed for the final covered surface. |
| B-PILOT-LOCK-001 | The 500/200 pilot and full study remain unavailable and unexecuted throughout Phase B. |

## Evidence rules

- Only clean production-path execution satisfies Phase B.
- Legacy code, legacy tests, quarantined artifacts, source validation alone, schemas alone, or mocked event-log shortcuts cannot satisfy a behavior requirement.
- No claim of completion may rely on an unpushed workspace, dirty tree, stale certification, or artifact from a different commit.
- Failed runs remain immutable and are never overwritten.

## Final Phase B deliverable

One reviewed merge commit on `main` containing the complete deck, policy/search/measurement framework, Phase B verifier, exact-head result artifact, and renewed durable Phase A certification. Phase C remains separately authorized and locked.
