Implement the exact deck in reviewed batches using the frozen Oracle snapshot. Do not run policy discovery or the pilot.

Requirements:

- Build reusable primitives for lands, mana rocks, draw/filter/loot, tutors, cycling/transmute, bounce/phasing, counters/removal, copying, flashback/aftermath, and damage/life-loss effects.
- Add bespoke handlers for Malcolm, Breeches, Glint-Horn Buccaneer, Dualcaster Mage, Twinflame, Electroduplicate, Curiosity, Niv-Mizzet, Lightning-Rig Crew, Crab Umbra, Psychosis Crawler, Long-Term Plans, split cards, and any other rules-heavy card.
- Implement all legal self-targeting or self-affecting modes that can matter in the baseline or exploratory search.
- Unknown Breeches cards must remain excluded.
- Opponent permanents must not be invented.
- Opponent choices must use the configured minimizing policy.
- Every card and commander must receive an explicit coverage status and tests.
- The engine must refuse a pilot if any entry is missing, blocked, or using an unreviewed fallback.

Work in several focused commits or PRs if needed. Produce `card_coverage.csv` and update the traceability matrix.
