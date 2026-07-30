"""The only authoritative zone mutation service."""

from __future__ import annotations

from mtg_kernel.errors import IllegalAction
from mtg_kernel.identity import IdentityService
from mtg_kernel.models import CopyKind, Event, GameObject, GameState, ObjectKind, Zone, ZoneChange


class ZoneService:
    def __init__(self, state: GameState, identity: IdentityService) -> None:
        self.state, self.identity = state, identity

    @staticmethod
    def zone_key(zone: Zone, owner: str | None) -> str:
        return f"{zone.value}:{owner or 'shared'}"

    def register(self, obj: GameObject) -> None:
        self.identity.validate_active_components()
        key = self.zone_key(obj.zone, obj.owner)
        self.state.zones.setdefault(key, []).append(obj.object_id)
        if obj.zone is Zone.STACK:
            self.state.stack.append(obj.object_id)

    def move(
        self, object_id: str, destination: Zone, cause: str, event: Event
    ) -> GameObject | None:
        old = self.state.objects[object_id]
        if old.retired or old.ceased_to_exist:
            raise IllegalAction("cannot move a retired object")
        old_key = self.zone_key(old.zone, old.owner)
        if object_id in self.state.zones.get(old_key, []):
            self.state.zones[old_key].remove(object_id)
        if object_id in self.state.stack:
            self.state.stack.remove(object_id)
        self.identity.snapshot_lki(old)
        old.retired = True
        external_leaves_model = old.object_kind is ObjectKind.EXTERNAL_PUBLIC_OBJECT
        ceases = old.copy_kind in {CopyKind.TOKEN_COPY, CopyKind.SPELL_COPY, CopyKind.ABILITY_COPY}
        successor: GameObject | None = None
        if external_leaves_model:
            self.state.external_object_ledger.append(
                {
                    "object_id": old.object_id,
                    "owner": old.owner,
                    "destination": destination.value,
                    "position": "SECOND_FROM_TOP" if cause == "COMMIT" else "UNSPECIFIED",
                }
            )
        elif not ceases:
            kind = (
                ObjectKind.PERMANENT if destination is Zone.BATTLEFIELD else ObjectKind.CARD_IN_ZONE
            )
            successor = GameObject(
                object_id=self.identity.new_id("object"),
                object_kind=kind,
                zone=destination,
                owner=old.owner,
                controller=old.controller if destination is Zone.BATTLEFIELD else None,
                component_card_instance_ids=old.component_card_instance_ids,
                predecessor_object_id=old.object_id,
                created_by_event_id=event.event_id,
                current_characteristics=dict(old.current_characteristics),
                permanent_status={"tap": "UNTAPPED", "face": "FACE_UP", "phase": "PHASED_IN"}
                if destination is Zone.BATTLEFIELD
                else None,
                identity_visible_to=set(old.identity_visible_to),
                was_cast=old.was_cast,
            )
            self.state.objects[successor.object_id] = successor
            self.register(successor)
        else:
            old.ceased_to_exist = True
        change = ZoneChange(
            self.identity.new_id("zone-change"),
            event.event_id,
            old.component_card_instance_ids,
            old.object_id,
            successor.object_id if successor else None,
            old.zone,
            destination,
            cause,
            "SAME_PHYSICAL_CARD" if successor else None,
            external_owner_destination=self.state.external_object_ledger[-1]
            if external_leaves_model
            else None,
        )
        self.state.zone_changes.append(change)
        self.identity.validate_active_components()
        return successor

    def reincarnate_same_zone(self, object_id: str, cause: str, event: Event) -> GameObject:
        obj = self.state.objects[object_id]
        if cause not in {"REEXILE", "COMMAND_FACE_DOWN", "COMMAND_REENTRY"}:
            raise IllegalAction("same-zone reincarnation cause is unsupported")
        successor = self.move(object_id, obj.zone, cause, event)
        if successor is None:
            raise IllegalAction("synthetic object cannot reincarnate")
        if cause == "COMMAND_FACE_DOWN":
            successor.nonbattlefield_orientation = "FACE_DOWN"
        return successor
