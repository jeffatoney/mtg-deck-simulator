"""Common mana, bounce, removal, damage, and untap Phase B effects."""

from __future__ import annotations

from typing import Any

from mtg_kernel.errors import IllegalAction
from mtg_kernel.mana import add_mana
from mtg_kernel.models import Action, GameObject
from mtg_kernel.phase_b_runtime_helpers import (
    _destroy,
    _permanents,
    _return_to_hand,
    _untap,
)
from mtg_kernel.phase_b_runtime_support import _ORIGINALS, _subtypes, _types


def _source_permanent(self: Any, source: GameObject | None, action: Action) -> GameObject:
    object_id = action.source_object_id
    if source is not None and source.source_object_id is not None:
        object_id = source.source_object_id
    if object_id is None or object_id not in self.state.objects:
        raise IllegalAction("effect cannot find its source permanent")
    permanent = self.state.objects[object_id]
    if not isinstance(permanent, GameObject):
        raise TypeError("state object registry returned a non-GameObject value")
    return permanent


def apply_effect_common(
    self: Any,
    source: GameObject | None,
    action: Action,
    effect: dict[str, Any],
    targets: list[GameObject],
    choices: dict[str, Any],
) -> bool:
    kind = str(effect.get("kind", "NONE"))
    delegated = {
        "NONE",
        "ADD_MANA",
        "ADD_CHOSEN_MANA",
        "ATTACH_AURA",
        "CREATE_SPELL_COPY",
        "CREATE_TOKEN_COPIES",
        "CREATE_TREASURES_FOR_DAMAGED_OPPONENTS",
        "DAMAGE",
        "DAMAGE_EACH_OPPONENT",
        "DRAW",
        "EXILE_CREATE_TOKEN",
        "EXILE_OBJECTS",
        "EXILE_OPPONENT_GRAVEYARDS",
        "EXILE_TARGET",
        "FACT_OR_FICTION_MINIMIZING",
        "LIBRARY_SECOND",
        "MEMORY",
        "RECORD_UNKNOWN_BREECHES_EXILES",
        "SCRY",
        "SEQUENCE",
        "TRANSMUTE",
        "TYPECYCLE",
    }
    if kind in delegated:
        _ORIGINALS["apply_effect"](self, source, action, effect, targets, choices)
        return True

    if kind == "ADD_COMMANDER_COLOR":
        selected_color = str(choices.get("mana_color", ""))
        if selected_color not in {"U", "R"}:
            raise IllegalAction("commander-color mana requires an explicit U or R choice")
        add_mana(self.state.players[action.actor_id].mana_pool, {selected_color: 1})
        self._event("MANA_ADDED", action, mana={selected_color: 1}, source_kind=kind)
        return True

    if kind == "ADD_OPPONENT_PROFILE_COLOR":
        profile = str(choices.get("opponent_mana_profile", "blue_red_available"))
        selected_color = str(choices.get("mana_color", ""))
        if profile != "blue_red_available" or selected_color not in {"U", "R"}:
            raise IllegalAction("opponent-profile mana requires an explicit available U or R")
        add_mana(self.state.players[action.actor_id].mana_pool, {selected_color: 1})
        self._event("MANA_ADDED", action, mana={selected_color: 1}, opponent_profile=profile)
        return True

    if kind == "ADD_CHOSEN_MANA_AND_DAMAGE_SELF":
        allowed = tuple(str(value) for value in effect.get("choices", ()))
        selected_color = str(choices.get("mana_color", ""))
        if selected_color not in allowed:
            raise IllegalAction("pain-land ability requires an explicit legal color")
        add_mana(self.state.players[action.actor_id].mana_pool, {selected_color: 1})
        self.state.players[action.actor_id].life -= int(effect.get("damage", 1))
        self._event("MANA_ADDED_AND_PLAYER_DAMAGED", action, mana={selected_color: 1})
        self.check_state_based_actions()
        return True

    if kind == "ADD_BLUE_OR_FIXED_CHOSEN":
        permanent = _source_permanent(self, source, action)
        fixed = str(permanent.current_characteristics.get("chosen_color", ""))
        selected_color = str(choices.get("mana_color", ""))
        if selected_color not in {"U", fixed} or not selected_color:
            raise IllegalAction("Thriving Isle requires blue or its fixed chosen color")
        add_mana(self.state.players[action.actor_id].mana_pool, {selected_color: 1})
        self._event("MANA_ADDED", action, mana={selected_color: 1})
        return True

    if kind in {"BOUNCE_TARGET", "BOUNCE_TARGETS"}:
        for target in targets:
            _return_to_hand(self, target, action, kind)
        return True

    if kind == "BOUNCE_ATTACKING_CREATURES":
        for target in list(_permanents(self)):
            if "Creature" in _types(target) and target.current_characteristics.get("attacking"):
                _return_to_hand(self, target, action, kind)
        return True

    if kind == "BOUNCE_ALL_ARTIFACTS":
        for target in list(_permanents(self)):
            if "Artifact" in _types(target):
                _return_to_hand(self, target, action, kind)
        return True

    if kind == "ECHOING_BOUNCE":
        if len(targets) != 1:
            raise IllegalAction("Echoing Truth requires one target")
        name = str(targets[0].current_characteristics.get("name", ""))
        for target in list(_permanents(self)):
            if str(target.current_characteristics.get("name", "")) == name:
                _return_to_hand(self, target, action, kind)
        return True

    if kind == "RETURN_CONTROLLED_LAND":
        if len(targets) != 1:
            raise IllegalAction("bounce-land trigger requires one controlled land")
        _return_to_hand(self, targets[0], action, kind)
        return True

    if kind == "DESTROY":
        if len(targets) != 1:
            raise IllegalAction("destroy effect requires one target")
        _destroy(self, targets[0], action, kind)
        return True

    if kind in {"DESTROY_TARGETS", "DESTROY_ALL_OPPONENT_ARTIFACTS"}:
        selected_targets = (
            targets
            if kind == "DESTROY_TARGETS"
            else [
                obj
                for obj in _permanents(self)
                if obj.controller != action.actor_id and "Artifact" in _types(obj)
            ]
        )
        for target in list(selected_targets):
            _destroy(self, target, action, kind)
        return True

    if kind == "DESTROY_ARTIFACTS_MV_LEQ":
        maximum = int(effect.get("maximum_mana_value", 0))
        for target in list(_permanents(self)):
            if (
                "Artifact" in _types(target)
                and int(target.current_characteristics.get("mana_value", 0)) <= maximum
            ):
                _destroy(self, target, action, kind)
        return True

    if kind == "DAMAGE_ALL_CREATURES_PLANESWALKERS":
        amount = int(effect.get("amount", 0))
        if amount < 0:
            raise IllegalAction("damage amount cannot be negative")
        damage_assignments: dict[str, int] = {}
        for target in _permanents(self):
            types = _types(target)
            if "Creature" in types:
                target.marked_damage += amount
                damage_assignments[target.object_id] = amount
            elif "Planeswalker" in types:
                loyalty = target.counters.get("LOYALTY")
                if not isinstance(loyalty, int):
                    raise IllegalAction("planeswalker damage requires loyalty counters")
                target.counters["LOYALTY"] = loyalty - amount
                damage_assignments[target.object_id] = amount
        rules_source = self._rules_source(source)
        self._event(
            "DAMAGE_DEALT_TO_OBJECTS",
            action,
            source_object_id=rules_source.object_id if rules_source is not None else None,
            assignments=damage_assignments,
            combat=False,
        )
        return True

    if kind == "DAMAGE_ALL_NON_SUBTYPE":
        amount = int(effect.get("amount", 0))
        excluded = str(effect.get("excluded_subtype", ""))
        creature_assignments = [
            (obj, amount)
            for obj in _permanents(self)
            if "Creature" in _types(obj) and excluded not in _subtypes(obj)
        ]
        if creature_assignments:
            self._damage_batch(
                self._rules_source(source), creature_assignments, action, combat=False
            )
        return True

    if kind == "EACH_OPPONENT_LOSES_LIFE":
        amount = int(effect.get("amount", 1))
        for player_id, player in self.state.players.items():
            if player.in_game and player_id != action.actor_id:
                player.life -= amount
        self._event("LIFE_LOST", action, amount=amount, each_opponent=True)
        self.check_state_based_actions()
        return True

    if kind == "CREATE_TREASURE":
        for _ in range(int(effect.get("count", 1))):
            self.create_treasure(action.actor_id, action)
        return True

    if kind == "UNTAP_SOURCE":
        _untap(self, [_source_permanent(self, source, action)], action)
        return True

    if kind == "UNTAP_ATTACHED":
        aura = _source_permanent(self, source, action)
        if aura.attached_to_ref is None:
            raise IllegalAction("Aura is not attached")
        attached = self.identity.resolve_reference(aura.attached_to_ref)
        if not isinstance(attached, GameObject):
            raise IllegalAction("attached object is unavailable")
        _untap(self, [attached], action)
        return True

    return False
