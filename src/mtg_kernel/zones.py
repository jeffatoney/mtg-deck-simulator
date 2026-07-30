"""The only authoritative zone mutation and synthetic-cessation service."""

from __future__ import annotations

from typing import Any

from mtg_kernel.errors import IllegalAction
from mtg_kernel.identity import IdentityService
from mtg_kernel.models import (
    CopyKind,
    Event,
    GameObject,
    GameState,
    ObjectKind,
    Zone,
    ZoneChange,
)
from mtg_kernel.specs import base_characteristics, default_visibility

SHARED_ZONES = {Zone.BATTLEFIELD, Zone.STACK, Zone.NONE}
SYNTHETIC_COPY_KINDS = {CopyKind.TOKEN_COPY, CopyKind.SPELL_COPY, CopyKind.ABILITY_COPY}
SYNTHETIC_OBJECT_KINDS = {
    ObjectKind.TRIGGERED_ABILITY,
    ObjectKind.ACTIVATED_ABILITY,
    ObjectKind.MANA_ABILITY,
    ObjectKind.ABILITY_COPY,
    ObjectKind.SPELL_COPY,
    ObjectKind.TOKEN_OBJECT,
}


class ZoneService:
    def __init__(self, state: GameState, identity: IdentityService) -> None:
        self.state, self.identity = state, identity

    @staticmethod
    def zone_key(zone: Zone, owner: str | None) -> str:
        if zone in SHARED_ZONES:
            return f"{zone.value}:shared"
        return f"{zone.value}:{owner or 'ownerless'}"

    def register(self, obj: GameObject) -> None:
        key = self.zone_key(obj.zone, obj.owner)
        self.state.zones.setdefault(key, []).append(obj.object_id)
        if obj.zone is Zone.STACK:
            self.state.stack.append(obj.object_id)
        self.identity.validate_object_schema()

    def _remove_from_zone(self, obj: GameObject) -> None:
        key = self.zone_key(obj.zone, obj.owner)
        if obj.object_id in self.state.zones.get(key, []):
            self.state.zones[key].remove(obj.object_id)
        if obj.object_id in self.state.stack:
            self.state.stack.remove(obj.object_id)

    def _physical_characteristics(self, old: GameObject, face: int | None) -> dict[str, object]:
        if not old.component_card_instance_ids:
            raise IllegalAction("physical successor requires a card component")
        instance = self.state.card_instances[old.component_card_instance_ids[0]]
        spec = self.state.card_specs[instance.card_spec_id]
        return base_characteristics(spec, face)

    def move(
        self,
        object_id: str,
        destination: Zone,
        cause: str,
        event: Event,
        *,
        object_kind: ObjectKind | None = None,
        controller: str | None = None,
        face: int | None = None,
        explicit_characteristics: dict[str, Any] | None = None,
        commander_choice_id: str | None = None,
    ) -> GameObject | None:
        old = self.state.objects[object_id]
        if old.retired or old.ceased_to_exist:
            raise IllegalAction("cannot move a retired object")
        self._remove_from_zone(old)
        self.identity.snapshot_lki(old)
        old.retired = True

        external_leaves_model = old.object_kind is ObjectKind.EXTERNAL_PUBLIC_OBJECT
        successor: GameObject | None = None
        external_record: dict[str, Any] | None = None
        if external_leaves_model:
            external_record = {
                "object_id": old.object_id,
                "owner": old.owner,
                "destination": destination.value,
                "position": "SECOND_FROM_TOP" if cause == "COMMIT" else "UNSPECIFIED",
                "cessation": "LEFT_MODELED_BOUNDARY",
            }
            self.state.external_object_ledger.append(external_record)
        else:
            is_synthetic = not old.component_card_instance_ids or old.copy_kind in SYNTHETIC_COPY_KINDS
            if is_synthetic:
                characteristics = (
                    dict(explicit_characteristics)
                    if explicit_characteristics is not None
                    else dict(old.current_characteristics)
                )
                kind = object_kind or old.object_kind
                successor = GameObject(
                    object_id=self.identity.new_id("object"),
                    object_kind=kind,
                    zone=destination,
                    owner=old.owner,
                    controller=controller
                    if destination in {Zone.BATTLEFIELD, Zone.STACK}
                    else None,
                    source_object_id=old.source_object_id,
                    predecessor_object_id=old.object_id,
                    created_by_event_id=event.event_id,
                    copy_kind=old.copy_kind,
                    copied_from_object_id=old.copied_from_object_id,
                    copiable_values_snapshot_id=old.copiable_values_snapshot_id,
                    copy_creation_event_id=old.copy_creation_event_id,
                    copy_target_choice_id=old.copy_target_choice_id,
                    current_characteristics=characteristics,
                    permanent_status={"tap": "UNTAPPED", "face": "FACE_UP", "phase": "PHASED_IN"}
                    if destination is Zone.BATTLEFIELD
                    else None,
                    identity_visible_to=set(old.identity_visible_to),
                    was_cast=old.was_cast,
                    pending_cease=destination is not Zone.BATTLEFIELD,
                )
            else:
                characteristics = self._physical_characteristics(old, face)
                if explicit_characteristics:
                    allowed = {
                        "selected_face_index",
                        "cast_choices",
                        "cast_payment",
                        "targets",
                        "modes",
                        "x_value",
                        "was_kicked",
                    }
                    unexpected = set(explicit_characteristics) - allowed
                    if unexpected:
                        raise IllegalAction(
                            f"unsupported successor continuity fields: {sorted(unexpected)}"
                        )
                    characteristics.update(explicit_characteristics)
                kind = object_kind or (
                    ObjectKind.PERMANENT
                    if destination is Zone.BATTLEFIELD
                    else ObjectKind.CARD_IN_ZONE
                )
                owner = old.owner
                if owner is None:
                    raise IllegalAction("physical card object requires an owner")
                face_down = cause == "COMMAND_FACE_DOWN"
                successor = GameObject(
                    object_id=self.identity.new_id("object"),
                    object_kind=kind,
                    zone=destination,
                    owner=owner,
                    controller=controller
                    if destination in {Zone.BATTLEFIELD, Zone.STACK}
                    else None,
                    component_card_instance_ids=old.component_card_instance_ids,
                    predecessor_object_id=old.object_id,
                    created_by_event_id=event.event_id,
                    current_characteristics=characteristics,
                    permanent_status={
                        "tap": "UNTAPPED",
                        "face": "FACE_DOWN" if face_down else "FACE_UP",
                        "phase": "PHASED_IN",
                    }
                    if destination is Zone.BATTLEFIELD
                    else None,
                    nonbattlefield_orientation="FACE_DOWN" if face_down else "FACE_UP",
                    identity_visible_to=default_visibility(
                        destination, owner, set(self.state.players), face_down
                    ),
                    was_cast=old.was_cast,
                )
            self.state.objects[successor.object_id] = successor
            self.register(successor)

        change = ZoneChange(
            self.identity.new_id("zone-change"),
            event.event_id,
            old.component_card_instance_ids,
            old.object_id,
            successor.object_id if successor else None,
            old.zone,
            destination,
            cause,
            "SAME_PHYSICAL_CARD"
            if successor and successor.component_card_instance_ids
            else ("SYNTHETIC_SUCCESSOR" if successor else None),
            commander_choice_id=commander_choice_id,
            external_owner_destination=external_record,
        )
        self.state.zone_changes.append(change)
        self.identity.validate_object_schema()
        return successor

    def cease(self, object_id: str, event: Event) -> None:
        obj = self.state.objects[object_id]
        if obj.ceased_to_exist:
            return
        if not obj.pending_cease:
            raise IllegalAction("only a synthetic object that arrived in a zone may cease")
        self._remove_from_zone(obj)
        obj.ceased_to_exist = True
        obj.retired = True
        obj.pending_cease = False
        self.state.events.append(
            Event(
                self.identity.new_id("event"),
                "SYNTHETIC_OBJECT_CEASED",
                event.cause_action_id,
                {"object_id": object_id, "after_event_id": event.event_id},
            )
        )

    def reincarnate_same_zone(self, object_id: str, cause: str, event: Event) -> GameObject:
        obj = self.state.objects[object_id]
        if cause not in {"REEXILE", "COMMAND_FACE_DOWN", "COMMAND_REENTRY"}:
            raise IllegalAction("same-zone reincarnation cause is unsupported")
        successor = self.move(object_id, obj.zone, cause, event)
        if successor is None or not successor.component_card_instance_ids:
            raise IllegalAction("synthetic object cannot reincarnate")
        return successor
