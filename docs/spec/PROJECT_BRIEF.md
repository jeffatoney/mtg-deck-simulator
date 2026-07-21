# Project brief

## Goal

Build a reproducible simulator that compares legal pilot policies for the exact Malcolm and Breeches deck and measures deterministic table-win access at Turns 5, 6, 8, and 10. Turn 8 is the primary checkpoint.

## Exact deck

- Library: the exact 98 cards in `docs/source/decklist.txt`
- Command zone: Malcolm, Keen-Eyed Navigator and Breeches, Brazen Plunderer

## Fixed baseline game conditions

- Three opponents, each beginning at 40 life
- Normal multiplayer Commander rules unless replaced by the league mulligan rule
- The simulated player draws on Turn 1
- One land play per turn
- Mana empties normally
- Commander tax applies independently to each commander
- Commanders may move to the command zone under normal rules and choices
- Summoning sickness, priority, timing, targeting, state-based actions, and the stack apply normally
- Current Oracle text is frozen before the run
- A deterministic table win must legally eliminate all three opponents
- No blockers
- No opponent interaction
- Opponent wins are not modeled
- Opponent choices required by a card must not be favorable by assumption
- Unknown cards exiled by Breeches are excluded from deterministic calculations
- Simulations continue through the end of the simulated player's Turn 10
- Checkpoints: Turns 5, 6, 8, and 10

## Study structure

- Full study, not yet authorized: 20,000 standard-policy simulations and 5,000 exploratory simulations, reported separately
- Pilot: 500 canonical standard games and 200 exploratory games paired with Standard Games 1–200
- Policy discovery and validation use separate precommitted seed sets
- Exploratory searches use the limits in `EXPLORATORY_SEARCH_LIMITS.md`

## Objective

Maximize legal deterministic table-win access by each checkpoint. Policies must be compared rather than assumed.

## Required interpretations

- Protection in the no-interaction baseline is measured as legal availability with sufficient mana; it is not an estimate of real-world effectiveness.
- Second-line recovery after an opponent removes a combo piece cannot be estimated from the no-interaction baseline. Use a separately reported scripted perturbation or recovery-stress analysis if authorized.
- All required opponent decisions, such as Fact or Fiction pile construction, use the documented adversarial/minimizing choice policy unless a different policy is explicitly approved.
