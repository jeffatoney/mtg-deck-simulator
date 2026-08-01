"""Opaque legal-action broker backed by production-executor probes."""

from __future__ import annotations

import hashlib
from copy import deepcopy
from dataclasses import dataclass
from itertools import combinations
from typing import Any

from mtg_kernel.engine import GameExecutor
from mtg_kernel.errors import IllegalAction, UnsupportedCapability
from mtg_kernel.hashing import state_hash
from mtg_kernel.land_actions import play_land
from mtg_kernel.models import GameObject, TargetRef, Zone
from mtg_kernel.observation import ObservationService


@dataclass(frozen=True)
class ObservedAction:
    handle: str
    kind: str
    identity: str | None
    mana_value: int
    tags: tuple[str, ...]
    target_count: int
    metadata: dict[str, Any]


@dataclass(frozen=True)
class _InternalAction:
    operation: str
    arguments: dict[str, Any]
    public: ObservedAction


class ActionBroker:
    """Generate only actions accepted by a cloned production executor."""

    def __init__(self, executor: GameExecutor, player_id: str) -> None:
        self.executor = executor
        self.player_id = player_id
        self.observations = ObservationService(executor.state)
        self.generation = 0
        self._state_token = ""
        self._actions: dict[str, _InternalAction] = {}

    def _handle(self, index: int, operation: str) -> str:
        return hashlib.sha256(
            f"action:{self.player_id}:{self.generation}:{index}:{operation}:{self._state_token}".encode()
        ).hexdigest()[:24]

    @staticmethod
    def _tags(obj: GameObject, ability: dict[str, Any] | None = None) -> tuple[str, ...]:
        tags = set(str(value) for value in obj.current_characteristics.get("card_types", []))
        tags.update(str(value) for value in obj.current_characteristics.get("subtypes", []))
        if ability:
            effect = ability.get("effect", {})
            if isinstance(effect, dict):
                tags.add(str(effect.get("kind", "NONE")))
            tags.add(str(ability.get("kind", "")))
        name = str(obj.current_characteristics.get("name", ""))
        if name in {
            "Glint-Horn Buccaneer",
            "Dualcaster Mage",
            "Twinflame",
            "Electroduplicate",
            "Curiosity",
            "Niv-Mizzet, the Firemind",
            "Lightning-Rig Crew",
            "Crab Umbra",
            "Psychosis Crawler",
            "Malcolm, Keen-Eyed Navigator",
        }:
            tags.add("COMBO_COMPONENT")
        if tags.intersection(
            {"COUNTER_IF", "COUNTER", "COUNTER_UNLESS_PAY", "COUNTER_TARGETING_CONTROLLER"}
        ):
            tags.add("PROTECTION")
        if ability and ability.get("mana_ability"):
            tags.add("MANA_ABILITY")
        return tuple(sorted(value for value in tags if value))

    def _public_target_handles(self, targets: tuple[TargetRef, ...]) -> tuple[str, ...]:
        result: list[str] = []
        for target in targets:
            handle = self.observations.handle_for_object(
                self.player_id, self.generation, target.object_id
            )
            if handle is None:
                raise IllegalAction("a legal action target is not visible to the acting policy")
            result.append(handle)
        return tuple(result)

    def _target_sets(self, actor: str, schema: dict[str, Any]) -> tuple[tuple[TargetRef, ...], ...]:
        minimum = int(schema.get("min", 0))
        maximum_raw = schema.get("max")
        candidates = self.executor._legal_candidates(actor, schema)
        maximum = len(candidates) if maximum_raw is None else min(int(maximum_raw), len(candidates))
        values: list[tuple[TargetRef, ...]] = []
        for count in range(minimum, maximum + 1):
            values.extend(
                tuple(TargetRef(candidate.object_id) for candidate in selected)
                for selected in combinations(candidates, count)
            )
        return tuple(values) if values else ((),)

    @staticmethod
    def _invoke(executor: GameExecutor, operation: str, arguments: dict[str, Any]) -> None:
        if operation == "play_land":
            play_land(executor, record=False, **deepcopy(arguments))
            return
        method = getattr(executor, operation)
        method(**deepcopy(arguments))

    def _probe(self, operation: str, arguments: dict[str, Any]) -> bool:
        state = deepcopy(self.executor.state)
        probe = GameExecutor(state, self.executor.seed, replaying=True)
        try:
            self._invoke(probe, operation, arguments)
        except (IllegalAction, UnsupportedCapability, KeyError, ValueError):
            return False
        return True

    @staticmethod
    def _permanent_spell_ability() -> dict[str, Any]:
        return {
            "ability_id": "rules:permanent-spell",
            "kind": "SPELL",
            "mode": "default",
            "target_schema": {"kind": "NONE", "min": 0, "max": 0, "unique": True},
            "effect": {"kind": "NONE"},
        }

    def _candidate_casts(self) -> list[_InternalAction]:
        result: list[_InternalAction] = []
        for obj in self.executor.state.objects.values():
            if obj.retired or obj.ceased_to_exist or obj.owner != self.player_id:
                continue
            if obj.zone not in {Zone.HAND, Zone.COMMAND, Zone.GRAVEYARD, Zone.EXILE}:
                continue
            faces = obj.current_characteristics.get("faces", [])
            for face_index, face in enumerate(faces):
                modes = list(face.get("spell_modes", [])) or [self._permanent_spell_ability()]
                for ability in modes:
                    schema = dict(ability.get("target_schema", {}))
                    for targets in self._target_sets(self.player_id, schema):
                        arguments = {
                            "actor": self.player_id,
                            "card_object_id": obj.object_id,
                            "targets": targets,
                            "face": face_index,
                            "x_value": 0,
                            "mode": ability.get("mode"),
                            "choices": {},
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
                            },
                        )
                        result.append(_InternalAction("cast", arguments, public))
        return result

    def _candidate_activations(self) -> list[_InternalAction]:
        result: list[_InternalAction] = []
        for obj in self.executor.state.objects.values():
            if obj.retired or obj.zone is not Zone.BATTLEFIELD or obj.controller != self.player_id:
                continue
            for ability in obj.current_characteristics.get("abilities", []):
                if ability.get("kind") != "ACTIVATED":
                    continue
                schema = dict(ability.get("target_schema", {}))
                for targets in self._target_sets(self.player_id, schema):
                    arguments = {
                        "actor": self.player_id,
                        "source_id": obj.object_id,
                        "ability": str(ability["ability_id"]),
                        "targets": targets,
                        "choices": {},
                    }
                    if not self._probe("activate", arguments):
                        continue
                    target_handles = self._public_target_handles(targets)
                    public = ObservedAction(
                        "",
                        "ACTIVATE",
                        str(obj.current_characteristics.get("name")),
                        0,
                        self._tags(obj, ability),
                        len(targets),
                        {
                            "ability_id": ability["ability_id"],
                            "target_handles": target_handles,
                        },
                    )
                    result.append(_InternalAction("activate", arguments, public))
        return result

    def refresh(self) -> tuple[dict[str, Any], tuple[ObservedAction, ...]]:
        observation = self.observations.observe_for_policy(self.player_id)
        self.generation = int(observation["generation"])
        self._state_token = state_hash(self.executor.state)
        candidates: list[_InternalAction] = []
        hand = self.executor.state.zones.get(f"HAND:{self.player_id}", [])
        for object_id in hand:
            obj = self.executor.state.objects[object_id]
            if "Land" not in obj.current_characteristics.get("card_types", []):
                continue
            arguments = {"actor": self.player_id, "card_object_id": object_id, "choices": {}}
            if self._probe("play_land", arguments):
                candidates.append(
                    _InternalAction(
                        "play_land",
                        arguments,
                        ObservedAction(
                            "",
                            "PLAY_LAND",
                            str(obj.current_characteristics.get("name")),
                            0,
                            self._tags(obj),
                            0,
                            {},
                        ),
                    )
                )
        candidates.extend(self._candidate_casts())
        candidates.extend(self._candidate_activations())
        pass_arguments = {"player_id": self.player_id}
        if self._probe("pass_priority", pass_arguments):
            candidates.append(
                _InternalAction(
                    "pass_priority",
                    pass_arguments,
                    ObservedAction("", "PASS_PRIORITY", None, 0, (), 0, {}),
                )
            )

        self._actions.clear()
        public: list[ObservedAction] = []
        for index, item in enumerate(candidates):
            handle = self._handle(index, item.operation)
            observed = ObservedAction(
                handle,
                item.public.kind,
                item.public.identity,
                item.public.mana_value,
                item.public.tags,
                item.public.target_count,
                dict(item.public.metadata),
            )
            self._actions[handle] = _InternalAction(item.operation, item.arguments, observed)
            public.append(observed)
        return observation, tuple(public)

    def execute(self, generation: int, action_handle: str) -> None:
        if generation != self.generation or state_hash(self.executor.state) != self._state_token:
            raise IllegalAction("legal-action handles have been revoked")
        item = self._actions.get(action_handle)
        if item is None:
            raise IllegalAction("unknown legal-action handle")
        self._invoke(self.executor, item.operation, item.arguments)
        self._actions.clear()
        self._state_token = ""
