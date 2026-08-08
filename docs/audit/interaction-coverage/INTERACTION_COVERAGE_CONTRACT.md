# Interaction Coverage Contract

**Status:** COORDINATOR_CANDIDATE_V1

**Purpose:** Define the finite rules-interaction surface that must be proven before Phase C simulation results may be treated as reliable.

This contract does not rewrite the engine and does not replace the existing Phase A or Phase B certifications. It adds a stricter interaction-level definition of coverage so a card cannot be declared covered merely because its card name has a handler or one representative path has a passing test.

This is an **exact-deck interaction contract**, not a claim that the engine implements every rule or card in Magic. Existing Phase A unsupported capabilities remain outside this contract unless a frozen exact-deck behavior or a required global interaction reaches them. If one becomes exact-deck-reachable, it becomes blocking here rather than remaining silently out of scope.

## 1. Coverage unit

The atomic execution coverage unit is an **interaction record**.

For exact-deck behavior, the canonical chain is:

`card -> ability/effect -> event/timing -> choice -> legality -> policy -> replay -> test`

One card may produce many `CARD_EFFECT` records. A nested effect may produce its own record. Engine-wide rules interactions that are not owned by one card use `GLOBAL_RULE` records.

There is also one `CARD_COMPOSITION` guard for every unique Oracle-bound card definition. That guard proves that the frozen Oracle wording was completely decomposed into the behavior model before any child interaction may be treated as fully covered. This is required because rule 108.1 makes the Oracle card reference authoritative for a card's wording.

A card is covered only when its `CARD_COMPOSITION` guard and every required `CARD_EFFECT` record are PROVEN.

## 2. Oracle composition boundary

The repository's existing `REVIEWED_COMPOSITION` value is retained as inherited Phase B inventory metadata. It is **not** elevated by this coordinator to independent proof that every Oracle sentence was modeled correctly.

Each generated record is pinned to:

- exact card name;
- Oracle ID;
- frozen Oracle-record SHA-256;
- the inherited composition status; and
- the frozen behavior/legality digest.

Each card also receives a `CARD_COMPOSITION` record that binds the Oracle digest to the complete behavior tuple. That record remains `MAPPED` until later proof work supplies independent evidence that all rules-relevant Oracle text, faces, permissions, costs, abilities, restrictions, and choices are represented. If the inherited Phase B composition claim is later invalidated, the corresponding composition guard cannot be PROVEN and the surface must be revised before Phase C certification.

## 3. Status vocabulary

Only these statuses are permitted:

- `UNMAPPED`: a rules-relevant interaction or choice exists but is not classified in the frozen surface.
- `MAPPED`: the interaction is present in the surface and all known choice purposes are explicitly classified.
- `IMPLEMENTED`: production engine/policy/replay handling has been identified, but proof evidence is incomplete.
- `PROVEN`: all required composition, rules, legality, policy, replay, and deterministic test evidence passes.

`IMPLEMENTED` is not equivalent to `PROVEN`.

The coordinator-generated surface is intentionally emitted as `MAPPED`. Freezing the coordinator specification does not assert that mapped interactions are already implemented or proven.

## 4. Required record contents

Every `CARD_EFFECT` record must identify:

1. exact card name, Oracle ID, and frozen Oracle-record digest;
2. inherited composition status;
3. stable ability ID and ability kind;
4. behavior index and nested effect path;
5. effect kind and canonical effect digest;
6. the event/timing at which the effect becomes relevant;
7. every rules-relevant player choice purpose;
8. when each choice is legally made;
9. who makes each choice;
10. which engine layer owns legality;
11. the frozen legality-contract digest for the complete behavior and target schema when one exists;
12. whether the actual actor's strategic policy, an opponent-minimizing policy, or no strategic policy is required;
13. what replay must persist rather than recompute;
14. rules/Oracle authority; and
15. deterministic production-path evidence.

Every `CARD_COMPOSITION` record must bind one Oracle record to the complete behavior tuple for that card. It may reach `PROVEN` only after independent composition evidence demonstrates that no rules-relevant Oracle text was omitted, merged incorrectly, or replaced by a different behavior contract.

