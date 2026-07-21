Implement only the core domain model, deterministic seed infrastructure, league mulligan procedure, and serialization/replay hashes. Do not implement card-specific effects beyond fixtures and do not run randomized pilot games.

Required work:

- Unique card instances and all relevant zones
- Four-player state with separate opponent life/status
- Command zone and independent commander cast counts
- Turn/phase/step, land-play count, attackers, stack objects, mana pool, and terminal status
- Internal hidden library order and policy-visible Observation that cannot expose it
- Named RNG streams and deterministic paired shuffle schedules for initial hands and every possible mulligan round
- League draw-back-to-seven mulligan with keep decisions made before refill cards are visible
- Typed event log, state hashes, replay skeleton, and invariants for card conservation and no actions after game over

Add unit and property tests. Demonstrate that changing worker count or replaying a manifest does not change the deterministic result of the fixtures. No pilot or policy evaluation.
