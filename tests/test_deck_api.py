from __future__ import annotations

from collections import Counter

from scripts.serve_health_api import build_deck_payload


def test_deck_api_serializes_exact_clean_deck_package() -> None:
    payload = build_deck_payload()

    assert payload["apiVersion"] == "deck-v1"
    assert payload["id"] == "deck-malcolm-breeches"
    assert payload["colorIdentity"] == ["U", "R"]
    assert payload["format"] == "Commander (Partner)"

    cards = payload["cards"]
    commanders = payload["commanders"]
    names = [card["name"] for card in cards]
    counts = Counter(names)

    assert len(cards) == 98
    assert len(commanders) == 2
    assert len(set(names)) == 78
    assert counts["Island"] == 12
    assert counts["Mountain"] == 10
    assert payload["counts"] == {
        "library": 98,
        "commanders": 2,
        "physicalCards": 100,
        "uniqueLibraryNames": 78,
    }
    assert [card["name"] for card in commanders] == [
        "Malcolm, Keen-Eyed Navigator",
        "Breeches, Brazen Plunderer",
    ]


def test_deck_api_uses_stable_unique_physical_ids_and_source_backed_fields() -> None:
    payload = build_deck_payload()
    physical_cards = [*payload["cards"], *payload["commanders"]]
    physical_ids = [card["id"] for card in physical_cards]

    assert len(physical_ids) == 100
    assert len(set(physical_ids)) == 100
    assert all(card["oracleId"] for card in physical_cards)
    assert all("manaValue" in card for card in physical_cards)
    assert all("manaCost" in card for card in physical_cards)
    assert all(card["typeLine"] for card in physical_cards)
    assert all(card["oracleText"] for card in physical_cards)
    assert all(card["roles"] == [] for card in physical_cards)

    source = payload["source"]
    assert source["package"] == "mtg_deck.load_exact_deck_package"
    assert source["decklist"] == "docs/source/decklist.txt"
    assert source["commanders"] == "docs/source/commanders.txt"
    assert source["oracleSourceVersion"].startswith("snapshot-v2:")


def test_deck_api_serializes_split_card_faces_without_paraphrase() -> None:
    payload = build_deck_payload()
    by_name = {card["name"]: card for card in payload["cards"]}

    commit_memory = by_name["Commit // Memory"]
    assert commit_memory["type"] == "Instant"
    assert commit_memory["typeLine"] == "Instant // Sorcery"
    assert commit_memory["manaCost"] == "{3}{U} // {4}{U}{U}"
    assert "Commit — Instant {3}{U}" in commit_memory["oracleText"]
    assert "Memory — Sorcery {4}{U}{U}" in commit_memory["oracleText"]
    assert "Put target spell or nonland permanent" in commit_memory["oracleText"]
    assert "Each player shuffles their hand and graveyard" in commit_memory["oracleText"]


def test_deck_api_contains_no_previous_placeholder_cards() -> None:
    payload = build_deck_payload()
    names = {card["name"] for card in payload["cards"]}
    forbidden = {
        "Dockside Extortionist",
        "Underworld Breach",
        "Brain Freeze",
        "Lion's Eye Diamond",
        "Ragavan, Nimble Pilferer",
        "Deflecting Swat",
        "Rhystic Study",
        "Mystic Remora",
        "Mana Crypt",
        "Hullbreacher",
    }

    assert not names.intersection(forbidden)
