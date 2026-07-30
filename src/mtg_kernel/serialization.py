"""JSON-safe serialization for replay and independent state reconstruction."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from mtg_kernel.models import (
    Action,
    CardInstance,
    CardSpec,
    Choice,
    CopyKind,
    DeckSlot,
    Event,
    GameObject,
    GameState,
    LKISnapshot,
    ObjectKind,
    PlayerState,
    RNGStreamState,
    ReferenceMode,
    TargetRef,
    TerminalState,
    TurnState,
    Zone,
    ZoneChange,
)


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, set):
        return sorted(_jsonable(item) for item in value)
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def state_to_data(state: GameState, *, include_replay: bool = False) -> dict[str, Any]:
    raw_data = _jsonable(asdict(state))
    if not isinstance(raw_data, dict):
        raise TypeError("serialized game state must be a JSON object")
    data: dict[str, Any] = raw_data
    if not include_replay:
        data.pop("replay_commands", None)
        data.pop("replay_initial_state", None)
    return data


def _target(data: dict[str, Any] | None) -> TargetRef | None:
    if data is None:
        return None
    return TargetRef(
        str(data["object_id"]),
        ReferenceMode(str(data.get("mode", ReferenceMode.CURRENT_OBJECT_REQUIRED.value))),
        data.get("capability"),
        data.get("authority"),
    )


def _card_spec(data: dict[str, Any]) -> CardSpec:
    return CardSpec(
        card_spec_id=str(data["card_spec_id"]),
        name=str(data["name"]),
        oracle_id=str(data["oracle_id"]),
        oracle_record_sha256=str(data["oracle_record_sha256"]),
        source_version=str(data["source_version"]),
        mana_cost=str(data["mana_cost"]),
        mana_value=int(data["mana_value"]),
        supertypes=tuple(data["supertypes"]),
        card_types=tuple(data["card_types"]),
        subtypes=tuple(data["subtypes"]),
        colors=tuple(data["colors"]),
        color_identity=tuple(data["color_identity"]),
        keywords=tuple(data["keywords"]),
        power=data.get("power"),
        toughness=data.get("toughness"),
        oracle_text=data.get("oracle_text"),
        faces=tuple(dict(face) for face in data["faces"]),
        abilities=tuple(dict(ability) for ability in data["abilities"]),
    )


def state_from_data(data: dict[str, Any]) -> GameState:
    players = {
        player_id: PlayerState(
            player_id=str(value["player_id"]),
            life=int(value["life"]),
            in_game=bool(value["in_game"]),
            loss_reasons=list(value["loss_reasons"]),
            mana_pool={str(key): int(amount) for key, amount in value["mana_pool"].items()},
            land_plays_remaining=int(value["land_plays_remaining"]),
            maximum_hand_size=int(value["maximum_hand_size"]),
            failed_draw_count=int(value["failed_draw_count"]),
        )
        for player_id, value in data["players"].items()
    }
    turn_data = data["turn"]
    state = GameState(
        game_id=str(data["game_id"]),
        players=players,
        turn=TurnState(
            active_player_id=str(turn_data["active_player_id"]),
            number=int(turn_data["number"]),
            phase=str(turn_data["phase"]),
            step=str(turn_data["step"]),
            priority_holder_id=turn_data.get("priority_holder_id"),
            consecutive_priority_passes=int(turn_data["consecutive_priority_passes"]),
            cleanup_iteration=int(turn_data["cleanup_iteration"]),
            cleanup_repeat_pending=bool(turn_data["cleanup_repeat_pending"]),
        ),
        schema_version=str(data["schema_version"]),
    )
    state.card_specs = {key: _card_spec(value) for key, value in data.get("card_specs", {}).items()}
    state.deck_slots = {
        key: DeckSlot(
            str(value["deck_slot_id"]),
            str(value["card_spec_id"]),
            int(value["deck_source_position"]),
        )
        for key, value in data.get("deck_slots", {}).items()
    }
    state.card_instances = {
        key: CardInstance(
            str(value["card_instance_id"]),
            str(value["card_spec_id"]),
            str(value["deck_slot_id"]),
            str(value["owner_id"]),
            bool(value["commander_designation"]),
            str(value["creation_provenance"]),
        )
        for key, value in data.get("card_instances", {}).items()
    }
    for key, value in data.get("objects", {}).items():
        state.objects[key] = GameObject(
            object_id=str(value["object_id"]),
            object_kind=ObjectKind(str(value["object_kind"])),
            zone=Zone(str(value["zone"])),
            owner=value.get("owner"),
            controller=value.get("controller"),
            component_card_instance_ids=tuple(value.get("component_card_instance_ids", [])),
            source_object_id=value.get("source_object_id"),
            predecessor_object_id=value.get("predecessor_object_id"),
            created_by_event_id=value.get("created_by_event_id"),
            copy_kind=CopyKind(str(value.get("copy_kind", CopyKind.NONE.value))),
            copied_from_object_id=value.get("copied_from_object_id"),
            copiable_values_snapshot_id=value.get("copiable_values_snapshot_id"),
            copy_creation_event_id=value.get("copy_creation_event_id"),
            copy_target_choice_id=value.get("copy_target_choice_id"),
            current_characteristics=dict(value.get("current_characteristics", {})),
            counters={str(name): int(amount) for name, amount in value.get("counters", {}).items()},
            marked_damage=int(value.get("marked_damage", 0)),
            attached_to_ref=_target(value.get("attached_to_ref")),
            permanent_status=dict(value["permanent_status"])
            if value.get("permanent_status")
            else None,
            nonbattlefield_orientation=str(
                value.get("nonbattlefield_orientation", "NOT_APPLICABLE")
            ),
            identity_visible_to=set(value.get("identity_visible_to", [])),
            lki_snapshot_id=value.get("lki_snapshot_id"),
            was_cast=value.get("was_cast"),
            retired=bool(value.get("retired", False)),
            ceased_to_exist=bool(value.get("ceased_to_exist", False)),
            pending_cease=bool(value.get("pending_cease", False)),
        )
    state.zones = {str(key): list(value) for key, value in data.get("zones", {}).items()}
    state.stack = list(data.get("stack", []))
    state.pending_actions = list(data.get("pending_actions", []))
    state.actions = [
        Action(
            str(value["action_id"]),
            str(value["kind"]),
            str(value["actor_id"]),
            value.get("source_object_id"),
            tuple(
                TargetRef(
                    str(target["object_id"]),
                    ReferenceMode(
                        str(target.get("mode", ReferenceMode.CURRENT_OBJECT_REQUIRED.value))
                    ),
                    target.get("capability"),
                    target.get("authority"),
                )
                for target in value.get("targets", [])
                if target is not None
            ),
            tuple(value.get("modes", [])),
            int(value.get("x_value", 0)),
            dict(value.get("payments", {})),
            dict(value.get("metadata", {})),
        )
        for value in data.get("actions", [])
    ]
    state.choices = [
        Choice(
            str(value["choice_id"]),
            str(value["player_id"]),
            str(value["kind"]),
            value.get("selected"),
            str(value["cause_event_id"]),
        )
        for value in data.get("choices", [])
    ]
    state.events = [
        Event(
            str(value["event_id"]),
            str(value["kind"]),
            value.get("cause_action_id"),
            dict(value.get("payload", {})),
        )
        for value in data.get("events", [])
    ]
    state.zone_changes = [
        ZoneChange(
            str(value["zone_change_id"]),
            str(value["event_id"]),
            tuple(value.get("card_instance_ids", [])),
            str(value["from_object_id"]),
            value.get("to_object_id"),
            Zone(str(value["from_zone"])),
            Zone(str(value["to_zone"])),
            str(value["cause"]),
            value.get("predecessor_relationship"),
            value.get("commander_choice_id"),
            dict(value["external_owner_destination"])
            if value.get("external_owner_destination")
            else None,
        )
        for value in data.get("zone_changes", [])
    ]
    state.target_records = [dict(value) for value in data.get("target_records", [])]
    state.waiting_triggers = list(data.get("waiting_triggers", []))
    state.delayed_triggers = list(data.get("delayed_triggers", []))
    state.replacement_effects = [dict(value) for value in data.get("replacement_effects", [])]
    state.continuous_effects = [dict(value) for value in data.get("continuous_effects", [])]
    state.lki_snapshots = {
        key: LKISnapshot(
            str(value["lki_snapshot_id"]),
            str(value["object_id"]),
            dict(value["characteristics"]),
            value.get("controller"),
            {str(name): int(amount) for name, amount in value.get("counters", {}).items()},
            int(value.get("marked_damage", 0)),
            _target(value.get("attached_to_ref")),
        )
        for key, value in data.get("lki_snapshots", {}).items()
    }
    state.commander_designations = dict(data.get("commander_designations", {}))
    state.commander_cast_counts = {
        str(key): int(value) for key, value in data.get("commander_cast_counts", {}).items()
    }
    state.commander_damage = {
        str(key): {str(player): int(amount) for player, amount in value.items()}
        for key, value in data.get("commander_damage", {}).items()
    }
    state.pending_commander_choices = list(data.get("pending_commander_choices", []))
    state.external_object_ledger = [dict(value) for value in data.get("external_object_ledger", [])]
    state.rng_streams = {
        key: RNGStreamState(
            str(value["domain"]), int(value["draw_count"]), str(value["state_digest"])
        )
        for key, value in data.get("rng_streams", {}).items()
    }
    state.allocation = {str(key): int(value) for key, value in data.get("allocation", {}).items()}
    terminal = data.get("terminal", {})
    state.terminal = TerminalState(
        str(terminal.get("status", "ACTIVE")),
        list(terminal.get("winners", [])),
        list(terminal.get("losers", [])),
        list(terminal.get("cause_event_ids", [])),
    )
    state.replay_commands = [dict(value) for value in data.get("replay_commands", [])]
    state.replay_initial_state = data.get("replay_initial_state")
    return state
