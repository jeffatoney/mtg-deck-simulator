# ADR 0017: Model both legal controlled-player counter-payment outcomes

## Status

Accepted by explicit owner study-design decision on 2026-08-15.

Owner decision identifier:

`MODEL_BOTH_LEGAL_CONTROLLED_PLAYER_OUTCOMES`

## Decision

When a `COUNTER_UNLESS_PAY` or `COUNTER_UNLESS_PAY_EXILE` effect resolves and the controlled player controls the targeted spell:

- `PAY` and `DECLINE` are separate modeled choices whenever both are legally available;
- only `DECLINE` is exposed when payment is legally impossible;
- the policy may not always force decline;
- an otherwise legal self-targeting counter line is not removed merely to avoid the choice;
- the public-state policy compares the legal outcomes under the frozen objective of maximizing legal deterministic table-win access; and
- the selected outcome, legal alternatives, payment amount, public mana state, reason code, replay binding, and result binding are durable evidence.

This is a strategic-choice decision, not a card-specific exception and not a diagnostic-seed workaround.

## Rules process for payment during resolution

The Comprehensive Rules source frozen for the project permits mana abilities to be activated while resolving a spell or ability when a player is asked to make a mana payment. The implementation therefore may not declare `PAY` unavailable merely because the required mana is not already in the player's mana pool.

The kernel performs a bounded, deterministic search over rules-declared mana abilities controlled by the payer. The search uses request-scoped public source handles, validates each activation through the production executor, and returns the canonical shortest legal payment plan. The plan is executed during resolution without granting priority and without putting the mana ability on the stack. If the bounded search cannot prove feasibility or impossibility within its supported rules surface, it fails closed as an unsupported capability rather than silently removing `PAY`.

The actual payment still uses the shared mana-payment validator after the selected mana-ability plan has resolved.

## Opponent boundary

The injected Phase C policy controls P0 only. If an unmodeled opponent controls the spell that is being asked to pay, the policy does not invent that opponent's decision. The engine requires an explicit rules choice or fails closed as unsupported.

## Policy comparison

The STANDARD strategic provider evaluates the public target spell contextually with the frozen evaluator and compares preservation of that spell against the existing evaluator value of the required mana. V2 may explore either legal outcome through the same directed-selection machinery and must persist its candidate evidence. No hidden object identity, library order, or opaque action capability may enter that comparison.

## Replay and evidence

A provider-driven payment choice is recorded as `counter-payment-choice-v2`, including:

- resolution-choice ID;
- parent priority-decision ID when the counter action came from a V2 priority decision;
- effect kind and decision owner;
- public target handle and identity;
- payment amount and legal modeled alternatives;
- whether `PAY` was legally available;
- selected outcome;
- public mana state before the choice;
- rules-validated mana-ability plan;
- actual payment;
- stable reason code;
- randomness flag;
- resulting public-state digest;
- evaluator identity;
- replay binding; and
- provider diagnostics.

Fresh replay consumes the recorded strategic choice rather than rerunning the live policy. Fresh-process policy recomputation separately proves that the frozen policy and exploration seed reproduce the same decision evidence.

## Certification consequence

This work changes Phase A-covered engine behavior as well as Phase B policy/run behavior. Both Phase A and Phase B certification cycles are therefore mandatory before replacement diagnostic evidence can become final closeout evidence.
