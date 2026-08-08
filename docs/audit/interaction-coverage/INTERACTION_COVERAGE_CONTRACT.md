# Interaction Coverage Contract

**Status:** COORDINATOR_FROZEN_V1

**Purpose:** Define the finite rules-interaction surface that must be proven before Phase C simulation results may be treated as reliable.

This contract does not rewrite the engine and does not replace the existing Phase A or Phase B certifications. It adds a stricter interaction-level definition of coverage so a card cannot be declared covered merely because its card name has a handler or one representative path has a passing test.

## 1. Coverage unit

The atomic coverage unit is an **interaction record**.

For exact-deck card behavior, the canonical chain is:

`card -> ability/effect -> event/timing -> choice -> legality -> policy -> replay -> test`

One card may produce many interaction records. A nested effect may produce its own record. A card is covered only when every required record derived from its frozen Oracle behavior is PROVEN.

Engine-wide rules interactions that are not owned by one card use `GLOBAL_RULE` records and are held to the same proof standard.

## 2. Status vocabulary

Only these statuses are permitted:

- `UNMAPPED`: a rules-relevant interaction or choice exists but is not classified in the frozen surface.
- `MAPPED`: the interaction is present in the surface and all choice purposes are explicitly classified.
- `IMPLEMENTED`: production engine/policy/replay handling has been identified, but proof evidence is incomplete.
- `PROVEN`: all required rules, legality, policy, replay, and deterministic test evidence passes.

`IMPLEMENTED` is not equivalent to `PROVEN`.

## 3. What must be recorded

Every `CARD_EFFECT` record must identify:

1. exact card name and Oracle ID;
2. stable ability ID and ability kind;
3. behavior index and nested effect path;
4. effect kind and a canonical effect digest;
5. the event or rules timing at which the effect becomes relevant;
6. every rules-relevant player choice purpose;
7. when each choice is legally made;
8. who makes each choice;
9. which engine layer owns legality;
10. whether strategic or opponent policy is required when more than one legal choice exists;
11. what replay must persist rather than recompute;
12. the rules/Oracle authority for the interaction; and
13. deterministic production-path tests proving the positive and applicable negative paths.

No field may silently mean “default policy,” “obvious target,” “first legal choice,” or “engine decides.” If the rules create a choice, it must have an explicit purpose and timing. If the rules do not create a choice, the effect kind must still be explicitly classified as having no additional resolution choice.

## 4. Choice timing is normative

The choice timing vocabulary is:

- `CAST_PROPOSAL`: modes, alternative/additional costs, X, target count, and spell targets chosen while casting.
- `ACTIVATION_PROPOSAL`: activated-ability modes/targets/cost choices made while activating.
- `TRIGGER_STACKING`: trigger modes, targets, and ordering decisions made as triggered abilities are put on the stack.
- `RESOLUTION`: choices made while a resolving spell or ability is applied.
- `REPLACEMENT_APPLICATION`: choices required before or while applying a replacement/prevention effect.
- `SPECIAL_ACTION`: choices made as part of a special action.
- `TURN_BASED_ACTION`: choices made by a turn-based action.
- `STATE_BASED_ACTION`: choices required by a state-based action.

A downstream implementation may not move a choice to a more convenient stage. In particular, policy must not supply a target during resolution when the Comprehensive Rules require the target as a spell/ability is put on the stack.

## 5. Legality and policy separation

Rules legality belongs to the rules engine. Policy selects only among choices already established as legal by the production rules path.

A record fails proof if any of the following occurs:

- policy invents or broadens the legal candidate set;
- a broker advertises an action the production executor later rejects for a rules restriction that should have been known at proposal time;
- a missing mandatory choice is replaced by first/lowest/default selection;
- a strategic evaluator reads hidden future information;
- an opponent-required choice is resolved favorably for this deck rather than by the documented opponent policy; or
- a failed legality check leaves a partially mutated game state.

## 6. Required choice classes

The surface generator creates structural choices directly from card behavior metadata, including:

- cast path / face / mode selection;
- X or variable-count selection;
- spell target and target-count selection;
- activated-ability targets;
- triggered-ability targets and optional trigger decisions;
- additional or optional casting costs represented in the frozen behavior; and
- special-action choices represented in the behavior.

Effect-specific choices that cannot be inferred safely from the generic structure are frozen in `automation/interaction-choice-contracts.json`.

Every observed effect kind must appear in that file, including effect kinds with zero additional choices. An unknown effect kind is a blocking `UNMAPPED` interaction, not an implicit no-choice effect.

