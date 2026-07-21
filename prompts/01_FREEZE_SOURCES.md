Create a focused branch for source intake and reproducibility. Do not implement game logic or run simulations.

Tasks:

- Validate that `docs/source/decklist.txt` contains exactly 98 library cards by quantity and that `docs/source/commanders.txt` contains exactly Malcolm and Breeches.
- Normalize split-card names without changing card identity.
- Create a source inventory with SHA-256 hashes for the rules file, decklist, commanders, and specifications.
- Create a script that validates counts and hashes.
- Create the traceability matrix from `docs/architecture/TRACEABILITY_TEMPLATE.csv` and populate every requirement/test ID currently present.
- Create an Oracle-snapshot schema and a refresh script, but do not silently fetch or update data. Document the one-time explicit refresh process.
- Record unresolved assumptions from `docs/spec/OPEN_DECISIONS.md` as blocking statuses.

Acceptance criteria:

- Source validation is automated and tested.
- No simulation code exists yet.
- The response lists commands actually run and exact results.
