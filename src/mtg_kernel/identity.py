"""The sole engine-owned identity and reference service."""

from __future__ import annotations

import hashlib

from mtg_kernel.errors import IllegalAction, UnsupportedCapability
from mtg_kernel.models import GameObject, GameState, LKISnapshot, ReferenceMode, TargetRef

SUPPORTED_CONTINUITY = {
    "ZONE_CHANGE_TRIGGER_FINDS_SUCCESSOR",
    "GRANTED_CAST_ABILITY_FOLLOWS_CARD_TO_STACK",
    "CAST_PERMISSION_EFFECT_FINDS_SPELL_ON_STACK",
    "SAME_EFFECT_FINDS_MOVED_OBJECT",
    "FLASHBACK_CARD_TO_SPELL_CONTINUITY",
    "AFTERMATH_CARD_TO_SPELL_CONTINUITY",
}


class IdentityService:
    def __init__(self, state: GameState, seed: str = "phase-a") -> None:
        self.state = state
        self.seed = seed

    def new_id(self, category: str) -> str:
        position = self.state.rng_positions["identity"]
        self.state.rng_positions["identity"] = position + 1
        suffix = hashlib.sha256(f"{self.seed}:identity:{category}:{position}".encode()).hexdigest()[
            :16
        ]
        return f"{self.state.game_id}:{category}-{suffix}"

    def validate_active_components(self) -> None:
        seen: set[str] = set()
        for obj in self.state.objects.values():
            if obj.retired or obj.ceased_to_exist:
                continue
            for card_id in obj.component_card_instance_ids:
                if card_id in seen:
                    raise IllegalAction(
                        "physical card component belongs to multiple active objects"
                    )
                seen.add(card_id)

    def snapshot_lki(self, obj: GameObject) -> LKISnapshot:
        snapshot = LKISnapshot(
            self.new_id("lki"), obj.object_id, dict(obj.current_characteristics), obj.controller
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
            if obj is None or obj.lki_snapshot_id is None:
                raise IllegalAction("no authorized last-known-information snapshot")
            return self.state.lki_snapshots[obj.lki_snapshot_id]
        if ref.capability not in SUPPORTED_CONTINUITY:
            raise UnsupportedCapability(f"unsupported continuity capability: {ref.capability}")
        successors = [
            candidate
            for candidate in self.state.objects.values()
            if candidate.predecessor_object_id == ref.object_id
        ]
        if len(successors) != 1:
            raise IllegalAction("successor tracking requires exactly one authorized successor")
        return successors[0]