No field may silently mean "default policy," "obvious target," "first legal choice," or "engine decides." If the rules create a choice, it must have an explicit purpose and timing. If an effect kind creates no additional resolution choice, that no-choice classification must still be explicit.

## 5. Choice timing is normative

The choice timing vocabulary is:

- `CAST_PROPOSAL`: modes, alternative/additional-cost declarations, X, target count, spell targets, and hybrid-cost configuration chosen while casting.
- `ACTIVATION_PROPOSAL`: activated-ability modes, targets, and hybrid activation-cost configuration chosen while proposing an activation.
- `COST_PAYMENT`: mana-ability sequencing, exact mana payment, payment order, discard identity, sacrifice identity, and other choices made while paying a spell or ability cost.
- `TRIGGER_STACKING`: trigger modes, targets, and ordering decisions made as triggered abilities are put on the stack.
- `RESOLUTION`: choices made while a spell or ability resolves. Activated mana abilities resolve immediately after activation and do not use the stack; choices made by their mana-producing effect are resolution choices, not proposal choices.
- `REPLACEMENT_APPLICATION`: choices required before or while applying a replacement/prevention effect.
- `SPECIAL_ACTION`: choices made as part of a special action.
- `TURN_BASED_ACTION`: choices made by a turn-based action, including declaring attackers and choosing cleanup discards.
- `STATE_BASED_ACTION`: choices required by a state-based action, including the legend rule and Commander rule 903.9a.
- `PRIORITY_WINDOW`: the priority holder chooses a legal action or passes priority.

A downstream implementation may not move a choice to a more convenient stage. Policy must not supply a target during resolution when the Comprehensive Rules require the target as a spell or ability is put on the stack, and a deterministic mana-payment helper may not silently stand in for a rules-relevant payment choice.

## 6. Legality and policy separation

Rules legality belongs to the rules engine. Policy selects only among choices already established as legal by the production rules path.

`ACTOR_POLICY` means the policy belongs to whichever player actually makes the choice in the current game state. This is required for effects such as a counterspell whose target controller may be this deck or an opponent; opponent policy cannot be assumed merely from the effect family.

A record fails proof if any of the following occurs:

- policy invents or broadens the legal candidate set;
- a broker advertises an action the production executor later rejects for a rules restriction that should have been known at proposal time;
- a missing mandatory choice is replaced by first/lowest/default selection;
- a strategic evaluator reads hidden future information;
- an opponent-required choice is resolved favorably for this deck rather than by the documented actor/opponent policy;
- a mana or nonmana cost choice is resolved by an undocumented fixed ordering when legally distinct choices can affect state or future options; or
- a failed legality check leaves a partially mutated game state.

## 7. Required choice classes

The surface generator creates structural choices directly from frozen card behavior and Oracle metadata, including:

- cast path / face / mode selection;
- X or variable-count selection;
- spell target and target-count selection;
- activated-ability targets;
- triggered-ability targets and optional trigger decisions;
- kicker and other explicit alternative/additional cost declarations represented in the frozen behavior;
- hybrid-cost configuration;
- discard-cost card identity when the behavior represents a discard cost;
- additional sacrifice selection when a frozen behavior requires a qualifying permanent; and
- special-action choices represented in the behavior.

Effect-specific choices that cannot be inferred safely from generic structure are frozen in `automation/interaction-choice-contracts.json`.

Every observed effect kind must appear in that file, including effect kinds with zero additional choices. An unknown effect kind is a blocking `UNMAPPED` interaction, not an implicit no-choice effect.

For library searches, "fail to find" is not a universal default. A search for a stated quality may permit failure to find that quality under rule 701.23b; an unrestricted search such as Long-Term Plans must find a card if the library contains one under rule 701.23d.

## 8. Replay requirement

For every nontrivial player or policy choice, replay must consume the recorded decision rather than rerun strategic policy. Replay evidence must be sufficient to reject missing, added, reordered, or altered decisions and must revalidate legality through the same production rules path.

