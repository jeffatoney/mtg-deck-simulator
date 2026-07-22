"""Phase 3 core domain model for deterministic Malcolm/Breeches simulations."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, Mapping, Sequence

COMMANDERS = ("Malcolm, Keen-Eyed Navigator", "Breeches, Brazen Plunderer")
MANA_COLORS = ("C", "W", "U", "B", "R", "G")


class DomainError(ValueError):
    """Raised when a core-domain invariant or transition is invalid."""


class Zone(str, Enum):
    LIBRARY = "library"
    HAND = "hand"
    BATTLEFIELD = "battlefield"
    GRAVEYARD = "graveyard"
    EXILE = "exile"
    COMMAND = "command_zone"
    STACK = "stack"


class Phase(str, Enum):
    BEGINNING = "beginning"
    PRECOMBAT_MAIN = "precombat_main"
    COMBAT = "combat"
    POSTCOMBAT_MAIN = "postcombat_main"
    ENDING = "ending"


class Step(str, Enum):
    UNTAP = "untap"
    UPKEEP = "upkeep"
    DRAW = "draw"
    MAIN = "main"
    BEGIN_COMBAT = "begin_combat"
    DECLARE_ATTACKERS = "declare_attackers"
    COMBAT_DAMAGE = "combat_damage"
    END = "end"
    CLEANUP = "cleanup"


class TerminalStatus(str, Enum):
    ONGOING = "ongoing"
    WON = "won"
    LOST = "lost"
    DRAW = "draw"


@dataclass(frozen=True, slots=True, order=True)
class CardInstanceId:
    """Unique identity for one physical card in this deck."""

    value: str


@dataclass(frozen=True, slots=True)
class CardInstance:
    id: CardInstanceId
    name: str
    is_commander: bool = False


@dataclass(slots=True)
class CardStatus:
    tapped: bool = False
    attacking: bool = False
    attacked_player: int | None = None


@dataclass(slots=True)
class PlayerState:
    player_id: int
    life: int = 40
    eliminated: bool = False
    is_simulated: bool = False


@dataclass(frozen=True, slots=True)
class StackObject:
    object_id: str
    source: CardInstanceId | None
    name: str
    controller: int
    kind: Literal["spell", "ability", "trigger", "copy", "fixture"]
    targets: tuple[CardInstanceId | int, ...] = ()
    cast: bool = False


@dataclass(frozen=True, slots=True)
class Event:
    sequence: int
    event_type: str
    payload: Mapping[str, Any]
    before_hash: str
    after_hash: str

    def canonical(self) -> dict[str, Any]:
        return {
            "after_hash": self.after_hash,
            "before_hash": self.before_hash,
            "event_type": self.event_type,
            "payload": dict(self.payload),
            "sequence": self.sequence,
        }


@dataclass(frozen=True, slots=True)
class Observation:
    """Policy-visible state. It intentionally contains no ordered library or RNG state."""

    hand: tuple[tuple[str, str], ...]
    battlefield: tuple[tuple[str, str, bool, bool], ...]
    graveyard_names: tuple[str, ...]
    exile_names: tuple[str, ...]
    command_zone_names: tuple[str, ...]
    stack: tuple[tuple[str, str], ...]
    players: tuple[tuple[int, int, bool], ...]
    turn: int
    phase: Phase
    step: Step
    land_plays_this_turn: int
    commander_cast_counts: Mapping[str, int]
    terminal_status: TerminalStatus
    library_size: int
    known_top_library: tuple[()] = ()


@dataclass(slots=True)
class GameState:
    cards: dict[CardInstanceId, CardInstance]
    zones: dict[Zone, list[CardInstanceId]]
    players: list[PlayerState] = field(
        default_factory=lambda: [
            PlayerState(0, is_simulated=True),
            PlayerState(1),
            PlayerState(2),
            PlayerState(3),
        ]
    )
    card_status: dict[CardInstanceId, CardStatus] = field(default_factory=dict)
    stack_objects: list[StackObject] = field(default_factory=list)
    mana_pool: dict[str, int] = field(default_factory=lambda: {c: 0 for c in MANA_COLORS})
    commander_cast_counts: dict[str, int] = field(
        default_factory=lambda: {name: 0 for name in COMMANDERS}
    )
    turn: int = 1
    phase: Phase = Phase.PRECOMBAT_MAIN
    step: Step = Step.MAIN
    land_plays_this_turn: int = 0
    terminal_status: TerminalStatus = TerminalStatus.ONGOING
    events: list[Event] = field(default_factory=list)

    def observation(self) -> Observation:
        def zone_names(zone: Zone) -> tuple[str, ...]:
            return tuple(self.cards[cid].name for cid in self.zones[zone])

        return Observation(
            hand=tuple((cid.value, self.cards[cid].name) for cid in self.zones[Zone.HAND]),
            battlefield=tuple(
                (
                    cid.value,
                    self.cards[cid].name,
                    self.card_status.setdefault(cid, CardStatus()).tapped,
                    self.card_status.setdefault(cid, CardStatus()).attacking,
                )
                for cid in self.zones[Zone.BATTLEFIELD]
            ),
            graveyard_names=zone_names(Zone.GRAVEYARD),
            exile_names=zone_names(Zone.EXILE),
            command_zone_names=zone_names(Zone.COMMAND),
            stack=tuple((obj.object_id, obj.name) for obj in self.stack_objects),
            players=tuple((p.player_id, p.life, p.eliminated) for p in self.players),
            turn=self.turn,
            phase=self.phase,
            step=self.step,
            land_plays_this_turn=self.land_plays_this_turn,
            commander_cast_counts=MappingProxyType(dict(self.commander_cast_counts)),
            terminal_status=self.terminal_status,
            library_size=len(self.zones[Zone.LIBRARY]),
        )

    def state_hash(self) -> str:
        payload = {
            "cards": {cid.value: self.cards[cid].name for cid in sorted(self.cards)},
            "zones": {z.value: [cid.value for cid in self.zones[z]] for z in Zone},
            "players": [(p.player_id, p.life, p.eliminated, p.is_simulated) for p in self.players],
            "status": {cid.value: vars(st) for cid, st in sorted(self.card_status.items())},
            "stack": [
                obj.__dict__ | {"source": None if obj.source is None else obj.source.value}
                for obj in self.stack_objects
            ],
            "mana": self.mana_pool,
            "commanders": self.commander_cast_counts,
            "turn": self.turn,
            "phase": self.phase.value,
            "step": self.step.value,
            "lands": self.land_plays_this_turn,
            "terminal": self.terminal_status.value,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()

    def record(self, event_type: str, payload: Mapping[str, Any], before_hash: str) -> Event:
        event = Event(len(self.events), event_type, payload, before_hash, self.state_hash())
        self.events.append(event)
        return event

    def assert_not_terminal(self) -> None:
        if self.terminal_status is not TerminalStatus.ONGOING:
            raise DomainError("no action may occur after terminal game state")

    def validate_invariants(self) -> None:
        seen: list[CardInstanceId] = []
        for zone in Zone:
            seen.extend(self.zones[zone])
        if len(seen) != len(self.cards) or set(seen) != set(self.cards):
            raise DomainError("card conservation failed")
        if len(seen) != len(set(seen)):
            raise DomainError("duplicate physical card detected")
        if any(amount < 0 for amount in self.mana_pool.values()):
            raise DomainError("negative mana pool")

    def move_card(self, card_id: CardInstanceId, source: Zone, dest: Zone, reason: str) -> Event:
        self.assert_not_terminal()
        before = self.state_hash()
        if card_id not in self.zones[source]:
            raise DomainError(f"{card_id.value} is not in {source.value}")
        self.zones[source].remove(card_id)
        self.zones[dest].append(card_id)
        self.validate_invariants()
        return self.record(
            "move_card",
            {
                "card_id": card_id.value,
                "source": source.value,
                "dest": dest.value,
                "reason": reason,
            },
            before,
        )

    def terminate(self, status: TerminalStatus, reason: str) -> Event:
        self.assert_not_terminal()
        before = self.state_hash()
        self.terminal_status = status
        return self.record("terminal", {"status": status.value, "reason": reason}, before)


def read_decklist(path: Path = Path("docs/source/decklist.txt")) -> list[str]:
    cards: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        count_text, name = line.split(" ", 1)
        cards.extend([name] * int(count_text))
    return cards


def new_game(deck_names: Sequence[str], *, library_order: Sequence[str] | None = None) -> GameState:
    cards: dict[CardInstanceId, CardInstance] = {}
    library: list[CardInstanceId] = []
    counters: dict[str, int] = {}
    ordered = list(library_order or deck_names)
    for name in ordered:
        counters[name] = counters.get(name, 0) + 1
        cid = CardInstanceId(f"deck:{name}:{counters[name]:02d}")
        cards[cid] = CardInstance(cid, name)
        library.append(cid)
    command: list[CardInstanceId] = []
    for name in COMMANDERS:
        cid = CardInstanceId(f"commander:{name}")
        cards[cid] = CardInstance(cid, name, is_commander=True)
        command.append(cid)
    state = GameState(cards=cards, zones={zone: [] for zone in Zone})
    state.zones[Zone.LIBRARY] = library
    state.zones[Zone.COMMAND] = command
    state.validate_invariants()
    return state
