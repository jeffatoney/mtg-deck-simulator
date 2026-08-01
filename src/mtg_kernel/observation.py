"""Hidden-information-safe observations with per-generation opaque handles."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from mtg_kernel.errors import IllegalAction
from mtg_kernel.models import GameObject, GameState, Zone

PUBLIC_OBJECT_ZONES = {Zone.BATTLEFIELD, Zone.STACK, Zone.GRAVEYARD, Zone.EXILE, Zone.COMMAND}


@dataclass
class ObservationService:
    state: GameState
    generation: int = 0
    _handles: dict[str, tuple[str, str]] = field(default_factory=dict)

    @staticmethod
    def _face_down(obj: GameObject) -> bool:
        return obj.nonbattlefield_orientation == "FACE_DOWN" or bool(
            obj.permanent_status and obj.permanent_status.get("face") == "FACE_DOWN"
        )

    def _identity_known(self, obj: GameObject, player_id: str) -> bool:
        if self._face_down(obj):
            return False
        if obj.zone is Zone.LIBRARY:
            return False
        return player_id in obj.identity_visible_to

    def observe(self, player_id: str) -> dict[str, Any]:
        if player_id not in self.state.players:
            raise IllegalAction("unknown observing player")
        self.generation += 1
        self._handles.clear()
        objects: list[dict[str, Any]] = []
        zone_counts: dict[str, int] = {}
        for obj in self.state.objects.values():
            if obj.retired or obj.ceased_to_exist:
                continue
            zone_label = obj.zone.value
            zone_counts[zone_label] = zone_counts.get(zone_label, 0) + 1
            individually_visible = obj.zone in PUBLIC_OBJECT_ZONES or (
                obj.zone is Zone.HAND and obj.owner == player_id
            )
            if obj.zone is Zone.LIBRARY or (obj.zone is Zone.HAND and obj.owner != player_id):
                individually_visible = False
            if not individually_visible:
                continue
            handle = hashlib.sha256(
                (
                    f"policy-handle:{player_id}:{self.generation}:{obj.object_id}:"
                    f"{self.state.rng_streams['policy'].state_digest}"
                ).encode()
            ).hexdigest()[:24]
            self._handles[handle] = (player_id, obj.object_id)
            identity = (
                obj.current_characteristics.get("name")
                if self._identity_known(obj, player_id)
                else None
            )
            objects.append(
                {
                    "handle": handle,
                    "zone": zone_label,
                    "owner": obj.owner if obj.zone in PUBLIC_OBJECT_ZONES else None,
                    "controller": obj.controller
                    if obj.zone in {Zone.BATTLEFIELD, Zone.STACK}
                    else None,
                    "identity": identity,
                    "face_down": self._face_down(obj),
                    "card_types": obj.current_characteristics.get("card_types", [])
                    if identity is not None
                    else [],
                }
            )
        hand_counts = {
            player: len(self.state.zones.get(f"{Zone.HAND.value}:{player}", []))
            for player in self.state.players
        }
        library_counts = {
            player: len(self.state.zones.get(f"{Zone.LIBRARY.value}:{player}", []))
            for player in self.state.players
        }
        return {
            "generation": self.generation,
            "player": player_id,
            "objects": objects,
            "zone_counts": zone_counts,
            "hand_counts": hand_counts,
            "library_counts": library_counts,
            "life": {player: state.life for player, state in self.state.players.items()},
            "turn": {
                "number": self.state.turn.number,
                "active_player": self.state.turn.active_player_id,
                "phase": self.state.turn.phase,
                "step": self.state.turn.step,
                "priority_holder": self.state.turn.priority_holder_id,
            },
        }

    def observe_for_policy(self, player_id: str) -> dict[str, Any]:
        return self.observe(player_id)

    def handle_for_object(
        self, player_id: str, generation: int, object_id: str
    ) -> str | None:
        """Return the current opaque handle for a visible object without exposing its ID."""
        self.require_current_generation(generation)
        for handle, binding in self._handles.items():
            if binding == (player_id, object_id):
                return handle
        return None

    def resolve_handle(self, player_id: str, generation: int, handle: str) -> GameObject:
        self.require_current_generation(generation)
        binding = self._handles.get(handle)
        if binding is None or binding[0] != player_id:
            raise IllegalAction("opaque observation handle is invalid")
        obj = self.state.objects.get(binding[1])
        if obj is None or obj.retired or obj.ceased_to_exist:
            raise IllegalAction("opaque observation handle no longer resolves")
        return obj

    def require_current_generation(self, generation: int) -> None:
        if generation != self.generation:
            raise IllegalAction("observation handles have been revoked")