A Phase C-reachable choice path is not PROVEN until a deterministic test demonstrates fresh-process replay for a scenario that exercises that choice, either directly or through an exact production-seed regression.

## 9. Test requirement

A `CARD_EFFECT` or `GLOBAL_RULE` record reaches `PROVEN` only when evidence includes, as applicable:

- one deterministic positive production-path execution;
- one deterministic negative/atomic legality test for each material invalid-choice family;
- proof that the correct choice timing was used;
- proof that policy received only observation-safe legal candidates when policy is required;
- proof that recorded replay reproduces the choice without rerunning policy; and
- fresh-process replay evidence for Phase C-reachable runtime choices.

A `CARD_COMPOSITION` record requires independent evidence comparing the frozen Oracle record with the complete frozen behavior tuple. A card-name registration test, handler-presence check, broad smoke test, or successful random game cannot satisfy that requirement by itself.

## 10. Deck and project PASS criteria

The interaction coverage gate is PASS only when all of the following are true on one exact commit:

1. exact deck identity remains 98 library cards plus two commanders and 80 unique Oracle-bound card definitions;
2. there is exactly one `CARD_COMPOSITION` guard for each unique card definition;
3. every card record is pinned to the frozen Oracle-record digest and inherited composition inventory used to generate the surface;
4. the generated interaction surface matches the frozen interaction-surface digest;
5. every behavior and nested effect is represented by a stable interaction record;
6. every observed effect kind has an explicit choice classification;
7. no record is `UNMAPPED`, `MAPPED`, or `IMPLEMENTED` in the aggregate proof ledger;
8. every required choice purpose has legality, actor-policy, replay, and deterministic test evidence appropriate to that choice;
9. all `CARD_COMPOSITION` and `GLOBAL_RULE` records are PROVEN;
10. all referenced blocking tests pass with zero skip and zero xfail;
11. no generic/default/fallback choice path can execute for a frozen-deck interaction; and
12. the complete proof report reports `PROVEN == total`, `unproven == 0`, `unproven_composition == 0`, and `unknown_choice_purposes == 0`.

Until those conditions are met, Phase A/Phase B certification may remain valid for its historical scope, but **interaction-proof coverage is not complete**.

## 11. Frozen global-rule interaction classes

The following engine-wide interactions are part of this contract even though they are not owned by one card:

- `GLOBAL-TRIGGER-ORDERING`: simultaneous triggered abilities and the required ordering when more than one controlled trigger is waiting.
- `GLOBAL-REPLACEMENT-ORDERING`: competing replacement/prevention effects and the affected player or relevant permanent's controller choice required by rule 616.1.
- `GLOBAL-COST-PAYMENT`: mana-ability activation sequencing, mana-payment configuration, and cost-payment order under rules 601.2g-h and 602.2b. Multiple legal payment configurations may not be collapsed into an undocumented deterministic engine preference.
- `GLOBAL-CLEANUP-REENTRY`: maximum-hand-size discard selection under rule 514.1, trigger collection, the rule 514.3a priority exception, and complete additional cleanup steps.
- `GLOBAL-COMBAT-ATTACKERS`: the active player explicitly chooses attackers and each attack destination under rules 508.1a-b; restrictions/requirements must be validated and an illegal declaration must roll back rather than partially mutate combat state.
- `GLOBAL-ILLEGAL-ACTION-ROLLBACK`: illegal proposals are atomic and restore the prior state.
- `GLOBAL-SBA-TIMING`: state-based actions occur at rules-defined checkpoints, not during resolution; when the legend rule applies, the controller explicitly chooses the one legendary permanent that remains under rule 704.5j.
- `GLOBAL-COMMANDER-GRAVEYARD-EXILE-RETURN`: under rule 903.9a, the owner explicitly chooses during a state-based-action check whether a commander newly in a graveyard or exile moves to the command zone; the intermediate zone is real and observable.
- `GLOBAL-COMMANDER-HAND-LIBRARY-REPLACEMENT`: under rule 903.9b, the owner explicitly chooses whether the command-zone replacement applies to a commander that would move to its hand or library.
- `GLOBAL-PRIORITY-STACK-LIFO`: the priority holder explicitly chooses a legal action or pass; stack objects resolve last-in/first-out only after the required passes.

