# One-Time Oracle Refresh Process

Phase 1A intentionally does not fetch live Oracle data. The refresh process is documented now and must be run only after explicit approval in a later source-refresh task.

1. Download the selected Scryfall Oracle Cards bulk JSON once in a controlled environment.
2. Record the download URL, retrieval timestamp, byte size, and SHA-256 hash.
3. Filter the bulk data to the exact card names in `docs/source/decklist.txt` and `docs/source/commanders.txt`.
4. Preserve split-card identities exactly as `Commit // Memory` and `Invert // Invent`.
5. Write deterministic UTF-8 JSON under `docs/source/oracle/` using sorted keys and two-space indentation.
6. Run `uv run mtg-sim validate-sources` and `uv run python scripts/check_manifest.py`.
7. Review all diffs and commit the refreshed snapshot and updated source inventory together.

Until a snapshot is populated, Oracle card behavior remains a blocking source dependency for engine implementation.
