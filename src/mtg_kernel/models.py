"""Typed, card-agnostic state for the deck-scoped clean engine."""

from __future__ import annotations

import hashlib
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
    MANA_ABILITY = "MANA_ABILITY"
    TOKEN_OBJECT = "TOKEN_OBJECT"
    SPELL_COPY = "SPELL_COPY"
    ABILITY_COPY = "ABILITY_COPY"
    EMBLEM = "EMBLEM"
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
    source_version: str
    mana_cost: str
    mana_value: int
    supertypes: tuple[str, ...]
    card_types: tuple[str, ...]
    subtypes: tuple[str, ...]
    colors: tuple[str, ...]
    color_identity: tuple[str, ...]
    keywords: tuple[str, ...]
    power: str | None
    toughness: str | None
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
    authority: str | None = None


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
    copy_target_choice_id: str | None = None
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
    pending_cease: bool = False


@dataclass(frozen=True)
class Action:
    action_id: str
    kind: str
    actor_id: str
    source_object_id: str | None = None
    targets: tuple[TargetRef, ...] = ()
    modes: tuple[str, ...] = ()
    x_value: int = 0
    payments: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Choice:
    choice_id: str
    player_id: str
    kind: str
    selected: Any
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
    counters: dict[str, int]
    marked_damage: int
    attached_to_ref: TargetRef | None


@dataclass
class PlayerState:
    player_id: str
    life: int = 40
    in_game: bool = True
    loss_reasons: list[str] = field(default_factory=list)
    mana_pool: dict[str, int] = field(
        default_factory=lambda: {symbol: 0 for symbol in ("W", "U", "B", "R", "G", "C")}
    )
    land_plays_remaining: int = 1
    maximum_hand_size: int = 7
    failed_draw_count: int = 0


@dataclass
class TurnState:
    active_player_id: str
    number: int = 1
    phase: str = "PRECOMBAT_MAIN"
    step: str = "PRECOMBAT_MAIN"
    priority_holder_id: str | None = None
    consecutive_priority_passes: int = 0
    cleanup_iteration: int = 0
    cleanup_repeat_pending: bool = False


@dataclass
class TerminalState:
    status: str = "ACTIVE"
    winners: list[str] = field(default_factory=list)
    losers: list[str] = field(default_factory=list)
    cause_event_ids: list[str] = field(default_factory=list)


@dataclass
class RNGStreamState:
    domain: str
    draw_count: int = 0
    state_digest: str = ""


def default_rng_streams() -> dict[str, RNGStreamState]:
    domains = {
        "identity": "mtg-v2/identity",
        "shuffle": "mtg-v2/shuffle",
        "policy": "mtg-v2/policy",
    }
    return {
        name: RNGStreamState(domain, 0, hashlib.sha256(domain.encode()).hexdigest())
        for name, domain in domains.items()
    }


def default_allocation() -> dict[str, int]:
    return {
        "object": 0,
        "action": 0,
        "event": 0,
        "zone-change": 0,
        "lki": 0,
        "choice": 0,
        "card": 0,
        "deck-slot": 0,
        "copy-snapshot": 0,
    }


@dataclass
class GameState:
    game_id: str
    players: dict[str, PlayerState]
    turn: TurnState
    schema_version: str = "identity-state-v2.0.0"
    card_specs: dict[str, CardSpec] = field(default_factory=dict)
    deck_slots: dict[str, DeckSlot] = field(default_factory=dict)
    card_instances: dict[str, CardInstance] = field(default_factory=dict)
    objects: dict[str, GameObject] = field(default_factory=dict)
    zones: dict[str, list[str]] = field(default_factory=dict)
    stack: list[str] = field(default_factory=list)
    pending_actions: list[str] = field(default_factory=list)
    actions: list[Action] = field(default_factory=list)
    choices: list[Choice] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    zone_changes: list[ZoneChange] = field(default_factory=list)
    target_records: list[dict[str, Any]] = field(default_factory=list)
    waiting_triggers: list[str] = field(default_factory=list)
    delayed_triggers: list[str] = field(default_factory=list)
    replacement_effects: list[dict[str, Any]] = field(default_factory=list)
    continuous_effects: list[dict[str, Any]] = field(default_factory=list)
    lki_snapshots: dict[str, LKISnapshot] = field(default_factory=dict)
    commander_designations: dict[str, str] = field(default_factory=dict)
    commander_cast_counts: dict[str, int] = field(default_factory=dict)
    commander_damage: dict[str, dict[str, int]] = field(default_factory=dict)
    pending_commander_choices: list[str] = field(default_factory=list)
    external_object_ledger: list[dict[str, Any]] = field(default_factory=list)
    rng_streams: dict[str, RNGStreamState] = field(default_factory=default_rng_streams)
    allocation: dict[str, int] = field(default_factory=default_allocation)
    terminal: TerminalState = field(default_factory=TerminalState)
    replay_commands: list[dict[str, Any]] = field(default_factory=list)
    replay_initial_state: dict[str, Any] | None = None

    def audit_dict(self) -> dict[str, Any]:
        return asdict(self)