These ten records are minimum frozen global coverage. If downstream work discovers another rules interaction that can affect a frozen-deck run, it must be proposed as a coordinator/specification revision; it may not be hidden inside an implementation patch or omitted because no current random seed reaches it.

## 12. Coordinator outputs and downstream change control

This coordinator freeze consists of:

- this contract;
- `automation/interaction-record.schema.json`;
- `automation/interaction-choice-contracts.json`;
- `automation/interaction-coverage-lock.json`;
- `automation/interaction-proof-bundle.schema.json`;
- `scripts/build_interaction_coverage_manifest.py`; and
- `tests/interaction_coverage/test_interaction_coverage_contract.py`.

Downstream agents may implement missing behavior and add proof evidence, but they may not silently alter the coverage unit, timing vocabulary, PASS criteria, or remove interaction records. A change to this contract or to the frozen surface requires a separately reviewed coordinator/specification change with a new surface digest.

### 12.1 Parallel proof bundles

Parallel work begins only after the coordinator surface is frozen. Each downstream agent receives a nonoverlapping assigned set of `record_id` values and the frozen `surface_sha256` and returns an `interaction-proof-bundle-v1` bundle.

The following fields are immutable copies of the frozen surface and may not be changed by downstream proof work:

- `record_id` and `record_class`;
- `card`;
- `effect`;
- `event`;
- `choices`;
- `legality`; and
- `authority`.

A proof agent may populate only `implementation`, `evidence`, and `status`.

The proof aggregator must reject a bundle if its surface SHA differs from the frozen lock; if it contains missing, extra, duplicate, or unassigned records; if any immutable field differs from the frozen record; or if two bundles make conflicting claims for the same record. No merge policy may resolve a specification conflict by choosing one agent's version.

The generated coordinator manifest remains the immutable `MAPPED` baseline. Proof bundles are evidence-bearing overlays/copies tied to that baseline. Only the later aggregate proof ledger may advance records to `IMPLEMENTED` or `PROVEN`.

## 13. Rules authority used for the coordinator freeze

The supplied Comprehensive Rules dated 2026-06-19 establish the key distinctions used here:

- rule 108.1: use the Oracle card reference when determining a card's wording;
- rule 601.2b: spell mode, alternative/additional-cost, X, and hybrid-cost configuration choices during casting;
- rule 601.2c: spell target and variable target-count choices during casting;
- rules 601.2g-h: mana abilities are activated before costs are paid, and the player pays the total cost in a legal order;
- rule 602.2b: activated abilities follow the corresponding casting-choice/payment steps;
- rules 107.4e and 118.3: hybrid mana and mana-payment choices;
- rules 115.1c-d and 603.3d: activated and triggered targets are chosen when those abilities are put on the stack;
- rule 605.3b: an activated mana ability does not use the stack and resolves immediately after activation;
- rule 608.2d: choices not already made as part of casting/activation/stack placement are made while resolving the effect;
- rule 614.12a: a replacement-effect choice that modifies battlefield entry is made before the permanent enters;
- rule 616.1: the affected player or relevant permanent's controller chooses among competing applicable replacement/prevention effects;
- rules 508.1 and 703.4i: declaring attackers is a turn-based action and an illegal declaration is reversed;
- rule 514.1: the active player chooses enough cards to discard to maximum hand size as a turn-based cleanup action;
- rule 514.3a: cleanup SBAs/triggers create the priority exception and then another complete cleanup step;
- rule 704.5j: the controller chooses one same-named legendary permanent to keep;
- rules 903.9a-b: graveyard/exile Commander return is an optional SBA while hand/library Commander movement is an optional replacement effect;
- rules 701.23b and 701.23d: stated-quality searches may fail to find while unrestricted searches must find if possible;
- rules 707.10 and 707.10c: spell copies copy prior decisions and are not cast; new targets may be chosen only when the copying effect permits it; and
- rule 733.1: an illegal action is reversed in its entirety and payments made for it are canceled.
