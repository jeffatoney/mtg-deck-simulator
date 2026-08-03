"""Exact 98-card library and two-commander construction."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from mtg_cards.full_deck import FULL_DECK_NAMES, RULES_BY_NAME, load_full_deck_specs
from mtg_kernel.engine import GameExecutor
from mtg_kernel.factory import add_card
from mtg_kernel.models import GameObject, GameState, Zone

ROOT = Path(__file__).resolve().parents[2]
DECKLIST = ROOT / "docs/source/decklist.txt"
COMMANDERS = ROOT / "docs/source/commanders.txt"

COMPOSITION_REVIEWED = "REVIEWED_COMPOSITION"
EXECUTION_IMPLEMENTED = "IMPLEMENTED"
EXECUTION_UNVERIFIED = "UNVERIFIED"
# Each entry below has direct exact-deck execution coverage in tests/phase_b.
IMPLEMENTED_CARDS = frozenset(
    {
        "Abrade",
        "Aetherize",
        "Arcane Signet",
        "Ash Barrens",
        "Breeches, Brazen Plunderer",
        "Brotherhood's End",
        "By Force",
        "Cascade Bluffs",
        "Change the Equation",
        "Command Tower",
        "Commit // Memory",
        "Crab Umbra",
        "Curse of the Swine",
        "Dispel",
        "Dizzy Spell",
        "Drift of Phantasms",
        "Dualcaster Mage",
        "Echoing Truth",
        "Electroduplicate",
        "Evolving Wilds",
        "Exotic Orchard",
        "Expedite",
        "Fact or Fiction",
        "Fading Hope",
        "Faithless Looting",
        "Fellwar Stone",
        "Fiery Cannonade",
        "Frantic Search",
        "Frostboil Snarl",
        "Glint-Horn Buccaneer",
        "Impulse",
        "Introduction to Annihilation",
        "Invert // Invent",
        "Island",
        "Izzet Boilerworks",
        "Izzet Signet",
        "Lightning-Rig Crew",
        "Long-Term Plans",
        "Malcolm, Keen-Eyed Navigator",
        "Mind Stone",
        "Mountain",
        "Muddle the Mixture",
        "Negate",
        "Opt",
        "Prismatic Lens",
        "Psychosis Crawler",
        "Ravenform",
        "Rebuild",
        "Resculpt",
        "Scavenger Grounds",
        "Sentinel Totem",
        "Shivan Reef",
        "Siren Stormtamer",
        "Sleight of Hand",
        "Sol Ring",
        "Spectral Sailor",
        "Step Through",
        "Storm Fleet Sprinter",
        "Temple of Epiphany",
        "Terramorphic Expanse",
        "Thriving Isle",
        "Twinflame",
        "Vandalblast",
        "Wash Away",
        "Wily Goblin",
    }
)


@dataclass(frozen=True)
class DeckEntry:
    quantity: int
    name: str
    zone: str


@dataclass(frozen=True)
class CoverageRecord:
    name: str
    oracle_id: str
    composition_status: str
    execution_status: str
    handler_ids: tuple[str, ...]
    source: str


@dataclass(frozen=True)
class DeckPackage:
    library: tuple[DeckEntry, ...]
    commanders: tuple[DeckEntry, ...]
    coverage: tuple[CoverageRecord, ...]

    @property
    def library_count(self) -> int:
        return sum(entry.quantity for entry in self.library)

    @property
    def commander_count(self) -> int:
        return sum(entry.quantity for entry in self.commanders)

    @property
    def physical_card_count(self) -> int:
        return self.library_count + self.commander_count


def _parse_decklist(path: Path, zone: str) -> tuple[DeckEntry, ...]:
    result: list[DeckEntry] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        value = line.strip()
        if not value:
            continue
        if zone == "command":
            result.append(DeckEntry(1, value, zone))
        else:
            quantity_text, name = value.split(" ", 1)
            result.append(DeckEntry(int(quantity_text), name, zone))
    return tuple(result)


def load_exact_deck_package() -> DeckPackage:
    specs = load_full_deck_specs()
    by_name = {spec.name: spec for spec in specs.values()}
    library = _parse_decklist(DECKLIST, "library")
    commanders = _parse_decklist(COMMANDERS, "command")
    requested = {entry.name for entry in (*library, *commanders)}
    if requested != set(FULL_DECK_NAMES):
        raise ValueError(
            f"exact deck and frozen Oracle inventory differ: missing={sorted(set(FULL_DECK_NAMES) - requested)}, "
            f"extra={sorted(requested - set(FULL_DECK_NAMES))}"
        )
    if sum(entry.quantity for entry in library) != 98 or len(commanders) != 2:
        raise ValueError("exact deck must contain 98 library cards and two commanders")
    coverage: list[CoverageRecord] = []
    for name in sorted(requested):
        spec = by_name[name]
        abilities = tuple(RULES_BY_NAME[name])
        if not abilities:
            raise ValueError(f"card has no reviewed behavior composition: {name}")
        handler_ids = tuple(str(value["ability_id"]) for value in abilities)
        execution_status = (
            EXECUTION_IMPLEMENTED if name in IMPLEMENTED_CARDS else EXECUTION_UNVERIFIED
        )
        coverage.append(
            CoverageRecord(
                name,
                spec.oracle_id,
                COMPOSITION_REVIEWED,
                execution_status,
                handler_ids,
                spec.source_version,
            )
        )
    return DeckPackage(library, commanders, tuple(coverage))


def build_exact_game(
    seed: str = "phase-b",
    player_ids: tuple[str, ...] = ("P0", "P1", "P2", "P3"),
) -> tuple[GameState, GameExecutor, dict[str, tuple[GameObject, ...]]]:
    package = load_exact_deck_package()
    specs = {spec.name: spec for spec in load_full_deck_specs().values()}
    from mtg_kernel.models import PlayerState, TurnState

    state = GameState(
        "game",
        {player: PlayerState(player) for player in player_ids},
        TurnState(player_ids[0], priority_holder_id=player_ids[0]),
    )
    executor = GameExecutor(state, seed)
    created: dict[str, list[GameObject]] = {"library": [], "command": []}
    for entry in package.library:
        for _ in range(entry.quantity):
            created["library"].append(
                add_card(executor, specs[entry.name], Zone.LIBRARY, owner="P0")
            )
    for entry in package.commanders:
        created["command"].append(
            add_card(executor, specs[entry.name], Zone.COMMAND, owner="P0", commander=True)
        )
    if len(state.card_instances) != 100 or len(state.deck_slots) != 100:
        raise ValueError("physical deck identity construction failed")
    positions = sorted(slot.deck_source_position for slot in state.deck_slots.values())
    if positions != list(range(100)):
        raise ValueError("deck source positions are not the exact immutable range 0..99")
    return state, executor, {key: tuple(value) for key, value in created.items()}
