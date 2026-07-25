"""Phase A identity-preserving, fail-closed rules kernel.

Card specifications are data.  All mutation is confined to the services here;
the legacy name/string engine remains isolated and is not a fallback.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
import hashlib
import json
from typing import Any, Protocol


class KernelError(ValueError):
    """An unsupported or illegal kernel operation."""


class Zone(StrEnum):
    LIBRARY = "library"
    HAND = "hand"
    BATTLEFIELD = "battlefield"
    GRAVEYARD = "graveyard"
    EXILE = "exile"
    COMMAND = "command"
    STACK = "stack"
    VOID = "ceased_to_exist"


@dataclass(frozen=True, slots=True)
class CardDefinition:
    definition_id: str
    oracle_id: str
    printed_name: str
    card_types: tuple[str, ...]
    mana_cost: str = ""
    faces: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CardInstance:
    instance_id: str
    definition_id: str
    owner_id: str
    commander: bool = False


@dataclass(slots=True)
class GameObject:
    object_id: str
    source_instance_id: str | None
    owner_id: str
    controller_id: str
    current_zone: Zone
    token: bool = False
    copy: bool = False
    characteristics: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PermanentObject(GameObject):
    tapped: bool = False
    attacking: bool = False
    marked_damage: int = 0
    power: int = 0
    toughness: int = 0


@dataclass(slots=True)
class SpellObject(GameObject):
    face: str | None = None
    targets: tuple[str, ...] = ()
    cast: bool = True


@dataclass(slots=True)
class AbilityObject(GameObject):
    source_object_id: str = ""
    targets: tuple[str, ...] = ()


@dataclass(slots=True)
class TriggeredAbilityObject(AbilityObject):
    trigger_id: str = ""


@dataclass(slots=True)
class ExternalObjectRef:
    object_id: str
    owner_id: str
    controller_id: str
    current_zone: Zone
    object_kind: str
    card_types: tuple[str, ...]
    colors: tuple[str, ...] = ()
    mana_value: int | None = None
    token: bool = False
    copy: bool = False
    commander: bool = False
    targets: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ExternalMove:
    object_id: str
    owner_id: str
    origin: Zone
    destination: Zone
    library_position: int | None
    ceased_to_exist: bool
    remains_in_simulation: bool


@dataclass(frozen=True, slots=True)
class Action:
    kind: str
    source_instance_id: str | None = None
    object_id: str | None = None
    face: str | None = None
    targets: tuple[str, ...] = ()
    modes: tuple[str, ...] = ()
    choices: tuple[str, ...] = ()
    payment: tuple[tuple[str, int], ...] = ()


@dataclass(slots=True)
class KernelState:
    definitions: dict[str, CardDefinition] = field(default_factory=dict)
    instances: dict[str, CardInstance] = field(default_factory=dict)
    objects: dict[str, GameObject] = field(default_factory=dict)
    zones: dict[tuple[str, Zone], list[str]] = field(default_factory=dict)
    stack: list[str] = field(default_factory=list)
    external: dict[str, ExternalObjectRef] = field(default_factory=dict)
    external_ledger: list[ExternalMove] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    actions: list[dict[str, Any]] = field(default_factory=list)
    mana: dict[str, int] = field(default_factory=lambda: {"C": 0, "U": 0, "R": 0})
    life: dict[str, int] = field(default_factory=lambda: {"self": 40, "opp1": 40})
    library_draw_failed: set[str] = field(default_factory=set)
    priority_player: str | None = None
    phase: str = "precombat_main"
    terminal: bool = False
    resolving: bool = False
    commander_casts: dict[str, int] = field(default_factory=dict)
    maximum_hand_size: int = 7

    def state_hash(self) -> str:
        payload = {
            "objects": {k: asdict(v) for k, v in sorted(self.objects.items())},
            "zones": {f"{p}:{z}": v for (p, z), v in sorted(self.zones.items())},
            "stack": self.stack,
            "external": {k: asdict(v) for k, v in sorted(self.external.items())},
            "ledger": [asdict(v) for v in self.external_ledger],
            "mana": self.mana,
            "life": self.life,
            "phase": self.phase,
            "terminal": self.terminal,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


class ReplacementEffect(Protocol):
    def replace(self, obj: GameObject, destination: Zone) -> Zone: ...


class ZoneService:
    """The sole authority for internal and explicitly modeled external moves."""

    def __init__(self, state: KernelState) -> None:
        self.state = state

    def move(
        self,
        object_id: str,
        destination: Zone,
        *,
        position: int | None = None,
        commander_to_command: bool = False,
    ) -> None:
        if object_id in self.state.external:
            self._move_external(object_id, destination, position)
            return
        obj = self.state.objects.get(object_id)
        if obj is None:
            raise KernelError("zone move requires an existing object identity")
        origin = obj.current_zone
        instance = self.state.instances.get(obj.source_instance_id or "")
        if (
            instance
            and instance.commander
            and commander_to_command
            and destination
            in {
                Zone.GRAVEYARD,
                Zone.EXILE,
                Zone.HAND,
                Zone.LIBRARY,
            }
        ):
            destination = Zone.COMMAND
        if (obj.token or obj.copy) and destination not in {Zone.BATTLEFIELD, Zone.STACK, Zone.VOID}:
            destination = Zone.VOID
        self._remove(object_id, obj.owner_id, origin)
        obj.current_zone = destination
        if destination is not Zone.VOID:
            target = self.state.zones.setdefault((obj.owner_id, destination), [])
            if destination is Zone.LIBRARY and position is not None:
                target.insert(min(position, len(target)), object_id)
            else:
                target.append(object_id)
        self.state.events.append(
            {
                "event": "zone_change",
                "object_id": object_id,
                "owner_id": obj.owner_id,
                "origin": origin.value,
                "destination": destination.value,
                "position": position,
            }
        )

    def _remove(self, object_id: str, owner: str, zone: Zone) -> None:
        if zone is Zone.STACK:
            if object_id not in self.state.stack:
                raise KernelError("object is not on stack")
            self.state.stack.remove(object_id)
        entries = self.state.zones.get((owner, zone), [])
        if object_id in entries:
            entries.remove(object_id)

    def _move_external(self, object_id: str, destination: Zone, position: int | None) -> None:
        obj = self.state.external[object_id]
        if destination not in {Zone.LIBRARY, Zone.GRAVEYARD, Zone.EXILE, Zone.HAND, Zone.VOID}:
            raise KernelError("unsupported external owner-zone destination")
        origin = obj.current_zone
        ceased = (obj.token or obj.copy) and destination is not Zone.VOID
        actual = Zone.VOID if ceased else destination
        if origin is Zone.STACK and object_id in self.state.stack:
            self.state.stack.remove(object_id)
        obj.current_zone = actual
        row = ExternalMove(object_id, obj.owner_id, origin, actual, position, ceased, False)
        self.state.external_ledger.append(row)
        self.state.events.append({"event": "external_zone_change", **asdict(row)})


class StateBasedActionService:
    def check_until_stable(self, state: KernelState, zones: ZoneService) -> None:
        if state.resolving:
            raise KernelError("state-based actions cannot occur during resolution")
        changed = True
        while changed:
            changed = False
            for player in tuple(state.library_draw_failed):
                state.life[player] = 0
                state.library_draw_failed.remove(player)
                changed = True
            for obj in tuple(state.objects.values()):
                if isinstance(obj, PermanentObject) and obj.current_zone is Zone.BATTLEFIELD:
                    is_creature = "Creature" in obj.characteristics.get("types", ())
                    if is_creature and (
                        obj.toughness <= 0 or obj.marked_damage >= obj.toughness > 0
                    ):
                        zones.move(obj.object_id, Zone.GRAVEYARD)
                        changed = True
            if state.life.get("self", 1) <= 0 or all(
                life <= 0 for player, life in state.life.items() if player != "self"
            ):
                state.terminal = True
        state.events.append({"event": "state_based_actions_checked"})


class StackPriorityService:
    def __init__(self, state: KernelState, zones: ZoneService) -> None:
        self.state, self.zones = state, zones

    def put(self, obj: SpellObject | AbilityObject) -> None:
        if self.state.terminal or obj.object_id in self.state.stack:
            raise KernelError("stack mutation rejected")
        obj.current_zone = Zone.STACK
        self.state.objects[obj.object_id] = obj
        self.state.stack.append(obj.object_id)
        self.state.events.append(
            {"event": "stack_put", "object_id": obj.object_id, "kind": type(obj).__name__}
        )

    def open_priority(self, player: str = "self") -> None:
        if not self.state.terminal:
            self.state.priority_player = player
            self.state.events.append({"event": "priority", "player": player})

    def pass_priority(self, player: str = "self") -> None:
        if self.state.priority_player != player:
            raise KernelError("player does not have priority")
        self.state.events.append({"event": "priority_pass", "player": player})


class TurnEngine:
    STEPS = (
        "untap",
        "upkeep",
        "draw",
        "precombat_main",
        "begin_combat",
        "declare_attackers",
        "combat_damage",
        "end_combat",
        "postcombat_main",
        "end_step",
        "cleanup",
    )

    def __init__(
        self,
        state: KernelState,
        zones: ZoneService,
        stack: StackPriorityService,
        sba: StateBasedActionService,
    ) -> None:
        self.state, self.zones, self.stack, self.sba = state, zones, stack, sba

    def enter(self, step: str) -> None:
        if step not in self.STEPS or self.state.terminal:
            raise KernelError("invalid turn step")
        self.state.phase = step
        self.state.events.append({"event": "step", "step": step})

    def cleanup(self, player: str = "self") -> None:
        self.enter("cleanup")
        hand = self.state.zones.setdefault((player, Zone.HAND), [])
        grave = Zone.GRAVEYARD
        discarded = 0
        while len(hand) > self.state.maximum_hand_size:
            self.zones.move(hand[-1], grave)
            discarded += 1
        for obj in self.state.objects.values():
            if isinstance(obj, PermanentObject):
                obj.marked_damage = 0
                obj.characteristics.pop("until_end_of_turn", None)
        self.sba.check_until_stable(self.state, self.zones)
        self.state.events.append({"event": "cleanup_complete", "discarded": discarded})


class KernelExecutor:
    """Canonical validator/executor shared by live play and action replay."""

    def __init__(self, state: KernelState) -> None:
        self.state = state
        self.zones = ZoneService(state)
        self.sba = StateBasedActionService()
        self.stack = StackPriorityService(state, self.zones)
        self.turn = TurnEngine(state, self.zones, self.stack, self.sba)

    def execute(self, action: Action, *, record: bool = True) -> None:
        if self.state.terminal:
            raise KernelError("no action after terminal state")
        before = self.state.state_hash()
        self.validate(action)
        if action.kind == "pass_priority":
            self.stack.pass_priority()
        elif action.kind == "play_land":
            assert action.object_id
            self.zones.move(action.object_id, Zone.BATTLEFIELD)
        elif action.kind == "cast":
            self._cast(action)
        elif action.kind == "resolve":
            self._resolve(action)
        elif action.kind == "declare_attacker":
            obj = self.state.objects[action.object_id or ""]
            assert isinstance(obj, PermanentObject)
            obj.attacking = True
            self.state.events.append({"event": "attacker_declared", "object_id": obj.object_id})
        elif action.kind == "cleanup":
            self.turn.cleanup()
        else:
            raise KernelError(f"unsupported action: {action.kind}")
        after = self.state.state_hash()
        if record:
            self.state.actions.append({"action": asdict(action), "before": before, "after": after})

    def validate(self, action: Action) -> None:
        if action.kind == "cast":
            instance = self.state.instances.get(action.source_instance_id or "")
            if instance is None:
                raise KernelError("cast requires a real card instance")
            definition = self.state.definitions[instance.definition_id]
            if definition.printed_name not in MIGRATED_NAMES:
                raise KernelError("card is PENDING_PHASE_B")
            if action.face == "Memory" and action.targets:
                raise KernelError("Memory has zero targets")
            if action.face == "Memory":
                obj = self._object_for_instance(instance.instance_id)
                if obj.current_zone is not Zone.GRAVEYARD:
                    raise KernelError("aftermath requires graveyard")
            if action.face == "Commit" and len(action.targets) != 1:
                raise KernelError("Commit requires exactly one target")
        elif action.kind == "resolve":
            if not self.state.stack or self.state.stack[-1] != action.object_id:
                raise KernelError("only stack top may resolve")

    def _object_for_instance(self, instance_id: str) -> GameObject:
        found = [o for o in self.state.objects.values() if o.source_instance_id == instance_id]
        if len(found) != 1:
            raise KernelError("card instance must map to exactly one current object")
        return found[0]

    def _cast(self, action: Action) -> None:
        assert action.source_instance_id
        card = self._object_for_instance(action.source_instance_id)
        definition = self.state.definitions[
            self.state.instances[action.source_instance_id].definition_id
        ]
        self.zones._remove(card.object_id, card.owner_id, card.current_zone)
        spell = SpellObject(
            card.object_id,
            card.source_instance_id,
            card.owner_id,
            card.controller_id,
            Zone.STACK,
            characteristics={
                "name": action.face or definition.printed_name,
                "types": definition.card_types,
            },
            face=action.face,
            targets=action.targets,
        )
        self.stack.put(spell)
        self.stack.open_priority()

    def _resolve(self, action: Action) -> None:
        obj = self.state.objects[action.object_id or ""]
        assert isinstance(obj, (SpellObject, AbilityObject))
        self.state.resolving = True
        try:
            name = str(obj.characteristics.get("name", ""))
            types = set(obj.characteristics.get("types", ()))
            if name == "Commit":
                target = obj.targets[0]
                if target not in self.state.objects and target not in self.state.external:
                    self.zones.move(obj.object_id, Zone.GRAVEYARD)
                else:
                    self.zones.move(target, Zone.LIBRARY, position=1)
                    self.zones.move(obj.object_id, Zone.GRAVEYARD)
            elif name == "Memory":
                self.zones.move(obj.object_id, Zone.EXILE)
            elif isinstance(obj, TriggeredAbilityObject):
                if obj.targets and obj.targets[0] in self.state.objects:
                    self.zones.move(obj.targets[0], Zone.EXILE)
                self.zones.move(obj.object_id, Zone.VOID)
            elif "Creature" in types or "Artifact" in types:
                permanent = PermanentObject(
                    **{
                        k: getattr(obj, k)
                        for k in (
                            "object_id",
                            "source_instance_id",
                            "owner_id",
                            "controller_id",
                            "current_zone",
                            "token",
                            "copy",
                            "characteristics",
                        )
                    }
                )
                permanent.current_zone = Zone.STACK
                self.state.objects[obj.object_id] = permanent
                self.zones.move(obj.object_id, Zone.BATTLEFIELD)
                if name == "Soul-Guide Lantern":
                    legal = [
                        oid
                        for (owner, zone), ids in self.state.zones.items()
                        if zone is Zone.GRAVEYARD
                        for oid in ids
                    ]
                    trigger = TriggeredAbilityObject(
                        f"trigger:{obj.object_id}",
                        None,
                        obj.owner_id,
                        obj.controller_id,
                        Zone.STACK,
                        characteristics={"name": "Soul-Guide Lantern ETB"},
                        source_object_id=obj.object_id,
                        targets=tuple(legal[:1]),
                        trigger_id="soul_guide_lantern_etb",
                    )
                    self.stack.put(trigger)
            else:
                self.zones.move(
                    obj.object_id,
                    Zone.EXILE if getattr(obj, "face", None) == "Memory" else Zone.GRAVEYARD,
                )
        finally:
            self.state.resolving = False
        self.sba.check_until_stable(self.state, self.zones)
        self.stack.open_priority()


MIGRATED_NAMES = frozenset(
    {
        "Island",
        "Sol Ring",
        "Opt",
        "Abrade",
        "Soul-Guide Lantern",
        "Commit // Memory",
        "Malcolm, Keen-Eyed Navigator",
        "Glint-Horn Buccaneer",
        "Dualcaster Mage",
        "Twinflame",
    }
)


def replay(initial: KernelState, records: list[dict[str, Any]]) -> KernelState:
    executor = KernelExecutor(initial)
    for expected in records:
        if initial.state_hash() != expected["before"]:
            raise KernelError("replay before-hash mismatch")
        executor.execute(Action(**expected["action"]), record=False)
        if initial.state_hash() != expected["after"]:
            raise KernelError("replay after-hash mismatch")
    return initial
