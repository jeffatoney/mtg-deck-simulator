# Frozen Oracle Snapshot Schema

Phase 1A defines the committed Oracle snapshot shape without fetching live Oracle data.

Snapshot files under `docs/source/oracle/` are frozen inputs once populated by the explicit one-time refresh process. Each card record MUST be derived from the same Oracle export date and MUST include:

- `name`: exact Oracle card name.
- `oracle_id`: Oracle UUID for the card face or object, as supplied by Scryfall bulk data.
- `mana_cost`: printed Oracle mana cost string, or empty string where absent.
- `type_line`: Oracle type line.
- `oracle_text`: Oracle rules text with line breaks preserved.
- `power`: printed power, or null.
- `toughness`: printed toughness, or null.
- `loyalty`: printed loyalty, or null.
- `defense`: printed defense, or null.
- `colors`: ordered list of color symbols.
- `color_identity`: ordered list of Commander color-identity symbols.
- `legalities.commander`: Commander legality value.
- `all_parts`: related face/part names and IDs for split, adventure, modal DFC, and meld cards.
- `source`: source metadata containing `provider`, `bulk_file`, `retrieved_at`, and `sha256`.

No simulator behavior may use live Oracle data. Future refreshes must replace the snapshot in one reviewed commit and update `docs/source/source_inventory.json`.
