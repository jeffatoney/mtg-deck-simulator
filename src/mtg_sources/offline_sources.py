"""Typed loaders for the committed offline Scryfall snapshot.

These loaders are intentionally fail-closed: callers get structured data only when the
exact decklist, normalized snapshot, and behavior declarations agree by card name,
set code, collector number, quantities, commanders, and recorded hashes.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import re
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[2]
DECK_PATH = ROOT / "deck" / "exact_decklist.txt"
SNAPSHOT_PATH = ROOT / "offline_snapshot" / "normalized" / "cards_snapshot.json"
METADATA_PATH = ROOT / "offline_snapshot" / "raw" / "snapshot_metadata.json"
REPORT_PATH = ROOT / "offline_snapshot" / "reports" / "snapshot_validation_report.json"
DATA_BEHAVIORS_PATH = ROOT / "data" / "simulation" / "card_behaviors.json"
SNAPSHOT_BEHAVIORS_PATH = ROOT / "offline_snapshot" / "simulation" / "card_behaviors.json"
COMMANDERS = ("Malcolm, Keen-Eyed Navigator", "Breeches, Brazen Plunderer")
DECK_RE = re.compile(
    r"^(?P<quantity>\d+) (?P<name>.+) \((?P<set>[A-Z0-9]+)\) (?P<collector>\S+)"
    r"(?P<commander> \*CMDR\*)?$"
)


class OfflineSourceError(ValueError):
    """Raised when committed offline sources fail a correctness gate."""


@dataclass(frozen=True, slots=True)
class DeckEntry:
    quantity: int
    name: str
    set_code: str
    collector_number: str
    is_commander: bool
    source_line: int


@dataclass(frozen=True, slots=True)
class CardFace:
    name: str
    mana_cost: str | None
    type_line: str | None
    oracle_text: str | None
    power: str | None = None
    toughness: str | None = None


@dataclass(frozen=True, slots=True)
class CardSnapshot:
    deck_quantity: int
    is_commander: bool
    name: str
    set_code: str
    collector_number: str
    layout: str
    mana_cost: str | None
    mana_value: float | None
    colors: tuple[str, ...]
    color_identity: tuple[str, ...]
    type_line: str
    oracle_text: str | None
    faces: tuple[CardFace, ...]


@dataclass(frozen=True, slots=True)
class BehaviorDeclaration:
    name: str
    set_code: str
    collector_number: str
    implementation: str
    version: int
    roles: tuple[str, ...]
    declaration_status: str
    rules_test_status: str


@dataclass(frozen=True, slots=True)
class SimulationCard:
    name: str
    set_code: str
    collector_number: str
    copy_index: int
    snapshot: CardSnapshot
    behavior: BehaviorDeclaration


@dataclass(frozen=True, slots=True)
class LoadedDeck:
    deck_entries: tuple[DeckEntry, ...]
    commanders: tuple[DeckEntry, DeckEntry]
    library: tuple[SimulationCard, ...]


def _read_json(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise OfflineSourceError(f"{path} must contain a JSON object")
    return value


def file_sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def load_exact_decklist(path: Path = DECK_PATH) -> tuple[DeckEntry, ...]:
    entries: list[DeckEntry] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        match = DECK_RE.match(line)
        if match is None:
            raise OfflineSourceError(f"malformed exact decklist line {line_number}: {raw_line!r}")
        quantity = int(match.group("quantity"))
        if quantity < 1:
            raise OfflineSourceError(f"decklist quantity must be positive on line {line_number}")
        entries.append(
            DeckEntry(
                quantity=quantity,
                name=match.group("name"),
                set_code=match.group("set").lower(),
                collector_number=match.group("collector"),
                is_commander=match.group("commander") is not None,
                source_line=line_number,
            )
        )
    return tuple(entries)


def _face_from_mapping(face: Mapping[str, Any]) -> CardFace:
    return CardFace(
        name=str(face["name"]),
        mana_cost=face.get("mana_cost"),
        type_line=face.get("type_line"),
        oracle_text=face.get("oracle_text"),
        power=face.get("power"),
        toughness=face.get("toughness"),
    )


def load_normalized_snapshot(path: Path = SNAPSHOT_PATH) -> tuple[CardSnapshot, ...]:
    payload = _read_json(path)
    cards = payload.get("cards")
    if not isinstance(cards, list):
        raise OfflineSourceError("normalized snapshot must contain a cards array")
    snapshots: list[CardSnapshot] = []
    for card in cards:
        if not isinstance(card, dict):
            raise OfflineSourceError("normalized card entries must be objects")
        raw_faces = card.get("card_faces") or []
        faces = tuple(_face_from_mapping(face) for face in raw_faces if isinstance(face, dict))
        snapshots.append(
            CardSnapshot(
                deck_quantity=int(card["deck_quantity"]),
                is_commander=bool(card["is_commander"]),
                name=str(card["name"]),
                set_code=str(card["set"]).lower(),
                collector_number=str(card["collector_number"]),
                layout=str(card["layout"]),
                mana_cost=card.get("mana_cost"),
                mana_value=card.get("mana_value"),
                colors=tuple(card.get("colors") or ()),
                color_identity=tuple(card.get("color_identity") or ()),
                type_line=str(card["type_line"]),
                oracle_text=card.get("oracle_text"),
                faces=faces,
            )
        )
    return tuple(snapshots)


def load_behavior_registry(path: Path = DATA_BEHAVIORS_PATH) -> tuple[BehaviorDeclaration, ...]:
    payload = _read_json(path)
    registry = payload.get("behavior_registry")
    if not isinstance(registry, list):
        raise OfflineSourceError("behavior registry must contain a behavior_registry array")
    declarations: list[BehaviorDeclaration] = []
    for entry in registry:
        if not isinstance(entry, dict):
            raise OfflineSourceError("behavior registry entries must be objects")
        declarations.append(
            BehaviorDeclaration(
                name=str(entry["name"]),
                set_code=str(entry["set"]).lower(),
                collector_number=str(entry["collector_number"]),
                implementation=str(entry["implementation"]),
                version=int(entry["version"]),
                roles=tuple(entry.get("roles") or ()),
                declaration_status=str(entry["declaration_status"]),
                rules_test_status=str(entry["rules_test_status"]),
            )
        )
    return tuple(declarations)


def build_simulation_deck() -> LoadedDeck:
    entries = load_exact_decklist()
    snapshots = {(c.name, c.set_code, c.collector_number): c for c in load_normalized_snapshot()}
    behaviors = {(b.name, b.set_code, b.collector_number): b for b in load_behavior_registry()}
    commanders = tuple(entry for entry in entries if entry.is_commander)
    if sum(entry.quantity for entry in entries) != 100:
        raise OfflineSourceError("exact decklist must contain exactly 100 total cards")
    if tuple(entry.name for entry in commanders) != COMMANDERS:
        raise OfflineSourceError("decklist must mark Malcolm and Breeches as the two commanders")
    library: list[SimulationCard] = []
    for entry in entries:
        key = (entry.name, entry.set_code, entry.collector_number)
        snapshot = snapshots.get(key)
        if snapshot is None:
            raise OfflineSourceError(f"missing normalized snapshot card: {key}")
        behavior = behaviors.get(key)
        if behavior is None:
            raise OfflineSourceError(f"missing behavior declaration: {key}")
        if snapshot.deck_quantity != entry.quantity or snapshot.is_commander != entry.is_commander:
            raise OfflineSourceError(f"snapshot/deck quantity or commander mismatch: {key}")
        if entry.is_commander:
            continue
        for copy_index in range(1, entry.quantity + 1):
            library.append(
                SimulationCard(
                    entry.name,
                    entry.set_code,
                    entry.collector_number,
                    copy_index,
                    snapshot,
                    behavior,
                )
            )
    if len(library) != 98:
        raise OfflineSourceError("simulation library must contain exactly 98 cards")
    return LoadedDeck(entries, commanders, tuple(library))  # type: ignore[arg-type]


def audit_offline_snapshot() -> dict[str, Any]:
    deck = build_simulation_deck()
    entries = load_exact_decklist()
    snapshots = load_normalized_snapshot()
    metadata = _read_json(METADATA_PATH)
    report = _read_json(REPORT_PATH)
    data_behaviors = DATA_BEHAVIORS_PATH.read_bytes()
    snapshot_behaviors = SNAPSHOT_BEHAVIORS_PATH.read_bytes()
    exact_snapshot_hash = file_sha256(
        ROOT / "offline_snapshot" / "raw" / "scryfall_exact_printings_snapshot.json"
    )
    return {
        "deck_total": sum(entry.quantity for entry in entries),
        "commanders": [entry.name for entry in deck.commanders],
        "library_total": len(deck.library),
        "exact_printings": len(snapshots),
        "exact_printings_expected": metadata.get("exact_entries_expected"),
        "exact_printings_resolved": metadata.get("exact_entries_resolved"),
        "card_data_status": report.get("card_data_status"),
        "exact_printing_validation_passed": report.get("exact_printing_validation_passed"),
        "deck_hash_matches_metadata": file_sha256(DECK_PATH) == metadata.get("deck_sha256"),
        "exact_snapshot_hash_matches_metadata": exact_snapshot_hash
        == metadata.get("exact_snapshot_sha256"),
        "behavior_files_identical": data_behaviors == snapshot_behaviors,
        "rules_engine_tests_status": report.get("rules_engine_tests_status"),
        "pilot_allowed_under_original_requirements": report.get(
            "pilot_allowed_under_original_requirements"
        ),
    }
