"""Hidden-information-safe policy observations with revocable opaque handles."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from mtg_kernel.errors import IllegalAction
from mtg_kernel.models import GameState, Zone


@dataclass
class ObservationService:
    state: GameState
    generation: int = 0

    def observe(self, player_id: str) -> dict[str, Any]:
        self.generation += 1
        handles: list[dict[str, Any]] = []
        for obj in self.state.objects.values():
            if obj.retired or obj.ceased_to_exist:
                continue
            visible = player_id in obj.identity_visible_to or obj.zone in {
                Zone.BATTLEFIELD,
                Zone.STACK,
                Zone.GRAVEYARD,
            }
            handle = hashlib.sha256(
                f"observation:{self.generation}:{obj.object_id}".encode()
            ).hexdigest()[:20]
            handles.append(
                {
                    "handle": handle,
                    "zone": obj.zone.value,
                    "identity": obj.current_characteristics.get("name") if visible else None,
                }
            )
        return {
            "generation": self.generation,
            "player": player_id,
            "objects": handles,
            "life": {pid: p.life for pid, p in self.state.players.items()},
        }

    def require_current_generation(self, generation: int) -> None:
        if generation != self.generation:
            raise IllegalAction("observation handles have been revoked")
