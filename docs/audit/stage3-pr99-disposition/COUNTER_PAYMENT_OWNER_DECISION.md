# Stage 3 counter-payment owner decision

Date: 2026-08-22

Status: AUTHORIZED_FOR_STAGE3_BASELINE

## Decision

When the controlled player faces a rules-legal `COUNTER_UNLESS_PAY` or
`COUNTER_UNLESS_PAY_EXILE` resolution choice, production STANDARD selects:

```text
PAY iff contextual_target_value > actual_required_payment × existing_mana_weight
otherwise DECLINE
```

The comparison is strict. A tie selects `DECLINE`.

## Authorized inputs and constants

- Use only the existing `contextual_combo_v1` evaluator.
- Use the existing frozen `mana` weight of `8`.
- Use the actual rules-required payment amount. For Syncopate this is the cast-time X recorded on the resolving counter spell.
- Rules feasibility remains owned exclusively by the shared Stage 2 resource solver. Policy never creates a second feasibility or payment model.
- Policy receives only the public semantic counter-payment request and public observation.

The production chooser must fail closed if it is invoked with a different evaluator ID or a different mana weight.

## Explicit non-goals

Stage 3 does not add any of the following:

- `RESCUE_MANA_WEIGHT` or another resource-value parameter.
- Outcome projection.
- Hypothetical trigger simulation.
- A second resource valuation model.
- Strategic Context.
- REQUIREMENTS_AWARE behavior.
- A change to existing STANDARD priority-action ranking, weights, or tie-breaks.
- A card-name whitelist for counter-payment choices.

## DECLINE approximation

For this Stage 3 baseline, the incremental strategic value assigned to `DECLINE` is
`0`.

This is an explicit approximation, not a claim that every countered destination has
zero strategic consequence. In particular, `COUNTER_UNLESS_PAY_EXILE` sends the
countered spell to exile rather than its graveyard. The destination is therefore
recorded as durable semantic evidence but is not assigned an additional strategic
score by this baseline.

## Durable evidence contract

Each strategic counter-payment choice records at least:

- `choice_kind`.
- `effect_kind`.
- `decision_owner`.
- Public target identity, mana value, card types, and effect kinds.
- `actual_required_payment`.
- Both legal modeled alternatives.
- Shared solver feasibility/result evidence.
- `counter_destination`.
- Contextual target evaluation.
- Frozen mana-weight valuation.
- Computed payment-mana valuation.
- `decline_incremental_value_microunits = 0`.
- Selected semantic outcome.
- Stable reason code.
- Evaluator ID and evaluator digest.
- Decision source and resolution timing.

Numeric policy values are recorded in deterministic microunits rather than floating
point state.

Replay consumes the recorded semantic outcome without rerunning live policy. Fresh
policy recomputation from the same public semantic request must reproduce the same
semantic selection.

## Characterization contract

Stage 3 tests must characterize representative outcomes through the actual frozen
evaluator, rather than reproducing a second hand-written scoring table. The fixtures
include:

- A neutral draw-valued target below the `{2}` payment threshold.
- A neutral interaction-valued target below the `{2}` payment threshold.
- A tutor-valued target above the `{2}` payment threshold.
- A combo-engine-valued target above the `{2}` payment threshold.
- A real combo-component example where contextual combo progress changes the target value.
- An exact-value tie that proves `DECLINE` wins ties.
- Syncopate with more than one X value, proving the payment valuation uses cast-time X.

## Intended successor, not implemented in Stage 3

The intended future model is symmetric complete-outcome comparison:

```text
compare value(PAY outcome) with value(DECLINE outcome)
```

That future model may use Strategic Context to value colored/generic deficits,
package requirements, protection resources, destination consequences, and changes to
earliest projected access. It is explicitly not implemented by this Stage 3 decision.

The current baseline is named and versioned so that a future requirements-aware model
can supersede it without changing the rules-side PAY/DECLINE legality, execution, or
replay boundary.