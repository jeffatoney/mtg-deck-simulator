# Lovable Deck API Boundary

## Purpose

`GET /api/deck` is the second read-only network boundary between the Lovable cockpit and the Python simulator repository. It exposes the exact Malcolm and Breeches deck through the clean deck package rather than duplicating deck truth in the web layer.

This route must not create a game, execute Magic rules, run a policy, run search, or start any simulation study.

## Authority

The endpoint calls:

- `mtg_deck.load_exact_deck_package()` for the 98-card library, two commanders, exact-name validation, and reviewed coverage inventory;
- `mtg_cards.full_deck.load_full_deck_specs()` for frozen-Oracle-backed display data.

`load_exact_deck_package()` already fails if the exact deck and frozen Oracle inventory differ or if the physical deck is not exactly 98 library cards plus two commanders. The API serializes that validated package; it does not maintain a second deck list.

## Response contract

`GET /api/deck` returns `apiVersion: deck-v1` plus the existing Lovable deck shape:

- deck id, name, format, and commander color identity;
- exactly two commander records;
- exactly 98 expanded physical library-card records;
- stable unique physical IDs;
- frozen Oracle ID, mana cost, mana value, colors, type line, and Oracle text;
- empty `roles` arrays because subjective role tags are not part of the source-of-truth repository data.

Split cards use their frozen face records to build display type lines and display Oracle text. The API does not paraphrase face text.

Additional `counts` and `source` metadata make provenance and basic invariants visible to clients.

## Failure behavior

Deck serialization is lazy. `/api/health` does not import or initialize the clean deck/rules packages.

If the clean deck package cannot load or its invariants fail, `/api/deck` returns HTTP 503 with a compact `unavailable` response. `/api/health` remains independently usable.

## Render deployment

The health-only service originally required no project installation. `/api/deck` imports the installed clean packages, so the Render service must install the local project during build.

Recommended Render build command:

```bash
pip install --no-deps .
```

The deck serialization import path uses only repository packages and Python-standard-library dependencies. The existing start command remains:

```bash
python scripts/serve_health_api.py
```

The existing `/healthz` health-check path remains valid.

## Lovable migration

The Lovable service boundary should migrate `getDeck()` to `GET /api/deck` only after the deployed endpoint is verified.

During the transition, the current source-backed static deck fixture may remain as a fail-closed/read-only availability fallback. If fallback is used, the UI must identify that the live deck API was unavailable; it must not silently claim the static fallback came from the live backend.

Simulation results, replay, and deck comparisons remain mock until separately migrated.
