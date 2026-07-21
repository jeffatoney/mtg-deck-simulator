Implement the shared rules engine primitives required by this deck. Do not implement all card handlers yet and do not run the pilot.

Scope:

- Legal action generation and a single validator/executor path
- Casting and activating, cost payment, targets, timing, priority, and stack LIFO
- Trigger collection and placement
- State-based actions only at legal checkpoints, never during resolution
- Empty-library draw-attempt loss semantics
- Combat declaration, attacking status, summoning sickness, haste, no blockers
- Damage events, prevention records, opponent elimination, and immediate game termination
- Commander tax and command-zone movement choices
- Mana abilities, colored/generic payment solver, tapped state, tokens, and Treasure
- Copying spells without casting them
- Additional cleanup steps when cleanup triggers occur

Use small fixtures and exact regression tests. Update traceability. Stop and report any rule that cannot be implemented confidently from the frozen sources.
