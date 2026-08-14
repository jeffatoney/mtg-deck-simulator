# Phase C Exploratory V2 Design

Status: IMPLEMENTATION / NON_AUTHORIZED_DIAGNOSTIC ONLY

This specification replaces the ineffective V1 exploratory decision mechanism without changing or invalidating the completed Phase C pilot. The historical pilot run `31752039318`, implementation `150671a8e7a78e5fa14b6b3aca2308f6af647df3`, and audit branch `audit/phase-c-postpilot-31752039318` remain frozen evidence. The 20,000 STANDARD / 5,000 EXPLORATORY study remains unauthorized.

## V1 diagnosis

The V1 production explorer performed exactly one successor transition for each candidate and evaluated that immediate successor. It discarded the belief seed during expansion, created a successor with no further actions, and then repeated a fresh shallow exploratory choice at the next priority window. That design had four consequential defects:

1. A developmental action was judged before its downstream value could materialize.
2. `PASS_PRIORITY` could preserve the current heuristic state and therefore defeat a land play or other setup action whose value was delayed.
3. The exploratory choice replaced competent STANDARD continuation rather than making one strategic deviation and then using competent continuation.
4. The decision record stored only selected-branch search metadata. It did not persist a complete score vector for every considered candidate, so the exact numeric comparisons could not be reconstructed after the pilot.

The post-pilot audit confirmed the practical result: all 200 paired exploratory games first diverged on Turn 1 with exploratory `PASS_PRIORITY` versus STANDARD `PLAY_LAND`, and the exploratory arm did not develop normally.

## Architectural boundary

V2 remains above the rules kernel. The shared `ActionBroker` is the sole source of legal priority actions. Rules-defined strategic requests continue to expose only observation-safe candidates through `mtg_kernel.strategic_choices`. Unsupported strategic decisions fail closed. V2 does not alter Oracle data, the deck, card implementations, legality validation, or STANDARD policy behavior.

## Arms

### EXPLORATORY_AGGRESSIVE_V2

Purpose: establish legal deterministic full-table access as early as possible. Glint-Horn tutoring is permitted. Deterministic access now and strictly earlier deterministic access are hard objective gates. Novelty is subordinate.

### EXPLORATORY_ALT_PACKAGE_NO_GLINT_TUTOR_V2

Reporting label: **CONSTRAINED COUNTERFACTUAL: NO GLINT-HORN TUTORING**.

Purpose: measure alternative-package behavior when deliberate library selection of Glint-Horn Buccaneer is prohibited. Glint-Horn remains in the frozen deck, may be naturally drawn, and may be used normally after a natural draw. Every tutor/search candidate set records Glint-Horn as an arm-specific exclusion when it was otherwise legal. Results from this arm must not be pooled with unrestricted exploration or described as the optimal deck policy.

### EXPLORATORY_INTERACTION_DISCOVERY_V2

Purpose: maximize useful canonical interaction and strategic-choice coverage, with deterministic access and productive development as secondary preferences. Raw object handles and card-instance IDs are excluded from discovery signatures.

Discovery classifications are:

- `NEW_PACKAGE_SEQUENCE`
- `NEW_TUTOR_TARGET`
- `NEW_MODAL_SELECTION`
- `NEW_ACTIVATED_ABILITY_LINE`
- `NEW_MANA_SEQUENCE`
- `NEW_DRAW_OR_DISCARD_SEQUENCE`
- `NEW_COMMANDER_SEQUENCE`
- `NEW_CONDITIONAL_ACCESS_LINE`
- `NEW_DETERMINISTIC_ACCESS_LINE`
- `REVISITED_UNDEREXPLORED_LINE`

## Candidate generation and baseline retention

At an eligible strategic decision V2 consumes the complete legal set produced by the shared broker or strategic-choice request. The STANDARD action is always retained as the explicit baseline candidate, even when an arm-specific prohibition makes it ineligible for final selection. Any pruning is recorded with a machine-readable reason.

Routine forced continuations and a sole legal `PASS_PRIORITY` are not treated as exploratory decisions.

## Score vector

Every considered candidate persists:

- immediate deterministic access;
- projected bounded-horizon deterministic access;
- earliest projected access turn;
- known-package progress;
- mana-development value;
- relevant-resource preservation;
- card-selection or tutor value;
- conditional-access status;
- novelty value;
- arm-specific constraint status;
- action cost;
- reason codes;
- final candidate rank.

Legal deterministic access continues to use the existing `ComboAccessTracker` definitions. Psychosis Crawler conditional access remains separate from deterministic full-table access.

## Competent continuation

V2 uses `ONE_DEVIATION_THEN_STANDARD_VISIBLE_HORIZON`.

For each safe-to-project priority candidate, V2 clones the current state, applies that one candidate, then follows the frozen STANDARD priority policy for up to eight additional visible-state actions. Continuation stops before a hidden-information boundary, before resolving a stack object through speculative opponent passes, when STANDARD passes, when priority leaves the controlled player, when the game terminates, or at the configured action cap. The actual environment library order and future environment random stream are never used for candidate ranking.

Actions that themselves expose unknown future random information are scored from current observation and explicit future-development features without speculative execution. This intentionally trades search depth for a verifiable hidden-information boundary.

## Controlled exploration

Candidates are lexicographically ranked under the arm objective. Immediate deterministic access, projected deterministic access, and earliest projected access turn are exact gates in the aggressive arms. A configured equivalence window applies only to lower-priority development/resource dimensions. The selector takes at most the configured top-k near-equivalent candidates and uses a SHA-256-derived local PRNG stream seeded only by the exploration seed, arm ID, and public decision identity. It never consumes environment RNG.

Novelty weighting cannot override legality, an immediate deterministic win, a strictly earlier deterministic line, required mana development, or an arm-specific prohibition.

## Mana-development guardrail

A `PASS_PRIORITY` candidate is ineligible in a main phase when a legal `PLAY_LAND` candidate exists unless a finite, evidence-backed land-hold reason is recorded. Passing priority is never itself a reason. The permitted reason-code set is versioned with the policy implementation; there is no `OTHER` escape hatch.

The guardrail is not the scoring model. Land plays, low-cost mana permanents, mana abilities, tutors, and setup permanents also receive explicit developmental value so delayed value remains visible to the evaluator.

## Hidden-information protection

The selection seed is independent of the environment seed. Public decision IDs and canonical interaction signatures exclude hidden library state and raw engine identity. Candidate projection stops before draw, scry, look, random, shuffle, search/tutor, transmute, typecycle, or impulse boundaries when executing the hypothetical branch would reveal information unavailable to the policy at the decision being evaluated.

Tests must mutate hidden future state while preserving the policy observation and verify the same semantic action selection.

## Evidence and replay

The decision schema is `EXPLORATORY_V2_DECISION_SCHEMA.json`. V2 records complete candidate vectors, baseline retention, pruning/exclusions, novelty-before state, equivalence set, seeded selection evidence, continuation details, public-state digests, and replay binding. Diagnostic execution must verify engine transcript replay and separately reproduce V2 decision evidence from fixed environment/exploration seeds.

## Pilot boundary

All V2 configs have `pilot_activation: false`. V2 diagnostic workflows may create only artifacts labeled `NON_AUTHORIZED_DIAGNOSTIC`. They must not call the historical pilot artifact writer or create pilot manifests, official summaries, aggregate pilot digests, approval records, or full-study activation files.
