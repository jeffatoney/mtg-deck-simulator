"""The sole engine-owned identity, RNG-domain, controller, and reference service."""

from __future__ import annotations

import hashlib

from mtg_kernel.errors import IllegalAction, UnsupportedCapability
from mtg_kernel.models import (
    CopyKind,
    GameObject,
    GameState,
    LKISnapshot,
    ObjectKind,
    ReferenceMode,
    TargetRef,
    Zone,
)

SUPPORTED_CONTINUITY = {
    "ZONE_CHANGE_TRIGGER_FINDS_SUCCESSOR",
    "GRANTED_CAST_ABILITY_FOLLOWS_CARD_TO_STACK",
    "CAST_PERMISSION_EFFECT_FINDS_SPELL_ON_STACK",
    "SAME_EFFECT_FINDS_MOVED_OBJECT",
    "FLASHBACK_CARD_TO_SPELL_CONTINUITY",
    "AFTERMATH_CARD_TO_SPELL_CONTINUITY",
}
UNSUPPORTED_CONTINUITY = {
    "CONTINUOUS_EFFECT_FOLLOWS_PERMANENT_SPELL",
    "STATIC_GRANTED_ABILITY_FOLLOWS_PERMANENT_SPELL",
    "PREVENTION_EFFECT_FOLLOWS_PERMANENT_SPELL",
    "PERMANENT_REFERENCES_CAST_COST_INFORMATION",
    "ENCHANTED_PERMANENT_LEAVE_TRIGGER_FINDS_AURAS",
    "LAND_PLAY_PERMISSION_FINDS_NEW_PERMANENT",
    "MADNESS_POST_RESOLUTION_TRACKING",
    "STICKER_RETENTION",
}
PUBLIC_SUCCESSOR_ZONES = {Zone.BATTLEFIELD, Zone.STACK, Zone.GRAVEYARD, Zone.EXILE, Zone.COMMAND}
ABILITY_KINDS = {
    ObjectKind.TRIGGERED_ABILITY,
    ObjectKind.ACTIVATED_ABILITY,
    ObjectKind.MANA_ABILITY,
    ObjectKind.ABILITY_COPY,
}


