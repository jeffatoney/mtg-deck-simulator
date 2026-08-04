# ADR-0015: Strategic choices and learned evaluator snapshots stay outside the rules kernel

## Status

Accepted for the Phase B corrective slice.

## Context

Magic rules determine legal actions, choice timing, information visibility, costs, targets, resolution, and zone changes. They do not determine how valuable a card is in a particular game state. The original Fact or Fiction implementation mixed those responsibilities by placing a context-free card score inside the rules kernel. Missing effect classifications silently scored zero, excess lands could outrank combo completion, and every policy shared one untestable strategic brain.

The project also needs a path for organic improvement. Repeated discovery examples may show that a card, feature, or interaction is more useful than the initial human-designed evaluator predicted. That learning must not rewrite a live canonical run or inspect validation outcomes while fitting.

## Decision

1. The rules kernel enumerates legal choices and applies the selected choice. It does not assign strategic value.
2. Strategic decisions are injected through an observation-only provider at the rules-defined choice time.
3. Tutor selection occurs during resolution. Fail to find remains legal when searching a hidden zone for a stated quality.
4. Fact or Fiction revelation and legal partition enumeration remain in the kernel. The opponent split and caster pile selection come from a policy-layer evaluator.
5. The baseline evaluator is a versioned, content-addressed configuration with explicit effect classifications, combo packages, land-curve assumptions, and fail-closed treatment of missing classifications.
6. Adjustable strategy assumptions are represented as evaluator or policy configuration fields, not code edits.
7. Learning is offline and discovery-only. It consumes 4,800 predeclared discovery comparisons from the exact 300 frozen discovery seeds, uses the first 200 seeds for mining/initial fitting and the remaining 100 for confirmation, freezes the feature set, refits on all discovery examples, and evaluates the resulting frozen snapshot exactly once on 1,000 comparisons from the untouched 200 validation seeds.
8. Every pairwise label compares alternatives from the same initial state, same future RNG streams, same continuation policy, same hidden-information boundary, and the same Turn-10-or-terminal horizon. Validation data cannot change features, thresholds, or learned weights. A snapshot may be activated only after it is marked `FROZEN_VALIDATED` and its identity and SHA-256 are bound into policy configuration, run manifests, and certification evidence.
9. Promotion requires at least a three-percentage-point paired validation-accuracy improvement over the human evaluator, a seed-clustered 95% confidence interval whose lower bound is above zero, and no regression in checkpoint table-kill access, full-table-kill rate, or median earliest legal-attempt turn. Canonical and exploratory runs do not update weights, add features, or select a different snapshot after outcomes are known.
10. Raw discovery records preserve only policy-visible card identities, zones, legal action signatures, ordered prior actions, mana/land context, combo/protection access, and both counterfactual outcomes. Internal object IDs, card-instance IDs, hidden library order, and future event fields are prohibited. Replay consumes recorded strategic choices and does not import or rerun policy or learning code.
11. A missing strategic classification or unadjudicated deterministic combo loop is a hard unsupported capability, not a neutral score or guessed result.

## Consequences

- Human-designed and learned evaluators can be compared as explicit adjustable policy buttons.
- A 4,800-comparison discovery set (300 frozen seeds × 16 comparisons) can improve preferences without contaminating canonical results, provided the feature set is frozen before refitting and the snapshot is frozen before holdout validation.
- Newly mined generic-feature, card-pair, and action-sequence interactions are hypothesis-ranking candidates only. They make no uncorrected significance claim and never become active behavior automatically.
- Every reported result identifies the exact evaluator snapshot that produced it.
- Changes to evaluator content, learning plans, strategic-choice contracts, or kernel choice timing require new hashes and the normal exact-head verification cycle.