## 7. Replay requirement

For every nontrivial player or policy choice, replay must consume the recorded decision rather than rerun strategic policy. Replay evidence must be sufficient to reject missing, added, reordered, or altered decisions and must revalidate legality through the same production rules path.

A Phase C-reachable choice path is not PROVEN until a deterministic test demonstrates fresh-process replay for a scenario that exercises that choice, either directly or through an exact production-seed regression.

## 8. Test requirement

A record reaches `PROVEN` only when evidence includes, as applicable:

- one deterministic positive production-path execution;
- one deterministic negative/atomic legality test for each material invalid-choice family;
- proof that the correct choice timing was used;
- proof that policy received only observation-safe legal candidates when policy is required;
- proof that recorded replay reproduces the choice without rerunning policy; and
- fresh-process replay evidence for Phase C-reachable runtime choices.

A broad smoke test, card-name registration test, or successful random game is supporting evidence, not sufficient interaction proof by itself.

## 9. Deck and project PASS criteria

The interaction coverage gate is PASS only when all of the following are true on one exact commit:

1. exact deck identity remains 98 library cards plus two commanders and 80 unique Oracle-bound card definitions;
2. the generated interaction surface matches the frozen interaction-surface digest;
3. every behavior and nested effect is represented by a stable interaction record;
4. every effect kind has an explicit choice classification;
5. no record is `UNMAPPED`, `MAPPED`, or `IMPLEMENTED` in the proof ledger;
6. every required choice purpose has legality, policy, replay, and deterministic test evidence appropriate to that choice;
7. all `GLOBAL_RULE` records are PROVEN;
8. all referenced tests pass with zero skip and zero xfail for blocking interaction evidence;
9. no generic/default/fallback choice path can execute for a frozen-deck interaction; and
10. the complete proof report reports `PROVEN == total`, `unproven == 0`, and `unknown_choice_purposes == 0`.

Until those conditions are met, Phase A/Phase B certification may remain valid for its historical scope, but **interaction-proof coverage is not complete**.

## 10. Frozen global-rule interaction classes

The following engine-wide interactions are part of this contract even though they are not owned by one card:

- `GLOBAL-TRIGGER-ORDERING`: simultaneous triggered abilities and APNAP/order choices.
- `GLOBAL-REPLACEMENT-ORDERING`: competing replacement/prevention effects and affected-player choice.
- `GLOBAL-CLEANUP-REENTRY`: cleanup triggers, priority exception, and additional cleanup steps.
- `GLOBAL-ILLEGAL-ACTION-ROLLBACK`: illegal proposals are atomic and restore the prior state.
- `GLOBAL-SBA-TIMING`: state-based actions occur at rules-defined checkpoints, not during resolution.
- `GLOBAL-COMMANDER-REPLACEMENT`: commander zone-replacement choices and subsequent object identity.
- `GLOBAL-PRIORITY-STACK-LIFO`: priority and stack last-in/first-out execution.

Downstream proof work may add narrower global records but may not remove or weaken these seven.

## 11. Coordinator outputs and downstream change control

This coordinator freeze consists of:

- this contract;
- `automation/interaction-record.schema.json`;
- `automation/interaction-choice-contracts.json`;
- `automation/interaction-coverage-lock.json`;
- `scripts/build_interaction_coverage_manifest.py`; and
- `tests/interaction_coverage/test_interaction_coverage_contract.py`.

Downstream agents may implement missing behavior and add proof evidence, but they may not silently alter the coverage unit, timing vocabulary, PASS criteria, or remove interaction records. A change to this contract or to the frozen surface requires a separately reviewed coordinator/specification change with a new surface digest.

## 12. Rules authority used for the coordinator freeze

The supplied Comprehensive Rules dated 2026-06-19 establish the key timing distinctions used here:

- rule 601.2b: spell mode, alternative/additional-cost, and X choices during casting;
- rule 601.2c: spell target and variable target-count choices during casting;
- rules 115.1c-d and 603.3d: activated and triggered targets are chosen when those abilities are put on the stack;
- rule 608.2d: choices not already made as part of casting/activation/stack placement are made while resolving the effect;
- rule 614.12a: a replacement-effect choice that modifies battlefield entry is made before the permanent enters;
- rule 616.1: the affected player/controller chooses among competing applicable replacement/prevention effects; and
- rules 707.10 and 707.10c: spell copies copy prior decisions and are not cast; new targets may be chosen only when the copying effect permits it.
