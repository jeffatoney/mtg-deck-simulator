"""RFC-8785-compatible integer-only identity-state-v2.0.0 hashing allowlist."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from typing import Any

from mtg_kernel.models import GameState

HASH_SCHEMA_VERSION = "identity-state-v2.0.0"
HASH_INCLUDED_ROOTS = (
    "schema_version",
    "game_id",
    "allocation",
    "rng_streams",
    "turn",
    "players",
    "deck_slots",
    "card_instances",
    "zones",
    "objects",
    "stack",
    "pending_actions",
    "recorded_choices",
    "targets",
    "waiting_triggers",
    "delayed_triggers",
    "replacement_effects",
    "continuous_effects",
    "lki_snapshots",
    "commander",
    "external_object_ledger",
    "terminal",
)


def _safe(value: Any) -> Any:
    if isinstance(value, float):
        raise TypeError("floating-point state is outside the Phase A hash schema")
    if isinstance(value, dict):
        return {str(key): _safe(item) for key, item in value.items()}
    if isinstance(value, set):
        return sorted(_safe(item) for item in value)
    if isinstance(value, (list, tuple)):
        return [_safe(item) for item in value]
    return value


def state_hash_document(state: GameState) -> dict[str, Any]:
    zones = []
    for zone_id, object_ids in sorted(state.zones.items()):
        zone_type, _, owner = zone_id.partition(":")
        zones.append(
            {
                "zone_id": zone_id,
                "zone_type": zone_type,
                "owner_id": None if owner == "shared" else owner,
                "ordered_object_ids": list(object_ids),
            }
        )
    objects = {
        object_id: {
            "object_id": obj.object_id,
            "object_kind": obj.object_kind,
            "zone": obj.zone,
            "owner": obj.owner,
            "controller": obj.controller,
            "component_card_instance_ids": obj.component_card_instance_ids,
            "source_object_id": obj.source_object_id,
            "predecessor_object_id": obj.predecessor_object_id,
            "created_by_event_id": obj.created_by_event_id,
            "copy_kind": obj.copy_kind,
            "copied_from_object_id": obj.copied_from_object_id,
            "copiable_values_snapshot_id": obj.copiable_values_snapshot_id,
            "copy_creation_event_id": obj.copy_creation_event_id,
            "copy_target_choice_id": obj.copy_target_choice_id,
            "current_characteristics": obj.current_characteristics,
            "counters": obj.counters,
            "marked_damage": obj.marked_damage,
            "attached_to_ref": asdict(obj.attached_to_ref) if obj.attached_to_ref else None,
            "permanent_status": obj.permanent_status,
            "nonbattlefield_orientation": obj.nonbattlefield_orientation,
            "visibility": {"identity_visible_to": obj.identity_visible_to},
            "lki_snapshot_id": obj.lki_snapshot_id,
            "was_cast": obj.was_cast,
            "retired": obj.retired,
            "ceased_to_exist": obj.ceased_to_exist,
        }
        for object_id, obj in sorted(state.objects.items())
    }
    document = {
        "schema_version": HASH_SCHEMA_VERSION,
        "game_id": state.game_id,
        "allocation": {
            "next_object_sequence": state.allocation.get("object", 0),
            "next_action_sequence": state.allocation.get("action", 0),
            "next_event_sequence": state.allocation.get("event", 0),
            "next_zone_change_sequence": state.allocation.get("zone-change", 0),
            "next_lki_sequence": state.allocation.get("lki", 0),
        },
        "rng_streams": {
            name: {
                "domain": stream.domain,
                "draw_count": stream.draw_count,
                "state_digest": stream.state_digest,
            }
            for name, stream in sorted(state.rng_streams.items())
        },
        "turn": asdict(state.turn),
        "players": {
            player_id: asdict(player)
            for player_id, player in sorted(state.players.items())
        },
        "deck_slots": {
            slot_id: asdict(slot) for slot_id, slot in sorted(state.deck_slots.items())
        },
        "card_instances": {
            card_id: asdict(card)
            for card_id, card in sorted(state.card_instances.items())
        },
        "zones": zones,
        "objects": objects,
        "stack": {"ordered_object_ids": list(state.stack)},
        "pending_actions": list(state.pending_actions),
        "recorded_choices": [asdict(choice) for choice in state.choices],
        "targets": list(state.target_records),
        "waiting_triggers": list(state.waiting_triggers),
        "delayed_triggers": list(state.delayed_triggers),
        "replacement_effects": list(state.replacement_effects),
        "continuous_effects": list(state.continuous_effects),
        "lki_snapshots": {
            snapshot_id: asdict(snapshot)
            for snapshot_id, snapshot in sorted(state.lki_snapshots.items())
        },
        "commander": {
            "designations": dict(sorted(state.commander_designations.items())),
            "command_zone_cast_counts": dict(sorted(state.commander_cast_counts.items())),
            "damage_by_commander": {
                card_id: dict(sorted(damage.items()))
                for card_id, damage in sorted(state.commander_damage.items())
            },
            "pending_zone_choices": list(state.pending_commander_choices),
        },
        "external_object_ledger": list(state.external_object_ledger),
        "terminal": asdict(state.terminal),
    }
    if tuple(document) != HASH_INCLUDED_ROOTS:
        raise TypeError("state hash root allowlist drifted without a schema version change")
    return _safe(document)


def canonical_state_bytes(state: GameState) -> bytes:
    return json.dumps(
        state_hash_document(state),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def state_hash(state: GameState) -> str:
    return hashlib.sha256(canonical_state_bytes(state)).hexdigest()
