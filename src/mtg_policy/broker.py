"""Public opaque legal-action broker with explicit ETB choice variants."""

from __future__ import annotations

from typing import Any

from mtg_kernel.models import GameObject, TargetRef, Zone
from mtg_kernel.phase_b_actions import (
    automatic_ability_execution_supported,
    effect_execution_supported,
)
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

    def _entry_trigger_choice_variants(
        self, obj: GameObject
    ) -> tuple[tuple[dict[str, Any], dict[str, Any]], ...]:
        """Enumerate policy-visible choices for supported targeted ETB triggers.

        Automatic ETB behavior that needs no policy decision remains implicit.  Any
        unsupported automatic ability still suppresses the cast.  Targeted,
        nonoptional ETB triggers with supported effects are made explicit in the
        cast action, using opaque public handles while retaining object IDs only in
        the broker's private execution arguments.
        """

        variants: tuple[tuple[dict[str, Any], dict[str, Any]], ...] = (({}, {}),)
        for raw_ability in obj.current_characteristics.get("abilities", ()):
            ability = dict(raw_ability)
            if automatic_ability_execution_supported(ability, entering=True):
                continue
            if (
                ability.get("kind") != "TRIGGERED"
                or ability.get("trigger") != "ETB"
                or ability.get("optional")
                or not effect_execution_supported(dict(ability.get("effect", {})))
            ):
                return ()
            if self._ability_choice_variants(ability) != ({},):
                return ()

            schema = dict(ability.get("target_schema", {}))
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
                entry_variants: tuple[tuple[dict[str, Any], dict[str, Any]], ...] = (
                    (({}, {}),)
                )
                if card_types.intersection(PERMANENT_TYPES):
                    entry_variants = self._entry_trigger_choice_variants(obj)
                    if not entry_variants:
                        continue
                modes = list(face.get("spell_modes", [])) or [self._permanent_spell_ability()]
                for raw_ability in modes:
                    ability = dict(raw_ability)
                    if not effect_execution_supported(dict(ability.get("effect", {}))):
                        continue
                    schema = dict(ability.get("target_schema", {}))
                    for targets in self._target_sets(self.player_id, schema):
                        for spell_choices in self._ability_choice_variants(ability):
                            for entry_choices, entry_public in entry_variants:
                                choices = self._merge_choices(spell_choices, entry_choices)
                                arguments = {
                                    "actor": self.player_id,
                                    "card_object_id": obj.object_id,
                                    "targets": targets,
                                    "face": face_index,
                                    "x_value": 0,
                                    "mode": ability.get("mode"),
                                    "choices": choices,
                                }
                                if not self._probe("cast", arguments):
                                    continue
                                target_handles = self._public_target_handles(targets)
                                public = ObservedAction(
                                    "",
                                    "CAST",
                                    str(obj.current_characteristics.get("name")),
                                    int(face.get("mana_value", 0)),
                                    self._tags(obj, ability),
                                    len(targets),
                                    {
                                        "face": face_index,
                                        "mode": ability.get("mode"),
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


__all__ = ["ActionBroker", "ObservedAction"]
