"""Public opaque legal-action broker with explicit ETB choice variants."""

from __future__ import annotations

from typing import Any

from mtg_kernel.engine import MAIN_PHASES
from mtg_kernel.errors import UnsupportedCapability
from mtg_kernel.models import GameObject, Zone
from mtg_kernel.phase_b_actions import (
    automatic_ability_execution_supported,
    effect_execution_supported,
)
from mtg_kernel.resource_sources import commander_colors_from_state
from mtg_policy.broker_core import (
    PERMANENT_TYPES,
    ActionBroker as _CoreActionBroker,
    ObservedAction,
    _InternalAction,
)


class ActionBroker(_CoreActionBroker):
    """Extend the certified broker core with explicit cast-time ETB decisions."""

    @staticmethod
    def _merge_choices(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
        merged = dict(base)
        for key, value in extra.items():
            if key == "trigger_targets":
                current = dict(merged.get(key, {}))
                current.update(dict(value))
                merged[key] = current
            else:
                merged[key] = value
        return merged

    def _ability_choice_variants(self, ability: dict[str, Any]) -> tuple[dict[str, Any], ...]:
        effect = dict(ability.get("effect", {}))
        if str(effect.get("kind", "NONE")) in {
            "ADD_COMMANDER_COLOR",
            "ADD_COMMANDER_COLOR_AND_MARK",
        }:
            try:
                colors = commander_colors_from_state(self.executor.state, self.player_id)
            except UnsupportedCapability:
                return ()
            return tuple({"mana_color": color} for color in colors)
        return super()._ability_choice_variants(ability)

    def _entry_trigger_choice_variants(
        self, obj: GameObject
    ) -> tuple[tuple[dict[str, Any], dict[str, Any]], ...]:
        """Enumerate policy-visible choices for supported targeted ETB triggers.

        Automatic ETB behavior that needs no policy decision remains implicit. Any
        unsupported automatic ability still suppresses the cast. Targeted,
        nonoptional ETB triggers with supported effects are made explicit in the
        cast action, using opaque public handles while retaining object IDs only in
        the broker's private execution arguments.
        """

        variants: tuple[tuple[dict[str, Any], dict[str, Any]], ...] = (({}, {}),)
        for raw_ability in obj.current_characteristics.get("abilities", ()):
            ability = dict(raw_ability)
            schema = dict(ability.get("target_schema", {}))
            is_targeted_etb = bool(
                ability.get("kind") == "TRIGGERED"
                and ability.get("trigger") == "ETB"
                and not ability.get("optional")
                and int(schema.get("max", 0) or 0) > 0
                and effect_execution_supported(dict(ability.get("effect", {})))
            )
            if not is_targeted_etb and automatic_ability_execution_supported(
                ability, entering=True
            ):
                continue
            if not is_targeted_etb or self._ability_choice_variants(ability) != ({},):
                return ()

            target_sets = self._target_sets(self.player_id, schema)
            if not target_sets:
                return ()
            additions: list[tuple[dict[str, Any], dict[str, Any]]] = []
            ability_id = str(ability["ability_id"])
            for targets in target_sets:
                minimum = int(schema.get("min", 0))
                if len(targets) < minimum:
                    continue
                object_ids = [target.object_id for target in targets]
                handles = list(self._public_target_handles(targets))
                selected_internal: str | list[str]
                selected_public: str | list[str]
                if len(object_ids) == 1:
                    selected_internal = object_ids[0]
                    selected_public = handles[0]
                else:
                    selected_internal = object_ids
                    selected_public = handles
                additions.append(
                    (
                        {"trigger_targets": {ability_id: selected_internal}},
                        {"trigger_target_handles": {ability_id: selected_public}},
                    )
                )
            if not additions:
                return ()
            variants = tuple(
                (
                    self._merge_choices(base_choices, added_choices),
                    {**base_public, **added_public},
                )
                for base_choices, base_public in variants
                for added_choices, added_public in additions
            )
        return variants

    def _candidate_casts(self) -> list[_InternalAction]:
        result: list[_InternalAction] = []
        for obj in self.executor.state.objects.values():
            if obj.retired or obj.ceased_to_exist or obj.owner != self.player_id:
                continue
            if obj.zone not in {Zone.HAND, Zone.COMMAND, Zone.GRAVEYARD, Zone.EXILE}:
                continue
            faces = obj.current_characteristics.get("faces", [])
            for face_index, face in enumerate(faces):
                card_types = set(str(value) for value in face.get("card_types", ()))
                entry_variants: tuple[tuple[dict[str, Any], dict[str, Any]], ...] = (({}, {}),)
                if card_types.intersection(PERMANENT_TYPES):
                    entry_variants = self._entry_trigger_choice_variants(obj)
                    if not entry_variants:
                        continue
                modes = list(face.get("spell_modes", [])) or [self._permanent_spell_ability()]
                for raw_ability in modes:
                    ability = dict(raw_ability)
                    if not effect_execution_supported(dict(ability.get("effect", {}))):
                        continue
                    permission = str(ability.get("cast_permission", "NORMAL"))
                    if obj.zone is Zone.GRAVEYARD and permission not in {"AFTERMATH", "FLASHBACK"}:
                        continue
                    if permission in {"AFTERMATH", "FLASHBACK"} and obj.zone is not Zone.GRAVEYARD:
                        continue
                    if obj.zone is Zone.EXILE and permission != "FORETELL":
                        continue
                    if permission == "FORETELL":
                        if obj.zone is not Zone.EXILE:
                            continue
                        if not bool(obj.current_characteristics.get("foretold")):
                            continue
                        if obj.current_characteristics.get("foretold_by") != self.player_id:
                            continue
                        if self.executor.state.turn.number <= int(
                            obj.current_characteristics.get("foretold_turn", -1)
                        ):
                            continue
                    if "Land" in card_types:
                        continue
                    instant_speed = "Instant" in card_types or "Flash" in face.get("keywords", ())
                    if not instant_speed and (
                        self.player_id != self.executor.state.turn.active_player_id
                        or self.executor.state.turn.phase not in MAIN_PHASES
                        or bool(self.executor.state.stack)
                    ):
                        continue
                    schema = dict(ability.get("target_schema", {}))
                    effect = dict(ability.get("effect", {}))
                    x_spell = "{X}" in str(face.get("mana_cost", ""))
                    mana_available = sum(
                        int(value)
                        for value in self.executor.state.players[self.player_id].mana_pool.values()
                    )
                    x_values = range(0, mana_available + 1) if x_spell else (0,)
                    for x_value in x_values:
                        target_schema = dict(schema)
                        if effect.get("target_count_from_x"):
                            target_schema["min"] = x_value
                            target_schema["max"] = x_value
                        target_sets = self._target_sets(self.player_id, target_schema)
                        if effect.get("target_count_from_x") and not target_sets:
                            continue
                        by_count: dict[int, list[tuple[Any, ...]]] = {}
                        for targets in target_sets:
                            by_count.setdefault(len(targets), []).append(targets)
                        for spell_choices in self._ability_choice_variants(ability):
                            for entry_choices, entry_public in entry_variants:
                                choices = self._merge_choices(spell_choices, entry_choices)
                                for target_count, same_count_sets in by_count.items():
                                    representative = same_count_sets[0]
                                    probe_arguments = {
                                        "actor": self.player_id,
                                        "card_object_id": obj.object_id,
                                        "targets": representative,
                                        "face": face_index,
                                        "x_value": x_value,
                                        "mode": ability.get("mode"),
                                        "choices": choices,
                                    }
                                    if not self._probe("cast", probe_arguments):
                                        continue
                                    for targets in same_count_sets:
                                        arguments = {**probe_arguments, "targets": targets}
                                        target_handles = self._public_target_handles(targets)
                                        public = ObservedAction(
                                            "",
                                            "CAST",
                                            str(obj.current_characteristics.get("name")),
                                            int(face.get("mana_value", 0)),
                                            self._tags(obj, ability),
                                            target_count,
                                            {
                                                "face": face_index,
                                                "mode": ability.get("mode"),
                                                "x_value": x_value,
                                                "target_handles": target_handles,
                                                "cast_permission": ability.get(
                                                    "cast_permission", "NORMAL"
                                                ),
                                                **self._public_choice_metadata(spell_choices),
                                                **entry_public,
                                            },
                                        )
                                        result.append(_InternalAction("cast", arguments, public))
        return result

    def _candidate_hand_activations(self) -> list[_InternalAction]:
        """Expose one activation; choose a hidden-zone identity at resolution."""

        from mtg_kernel.phase_b_actions import legal_tutor_names

        result: list[_InternalAction] = []
        hand = self.executor.state.zones.get(f"{Zone.HAND.value}:{self.player_id}", [])
        for object_id in hand:
            obj = self.executor.state.objects[object_id]
            for raw_ability in obj.current_characteristics.get("abilities", []):
                ability = dict(raw_ability)
                if ability.get("kind") != "ACTIVATED":
                    continue
                cost = dict(ability.get("cost", {}))
                if int(cost.get("discard", 0)) != 1:
                    continue
                effect = dict(ability.get("effect", {}))
                if not effect_execution_supported(effect):
                    continue
                kind = str(effect.get("kind", ""))
                tutor_names: tuple[str, ...] = ()
                choice_variants: tuple[dict[str, Any], ...]
                if kind in {"TRANSMUTE", "TYPECYCLE"}:
                    tutor_names = legal_tutor_names(self.executor, self.player_id, effect)
                    choice_variants = ({},)
                else:
                    choice_variants = self._ability_choice_variants(ability)
                schema = dict(ability.get("target_schema", {}))
                for targets in self._target_sets(self.player_id, schema):
                    for choices in choice_variants:
                        arguments = {
                            "actor": self.player_id,
                            "source_id": obj.object_id,
                            "ability_id": str(ability["ability_id"]),
                            "targets": targets,
                            "choices": choices,
                        }
                        if not self._probe("activate_hand", arguments):
                            continue
                        metadata: dict[str, Any] = {
                            "ability_id": ability["ability_id"],
                            "target_handles": self._public_target_handles(targets),
                        }
                        if tutor_names:
                            metadata["eligible_tutor_identities"] = tutor_names
                            metadata["choice_timing"] = "RESOLUTION"
                        result.append(
                            _InternalAction(
                                "activate_hand",
                                arguments,
                                ObservedAction(
                                    "",
                                    "ACTIVATE_HAND",
                                    str(obj.current_characteristics.get("name", "")),
                                    0,
                                    self._tags(obj, ability),
                                    len(targets),
                                    metadata,
                                ),
                            )
                        )
        return result

    def refresh(self) -> tuple[dict[str, Any], tuple[ObservedAction, ...]]:
        tracker = getattr(self.executor, "combo_access_tracker", None)
        if tracker is not None:
            tracker.observe(self.executor)
        return super().refresh()

    def execute(self, generation: int, action_handle: str) -> None:
        super().execute(generation, action_handle)
        tracker = getattr(self.executor, "combo_access_tracker", None)
        if tracker is not None:
            tracker.observe(self.executor)


__all__ = ["ActionBroker", "ObservedAction"]
