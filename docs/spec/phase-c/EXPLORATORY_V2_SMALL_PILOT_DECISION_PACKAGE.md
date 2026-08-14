# Exploratory V2 Small-Pilot Owner Decision Package

Status: **PREPARED, NOT AUTHORIZED**

This package is for an owner decision after all V2 technical gates pass. It does not activate or execute a pilot.

## Proposed smallest technical pilot

Use **32 games per exploratory arm**. This is a behavior-validation pilot, not an outcome-estimation study.

- Arm 1: 32 `EXPLORATORY_AGGRESSIVE_V2` games, paired with 32 unchanged STANDARD games on the same environment seeds.
- Arm 2: 32 `EXPLORATORY_ALT_PACKAGE_NO_GLINT_TUTOR_V2` games on the same 32 paired environment seeds for descriptive counterfactual comparison. The no-Glint-tutor constraint must remain explicit in every result.
- Arm 3: 32 `EXPLORATORY_INTERACTION_DISCOVERY_V2` games on a separate 32-seed environment set. Its primary analysis is coverage/discovery, not win-access difference.

The paired STANDARD executions may be reused as the control for Arms 1 and 2 because the environment seeds match exactly. No arm result is pooled with another arm.

## Seed construction

Convert a namespace string to an unsigned 63-bit seed with:

`int.from_bytes(SHA256(namespace UTF-8)[:8], "big") & ((1 << 63) - 1)`.

Pilot indexes are 1 through 32.

- Paired environment seed namespace: `phase-c-exploratory-v2-small-pilot:v1:paired-env:<index>`.
- Arm 1 exploration namespace: `phase-c-exploratory-v2-small-pilot:v1:aggressive-search:<index>`.
- Arm 2 exploration namespace: `phase-c-exploratory-v2-small-pilot:v1:alt-no-glint-search:<index>`.
- Arm 3 environment namespace: `phase-c-exploratory-v2-small-pilot:v1:discovery-env:<index>`.
- Arm 3 exploration namespace: `phase-c-exploratory-v2-small-pilot:v1:discovery-search:<index>`.

Environment and exploration domains must be proven disjoint before activation.

Indexes 33 through 48 in each namespace are reserved as a 16-game holdout and must not be used during implementation, tuning, or the 32-game technical pilot.

## Frozen selector values

- selection: `SEEDED_WEIGHTED_TOP_K_WITH_HARD_OBJECTIVE_GATES`;
- Arm 1 top-k 3; novelty weight 100,000 microunits;
- Arm 2 top-k 3; novelty weight 100,000 microunits;
- Arm 3 top-k 4; novelty weight 500,000 microunits;
- continuation: `ONE_DEVIATION_THEN_STANDARD_VISIBLE_HORIZON`;
- continuation limit: 8 STANDARD actions;
- exact equivalence windows: the committed arm configuration files;
- evaluator definition: `configs/evaluators/exploratory_v2_scoring.yaml` plus each arm configuration digest.

The final pilot authorization record must bind the exact implementation commit, tree, all four scoring/config files, decision schema, workflow, STANDARD policy digest, and evaluator digest.

## Required stop conditions

Stop the technical pilot immediately if any arm has:

- one legality failure;
- one transcript replay failure;
- one fresh-policy decision recomputation failure;
- one missing STANDARD baseline candidate;
- one missing candidate score vector without a documented pruning reason;
- one main-phase land-development violation;
- one hidden-future invariant violation;
- one environment/exploration RNG-domain collision;
- one Arm 2 Glint-Horn tutor selection;
- one artifact missing its arm ID/config digest/classification;
- any pilot/full-study artifact produced outside the separately authorized pilot root.

## Minimum behavior thresholds

These are defect-detection thresholds, not claims of statistical power.

### Arm 1

- 100% replay/evidence/land-development compliance;
- at least one legal Glint-Horn tutor opportunity may be selected if presented by the pilot draws;
- at least two actual deterministic-package attempts across the 32 games;
- at least two package IDs visited in candidate/plan evidence when legally reachable.

### Arm 2

- 100% replay/evidence/land-development compliance;
- zero selected Glint-Horn tutor targets;
- every prohibited Glint-Horn tutor opportunity records the legal alternative targets;
- at least two actual alternate-package attempts across the 32 games;
- naturally drawn Glint-Horn remains usable and is not policy-suppressed.

### Arm 3

- 100% replay/evidence/land-development compliance;
- at least three package IDs visited when legally reachable;
- at least eight unique canonical useful-discovery signatures;
- at least three discovery classifications represented;
- duplicate-discovery rate reported, not optimized post hoc;
- deterministic-access results reported only as secondary context.

Targeted golden scenarios remain the authoritative proof for features that a random 32-game draw set does not present.

## Exact artifacts to produce if authorized

Each arm receives its own immutable:

- authorization binding;
- config/evaluator digest record;
- environment-seed inventory;
- exploration-seed inventory;
- game manifest;
- per-game technical record;
- complete decision-evidence stream;
- measurement file;
- replay report;
- arm summary;
- limitations file;
- aggregate digest for that arm only.

A top-level index may link the three arms but must not calculate a pooled access rate.

## Proposed owner authorization text

> I authorize one Phase C Exploratory V2 technical pilot only: 32 games for each of the three committed V2 exploratory arms, plus the paired unchanged STANDARD controls described in `EXPLORATORY_V2_SMALL_PILOT_DECISION_PACKAGE.md`. I authorize only the exact implementation commit, tree, arm configurations, scoring configuration, seed construction, holdout separation, workflows, stop conditions, and artifact schemas bound by the activation record. This authorization does not authorize the 20,000 STANDARD / 5,000 EXPLORATORY study, does not authorize post-result policy tuning, does not alter the completed historical Phase C pilot, and does not authorize closing Issue #52.
