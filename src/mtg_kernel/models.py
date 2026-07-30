"""Typed, card-agnostic state for the deck-scoped clean engine."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class Zone(StrEnum):
    BATTLEFIELD = "BATTLEFIELD"
    STACK = "STACK"
    HAND = "HAND"
    LIBRARY = "LIBRARY"
    GRAVEYARD = "GRAVEYARD"
    EXILE = "EXILE"
    COMMAND = "COMMAND"
    NONE = "NONE"


class ObjectKind(StrEnum):
    CARD_IN_ZONE = "CARD_IN_ZONE"
    SPELL = "SPELL"
    PERMANENT = "PERMANENT"
    TRIGGERED_ABILITY = "TRIGGERED_ABILITY"
    ACTIVATED_ABILITY = "ACTIVATED_ABILITY"
    TOKEN_OBJECT = "TOKEN_OBJECT"
    SPELL_COPY = "SPELL_COPY"
    ABILITY_COPY = "ABILITY_COPY"
    EXTERNAL_PUBLIC_OBJECT = "EXTERNAL_PUBLIC_OBJECT"


class CopyKind(StrEnum):
    NONE = "NONE"
    TOKEN_COPY = "TOKEN_COPY"
    SPELL_COPY = "SPELL_COPY"
    ABILITY_COPY = "ABILITY_COPY"
    PHYSICAL_OBJECT_COPY_EFFECT = "PHYSICAL_OBJECT_COPY_EFFECT"


class ReferenceMode(StrEnum):
    CURRENT_OBJECT_REQUIRED = "CURRENT_OBJECT_REQUIRED"
    LAST_KNOWN_INFORMATION = "LAST_KNOWN_INFORMATION"
    SUCCESSOR_TRACKING = "SUCCESSOR_TRACKING"


@dataclass(frozen=True)
class CardSpec:
    card_spec_id: str
    name: str
    oracle_id: str
    oracle_record_sha256: str
    mana_cost: str
    mana_value: int
    supertypes: tuple[str, ...]
    card_types: tuple[str, ...]
    subtypes: tuple[str, ...]
    oracle_text: str | None
    faces: tuple[dict[str, Any], ...]
    abilities: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class DeckSlot:
    deck_slot_id: str
    card_spec_id: str
    deck_source_position: int


@dataclass
class CardInstance:
    card_instance_id: str
    card_spec_id: str
    deck_slot_id: str
    owner_id: str
    commander_designation: bool = False
    creation_provenance: str = "DECK"


@dataclass(frozen=True)
class TargetRef:
    object_id: str
    mode: ReferenceMode = ReferenceMode.CURRENT_OBJECT_REQUIRED
    capability: str | None = None


@dataclass
class GameObject:
    object_id: str
    object_kind: ObjectKind
    zone: Zone
    owner: str | None
    controller: str | None
    component_card_instance_ids: tuple[str, ...] = ()
    source_object_id: str | None = None
    predecessor_object_id: str | None = None
    created_by_event_id: str | None = None
    copy_kind: CopyKind = CopyKind.NONE
    copied_from_object_id: str | None = None
    copiable_values_snapshot_id: str | None = None
    copy_creation_event_id: str | None = None
    current_characteristics: dict[str, Any] = field(default_factory=dict)
    counters: dict[str, int] = field(default_factory=dict)
    marked_damage: int = 0
    attached_to_ref: TargetRef | None = None
    permanent_status: dict[str, str] | None = None
    nonbattlefield_orientation: str = "NOT_APPLICABLE"
    identity_visible_to: set[str] = field(default_factory=set)
    lki_snapshot_id: str | None = None
    was_cast: bool | None = None
    retired: bool = False
    ceased_to_exist: bool = False


@dataclass(frozen=True)
class Action:
    action_id: str
    kind: str
    actor_id: str
    source_object_id: str | None = None
    targets: tuple[TargetRef, ...] = ()
    modes: tuple[str, ...] = ()
    x_value: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Choice:
    choice_id: str
    player_id: str
    kind: str
    selected: str
    cause_event_id: str


@dataclass(frozen=True)
class Event:
    event_id: str
    kind: str
    cause_action_id: str | None
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ZoneChange:
    zone_change_id: str
    event_id: str
    card_instance_ids: tuple[str, ...]
    from_object_id: str
    to_object_id: str | None
    from_zone: Zone
    to_zone: Zone
    cause: str
    predecessor_relationship: str | None
    commander_choice_id: str | None = None
    external_owner_destination: dict[str, Any] | None = None


@dataclass(frozen=True)
class LKISnapshot:
    lki_snapshot_id: str
    object_id: str
    characteristics: dict[str, Any]
    controller: str | None


@dataclass
class PlayerState:
    player_id: str
    life: int = 40
    in_game: bool = True
    loss_reasons: list[str] = field(default_factory=list)
    mana_pool: dict[str, int] = field(default_factory=dict)
    land_plays_remaining: int = 1
    maximum_hand_size: int = 7
    failed_draw_count: int = 0


@dataclass
class TurnState:
    active_player_id: str
    phase: str = "PRECOMBAT_MAIN"
    step: str = ""
    priority_holder_id: str | None = None
    consecutive_priority_passes: int = 0
    cleanup_iteration: int = 0


@dataclass
class TerminalState:
    status: str = "ACTIVE"
    winners: list[str] = field(default_factory=list)
    losers: list[str] = field(default_factory=list)
    cause_event_ids: list[str] = field(default_factory=list)


@dataclass
class GameState:
    game_id: str
    players: dict[str, PlayerState]
    turn: TurnState
    card_instances: dict[str, CardInstance] = field(default_factory=dict)
    objects: dict[str, GameObject] = field(default_factory=dict)
    zones: dict[str, list[str]] = field(default_factory=dict)
    stack: list[str] = field(default_factory=list)
    actions: list[Action] = field(default_factory=list)
    choices: list[Choice] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    zone_changes: list[ZoneChange] = field(default_factory=list)
    waiting_triggers: list[str] = field(default_factory=list)
    delayed_triggers: list[str] = field(default_factory=list)
    lki_snapshots: dict[str, LKISnapshot] = field(default_factory=dict)
    commander_cast_counts: dict[str, int] = field(default_factory=dict)
    commander_damage: dict[str, dict[str, int]] = field(default_factory=dict)
    pending_commander_choices: list[str] = field(default_factory=list)
    external_object_ledger: list[dict[str, Any]] = field(default_factory=list)
    rng_positions: dict[str, int] = field(
        default_factory=lambda: {"identity": 0, "shuffle": 0, "policy": 0}
    )
    terminal: TerminalState = field(default_factory=TerminalState)

    def public_dict(self) -> dict[str, Any]:
        return asdict(self)