class IdentityService:
    def __init__(self, state: GameState, seed: str = "phase-a") -> None:
        self.state = state
        self.seed = seed

    def _draw(self, stream_name: str, purpose: str) -> str:
        stream = self.state.rng_streams[stream_name]
        payload = (
            f"{self.seed}\0{stream.domain}\0{stream.draw_count}\0{purpose}\0{stream.state_digest}"
        ).encode()
        value = hashlib.sha256(payload).hexdigest()
        stream.draw_count += 1
        stream.state_digest = hashlib.sha256(
            f"{stream.state_digest}:{value}".encode()
        ).hexdigest()
        return value

    def random_index(self, stream_name: str, upper_bound: int, purpose: str) -> int:
        if upper_bound <= 0:
            raise IllegalAction("random selection requires a positive bound")
        return int(self._draw(stream_name, purpose), 16) % upper_bound

    def new_id(self, category: str) -> str:
        if category not in self.state.allocation:
            self.state.allocation[category] = 0
        sequence = self.state.allocation[category]
        self.state.allocation[category] = sequence + 1
        suffix = self._draw("identity", f"{category}:{sequence}")[:16]
        return f"{self.state.game_id}:{category}-{suffix}"

    def validate_active_components(self) -> None:
        seen: set[str] = set()
        for obj in self.state.objects.values():
            if obj.retired or obj.ceased_to_exist:
                continue
            if obj.object_kind in ABILITY_KINDS and obj.component_card_instance_ids:
                raise IllegalAction("ability object duplicates its source card component")
            if obj.copy_kind in {CopyKind.TOKEN_COPY, CopyKind.SPELL_COPY, CopyKind.ABILITY_COPY}:
                if obj.component_card_instance_ids:
                    raise IllegalAction("synthetic object has a fabricated physical-card component")
            for card_id in obj.component_card_instance_ids:
                if card_id in seen:
                    raise IllegalAction(
                        "physical card component belongs to multiple active objects"
                    )
                seen.add(card_id)

    def validate_object_schema(self) -> None:
        forbidden_characteristic_keys = {
            "counters",
            "marked_damage",
            "attached_to_ref",
            "permanent_status",
            "identity_visible_to",
        }
        for obj in self.state.objects.values():
            if forbidden_characteristic_keys.intersection(obj.current_characteristics):
                raise IllegalAction("rules-state categories were stored as characteristics")
            battlefield_permanent = obj.zone is Zone.BATTLEFIELD and obj.object_kind in {
                ObjectKind.PERMANENT,
                ObjectKind.TOKEN_OBJECT,
            }
            if battlefield_permanent != (obj.permanent_status is not None):
                raise IllegalAction("permanent status is valid only on battlefield permanents")
            if obj.zone is not Zone.BATTLEFIELD and obj.nonbattlefield_orientation not in {
                "NOT_APPLICABLE",
                "FACE_UP",
                "FACE_DOWN",
            }:
                raise IllegalAction("invalid nonbattlefield orientation")
            if obj.object_kind is ObjectKind.CARD_IN_ZONE and obj.controller is not None:
                raise IllegalAction("ordinary cards outside battlefield and stack have no controller")
            if obj.object_kind in {
                ObjectKind.SPELL,
                ObjectKind.SPELL_COPY,
                ObjectKind.ACTIVATED_ABILITY,
                ObjectKind.TRIGGERED_ABILITY,
                ObjectKind.ABILITY_COPY,
            } and obj.zone is Zone.STACK and obj.controller is None:
                raise IllegalAction("every stack object must have a controller")
            if obj.object_kind in ABILITY_KINDS and obj.owner is not None:
                raise IllegalAction("ability objects do not receive a fabricated rules owner")
            if obj.object_kind is ObjectKind.SPELL_COPY and obj.owner != obj.controller:
                raise IllegalAction("spell-copy owner must be its copy-placement controller")
            if obj.copy_kind is not CopyKind.NONE and obj.predecessor_object_id is not None:
                raise IllegalAction("copy ancestry may not use predecessor identity")
        self.validate_active_components()

    def snapshot_lki(self, obj: GameObject) -> LKISnapshot:
        snapshot = LKISnapshot(
            self.new_id("lki"),
            obj.object_id,
            dict(obj.current_characteristics),
            obj.controller,
            dict(obj.counters),
            obj.marked_damage,
            obj.attached_to_ref,
        )
        self.state.lki_snapshots[snapshot.lki_snapshot_id] = snapshot
        obj.lki_snapshot_id = snapshot.lki_snapshot_id
        return snapshot

    def resolve_reference(self, ref: TargetRef) -> GameObject | LKISnapshot:
        obj = self.state.objects.get(ref.object_id)
        if ref.mode is ReferenceMode.CURRENT_OBJECT_REQUIRED:
            if obj is None or obj.retired or obj.ceased_to_exist:
                raise IllegalAction("target is no longer the referenced object")
            return obj
        if ref.mode is ReferenceMode.LAST_KNOWN_INFORMATION:
            if ref.authority is None:
                raise IllegalAction("last-known information requires an authorizing rule")
            if obj is None or obj.lki_snapshot_id is None:
                raise IllegalAction("no authorized last-known-information snapshot")
            return self.state.lki_snapshots[obj.lki_snapshot_id]
        capability = ref.capability
        if capability in UNSUPPORTED_CONTINUITY or capability not in SUPPORTED_CONTINUITY:
            raise UnsupportedCapability(f"unsupported continuity capability: {capability}")
        successors = [
            candidate
            for candidate in self.state.objects.values()
            if candidate.predecessor_object_id == ref.object_id
            and not candidate.retired
            and not candidate.ceased_to_exist
        ]
        if len(successors) != 1:
            raise IllegalAction("successor tracking requires exactly one authorized successor")
        successor = successors[0]
        if capability in {
            "ZONE_CHANGE_TRIGGER_FINDS_SUCCESSOR",
            "SAME_EFFECT_FINDS_MOVED_OBJECT",
        } and successor.zone not in PUBLIC_SUCCESSOR_ZONES:
            raise IllegalAction("this continuity capability cannot follow into a hidden zone")
        return successor
