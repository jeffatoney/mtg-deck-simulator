# Rules acceptance tests

Every test must show PASS/FAIL, cite the relevant rule or frozen Oracle text, and save machine-readable output. Any failure or uncertainty is a no-go for the pilot.

## Original competency tests

- CR-001: Malcolm creates one Treasure for each opponent damaged by one or more Pirates in a damage event.
- CR-002: Multiple Pirates damaging the same opponent simultaneously do not create multiple Treasures for that opponent.
- CR-003: Glint-Horn Buccaneer activates only while attacking.
- CR-004: Glint-Horn does not need to deal combat damage to activate.
- CR-005: Glint-Horn finite sequences track mana, cards in library, cards available to discard, opponent life totals, and opponent count.
- CR-006: Twinflame or Electroduplicate is on the stack before the combo-initiating Dualcaster Mage enters.
- CR-007: The copy spell requires a legal initial creature target.
- CR-008: Dualcaster's trigger can copy the spell and retarget the copy to Dualcaster.
- CR-009: Copied spells are not cast.
- CR-010: Curiosity draws are optional.
- CR-011: Curiosity and Glint-Horn cleanup-step triggers create additional cleanup steps correctly.
- CR-012: Empty-library draw attempts and loss are handled according to EL-001 through EL-007.
- CR-013: Lightning-Rig Crew and Crab Umbra track actual untap cost, Treasure production, opponent count, life totals, and summoning sickness.
- CR-014: Transmute is activated only at sorcery speed.
- CR-015: Drift of Phantasms finds mana value 3.
- CR-016: Muddle the Mixture finds mana value 2.
- CR-017: Dizzy Spell finds mana value 1.
- CR-018: Wizardcycling finds only cards with the Wizard subtype.
- CR-019: Long-Term Plans puts the selected card third from the top.
- CR-020: One tutor cannot count as access to two different cards simultaneously.
- CR-021: Commander tax and command-zone replacement/state-based choices work correctly and are tracked separately for Malcolm and Breeches.
- CR-022: Colored mana payments and tapped-land sequencing are legal.

## Empty-library and Glint-Horn tests

- EL-001: A mandatory draw resolves with an empty library and no lethal damage; the player loses at the next state-based-action check.
- EL-002: An optional Curiosity draw is declined with an empty library; the player does not lose for drawing.
- EL-003: An optional Curiosity draw is accepted with an empty library; the player loses at the next state-based-action check.
- EL-004: A lethal Glint-Horn discard trigger resolves while the activated draw ability remains below it; all opponents lose and the game ends before the draw resolves.
- EL-005: A nonlethal Glint-Horn discard trigger resolves with an empty library; the mandatory draw is attempted and the player loses.
- EL-006: No activation is allowed after the player has lost.
- EL-007: The final lethal Glint-Horn draw is not required to resolve after all opponents have left the game.

## Opponent-dependent Malcolm tests

- OT-001: One Pirate damages all three opponents in one event; three Treasures are created.
- OT-002: Multiple Pirates damage the same opponent simultaneously; one Treasure is created for that opponent.
- OT-003: One Pirate damages two opponents; two Treasures are created.
- OT-004: Damage to one opponent is prevented; no Treasure is created for that opponent.
- OT-005: An opponent already left the game before the event; that player is not counted.
- OT-006: Glint-Horn with three opponents gains one net Treasure per completed nonlethal iteration after funding the next activation from Treasures.
- OT-007: Glint-Horn with two opponents is mana-neutral.
- OT-008: Glint-Horn with one opponent consumes one additional mana per iteration.
- OT-009: Treasure accumulated during earlier three-opponent iterations remains after an opponent leaves.
- OT-010: Lightning-Rig Crew plus Crab Umbra is mana-neutral with three damaged opponents and requires supplemental mana after opponent count decreases.
- OT-011: Simultaneous lethal damage to all remaining opponents ends the game before another activation, untap, or draw is required.
- OT-012: Unequal life totals are processed individually rather than assuming simultaneous elimination.

## Additional required regression and property tests

- PROP-001: Card instances are conserved across zones, except explicitly created tokens and ceased-to-exist tokens.
- PROP-002: Mana balances never become negative and colored requirements cannot be paid by illegal sources.
- PROP-003: No action or resolution occurs after a terminal game state.
- PROP-004: Stack resolution is last-in, first-out, with triggers placed at the correct time.
- PROP-005: State-based actions are not checked during the resolution of a spell or ability.
- PROP-006: A policy cannot access the actual hidden library order or future event stream.
- PROP-007: Replaying the same run manifest produces the same event-log hash regardless of worker count.
- PROP-008: Every card and commander has a unique instance identity, including basic-land copies.
- PROP-009: Every legal tutor consumes the tutor and selects exactly one legal object per resolution.
- PROP-010: Every deck entry has an explicit reviewed coverage status; no unreviewed fallback can run.

## Card-specific boundary tests to include

- Electroduplicate flashback and copied-spell handling
- Niv-Mizzet summoning sickness and Curiosity's optional stop
- Psychosis Crawler life loss is not damage and does not trigger Malcolm or Curiosity
- Simultaneous cleanup discards create the correct number of Glint-Horn triggers and additional cleanup steps
- Izzet Boilerworks can return itself when legal
- Cascade Bluffs filtering requires an initial blue or red mana
- Frostboil Snarl reveal choice and entry status
- Thriving Isle's chosen second color is fixed on entry
- Path of Ancestry scries only for a creature sharing a type with a commander
- Split-card names, face costs, mana values, aftermath, and tutor interactions are correct in each zone
- Breeches triggers are recorded while unknown opponent cards remain unusable for deterministic lines
- Fact or Fiction uses the configured opponent-choice policy rather than a favorable split
