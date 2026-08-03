"""Face-down manifestation effects for the exact-deck Phase B runtime."""

from __future__ import annotations

from typing import Any

from mtg_kernel.errors import IllegalAction
from mtg_kernel.models import Action, GameObject, ObjectKind, Zone


def apply_effect_manifest(
    self: Any,
    source: GameObject | None,
    action: Action,
    effect: dict[str, Any],
    targets: list[GameObject],
    choices: dict[str, Any],
) -> bool:
    """Exile one creature, then manifest its controller's top library card."""

    del source, choices
    if str(effect.get("kind", "NONE")) != "EXILE_AND_MANIFEST":
        return False
    if len(targets) != 1:
        raise IllegalAction("exile-and-manifest effect requires one creature target")

    target = targets[0]
    controller = target.controller or target.owner
    if controller is None or controller not in self.state.players:
        raise IllegalAction("manifesting player is unavailable")

    self.zones.move(
        target.object_id,
        Zone.EXILE,
        "EXILE_AND_MANIFEST",
        self._event("OBJECT_EXILED", action, object_id=target.object_id),
    )

    library_key = self.zones.zone_key(Zone.LIBRARY, controller)
    library = self.state.zones.get(library_key, [])
    if not library:
        self._event("MANIFEST_SKIPPED_EMPTY_LIBRARY", action, player_id=controller)
        return True

    top_object_id = library[-1]
    manifest_event = self._event(
        "CARD_MANIFESTED",
        action,
        player_id=controller,
        from_object_id=top_object_id,
    )
    manifested = self.zones.move(
        top_object_id,
        Zone.BATTLEFIELD,
        "MANIFEST",
        manifest_event,
        object_kind=ObjectKind.PERMANENT,
        controller=controller,
    )
    if manifested is None or not manifested.component_card_instance_ids:
        raise IllegalAction("manifest requires a physical card from the library")

    manifested.current_characteristics = {
        "name": "Face-down creature",
        "mana_cost": "",
        "mana_value": 0,
        "supertypes": [],
        "card_types": ["Creature"],
        "subtypes": [],
        "colors": [],
        "color_identity": [],
        "keywords": [],
        "abilities": [],
        "power": 2,
        "toughness": 2,
        "manifested": True,
    }
    manifested.permanent_status = {
        "tap": "UNTAPPED",
        "face": "FACE_DOWN",
        "phase": "PHASED_IN",
    }
    manifested.nonbattlefield_orientation = "NOT_APPLICABLE"
    manifested.identity_visible_to = {controller}
    self.identity.validate_object_schema()
    self._queue_etb(manifested)
    self._event(
        "MANIFESTED_PERMANENT_CREATED",
        action,
        player_id=controller,
        object_id=manifested.object_id,
        predecessor_object_id=top_object_id,
    )
    return True
