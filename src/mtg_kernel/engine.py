"""Public production executor with Phase B atomicity and terminal hardening."""

from __future__ import annotations

from copy import deepcopy
import hashlib
from itertools import combinations
from typing import Any

from mtg_kernel.engine_core import MAIN_PHASES, PERMANENT_TYPES
from mtg_kernel.engine_core import GameExecutor as _CoreGameExecutor
from mtg_kernel.errors import IllegalAction, UnsupportedCapability
from mtg_kernel.models import (
    Action,
    Choice,
    CopyKind,
    GameObject,
    GameState,
    ObjectKind,
    TargetRef,
    Zone,
)
from mtg_kernel.observation import ObservationService
from mtg_kernel.strategic_choices import (
    PublicCard,
    SpellCopyTargetRequest,
    StrategicChoiceProvider,
    require_provider,
)


class HardenedGameExecutor(_CoreGameExecutor):
    """Runtime executor adding Slice 3 atomicity and terminal protections."""

    def __init__(
        self,
        state: GameState,
        seed: str = "phase-a",
        *,
        replaying: bool = False,
        strategic_choice_provider: StrategicChoiceProvider | None = None,
    ) -> None:
        super().__init__(state, seed, replaying=replaying)
        self.strategic_choice_provider = strategic_choice_provider

    def bind_strategic_choice_provider(
        self,
        provider: StrategicChoiceProvider,
    ) -> StrategicChoiceProvider:
        """Bind one declared strategic provider to this executor instance."""

        self.strategic_choice_provider = provider
        return provider

    def _strategic_observation(self, actor_id: str) -> dict[str, Any]:
        observation = ObservationService(self.state).observe_for_policy(actor_id)
        observation["mana_pool"] = dict(self.state.players[actor_id].mana_pool)
        observation["land_played_this_turn"] = bool(
            getattr(self.state.turn, "land_played_this_turn", False)
        )
        return observation

    @staticmethod
    def _strategic_handle(request_id: str, object_id: str) -> str:
        return hashlib.sha256(f"strategic-choice:{request_id}:{object_id}".encode()).hexdigest()[
            :24
        ]

    @staticmethod
    def _strategic_effect_kinds(obj: GameObject) -> tuple[str, ...]:
        kinds: set[str] = set()
        for ability in obj.current_characteristics.get("abilities", ()):
            effect = ability.get("effect", {})
            if not isinstance(effect, dict):
                continue
            kind = str(effect.get("kind", "")).strip()
            if kind:
                kinds.add(kind)
            for child in effect.get("effects", ()):
                if isinstance(child, dict):
                    child_kind = str(child.get("kind", "")).strip()
                    if child_kind:
                        kinds.add(child_kind)
        return tuple(sorted(kinds))

    def _choose_copy_targets(
        self,
        source: GameObject | None,
        original: GameObject,
        action: Action,
        effect: dict[str, Any],
    ) -> tuple[tuple[TargetRef, ...] | None, dict[str, Any] | None]:
        original_action = self._created_action(original)
        if not bool(effect.get("may_choose_new_targets")) or not original_action.targets:
            return None, None
        schema = dict(original_action.metadata.get("target_schema", {}))
        count = len(original_action.targets)
        candidates = self._legal_candidates(action.actor_id, schema)
        legal_sets = tuple(
            tuple(TargetRef(candidate.object_id) for candidate in selected)
            for selected in combinations(candidates, count)
        )
        if not legal_sets:
            return None, None
        request_id = self.identity.new_id("strategic-request")
        handles = {
            candidate.object_id: self._strategic_handle(request_id, candidate.object_id)
            for candidate in candidates
        }
        legal_handle_sets = tuple(
            tuple(handles[target.object_id] for target in targets) for targets in legal_sets
        )
        original_handles = tuple(
            handles[target.object_id]
            for target in original_action.targets
            if target.object_id in handles
        )
        if len(original_handles) != len(original_action.targets):
            raise IllegalAction("original copy targets are no longer legal")
        source_identity = ""
        if source is not None and source.source_object_id:
            source_object = self.state.objects.get(source.source_object_id)
            if source_object is not None:
                source_identity = str(source_object.current_characteristics.get("name", ""))
        public_targets = tuple(
            PublicCard(
                handle=handles[candidate.object_id],
                identity=str(candidate.current_characteristics.get("name", "")),
                mana_value=int(candidate.current_characteristics.get("mana_value", 0)),
                card_types=tuple(
                    str(value) for value in candidate.current_characteristics.get("card_types", ())
                ),
                effect_kinds=self._strategic_effect_kinds(candidate),
            )
            for candidate in candidates
        )
        provider = require_provider(
            self.strategic_choice_provider,
            "spell-copy target selection",
        )
        selection = provider.choose_spell_copy_targets(
            SpellCopyTargetRequest(
                request_id=request_id,
                actor_id=action.actor_id,
                source_identity=source_identity,
                copied_spell_identity=str(original.current_characteristics.get("name", "")),
                turn_number=self.state.turn.number,
                observation=self._strategic_observation(action.actor_id),
                original_target_handles=original_handles,
                legal_targets=public_targets,
                legal_target_sets=legal_handle_sets,
            )
        )
        if selection.target_handles not in legal_handle_sets:
            raise IllegalAction("strategic provider selected an illegal copy target set")
        objects_by_handle = {handles[obj.object_id]: obj for obj in candidates}
        selected_targets = tuple(
            TargetRef(objects_by_handle[handle].object_id) for handle in selection.target_handles
        )
        record = {
            "target_handles": list(selection.target_handles),
            "evaluator_id": selection.evaluator_id,
            "evaluator_sha256": selection.evaluator_sha256,
            "diagnostics": dict(selection.diagnostics),
            "chosen_at": "RESOLUTION",
        }
        return selected_targets, record

    def _apply_effect(
        self,
        source: GameObject | None,
        action: Action,
        effect: dict[str, Any],
        targets: list[GameObject],
        choices: dict[str, Any],
    ) -> None:
        if str(effect.get("kind", "NONE")) != "CREATE_SPELL_COPY" or not targets:
            super()._apply_effect(source, action, effect, targets, choices)
            return
        new_targets_data = choices.get("copy_targets")
        choice_record: dict[str, Any] | None = None
        new_targets: tuple[TargetRef, ...] | None
        if isinstance(new_targets_data, list):
            new_targets = tuple(self._target_from_data(dict(item)) for item in new_targets_data)
        else:
            new_targets, choice_record = self._choose_copy_targets(
                source, targets[0], action, effect
            )
        self.copy_spell(
            targets[0],
            action.actor_id,
            new_targets,
            action,
            choice_record=choice_record,
        )

    def copy_spell(
        self,
        original: GameObject,
        controller: str,
        new_targets: tuple[TargetRef, ...] | None,
        cause_action: Action,
        *,
        choice_record: dict[str, Any] | None = None,
    ) -> GameObject:
        if original.zone is not Zone.STACK or original.object_kind not in {
            ObjectKind.SPELL,
            ObjectKind.SPELL_COPY,
        }:
            raise IllegalAction("spell-copy source must be a spell on the stack")
        original_action = self._created_action(original)
        targets = new_targets if new_targets is not None else original_action.targets
        schema = dict(original_action.metadata.get("target_schema", {}))
        self._validate_targets(controller, targets, schema)
        choice_event = self._event("COPY_TARGET_DECISION", cause_action)
        selected_choice: Any
        if choice_record is not None:
            selected_choice = dict(choice_record)
        elif new_targets is not None:
            selected_choice = [target.object_id for target in targets]
        else:
            selected_choice = "RETAIN_ORIGINAL_TARGETS"
        choice = Choice(
            self.identity.new_id("choice"),
            controller,
            "COPY_TARGETS",
            selected_choice,
            choice_event.event_id,
        )
        self.state.choices.append(choice)
        action = Action(
            self.identity.new_id("action"),
            "COPY_SPELL",
            controller,
            original.object_id,
            targets,
            original_action.modes,
            original_action.x_value,
            {},
            {
                "ability_id": original_action.metadata.get("ability_id"),
                "face": original_action.metadata.get("face", 0),
                "target_schema": schema,
                "choices": dict(original_action.metadata.get("choices", {})),
            },
        )
        self.state.actions.append(action)
        event = self._event("SPELL_COPIED", action, copied_from=original.object_id)
        copy = GameObject(
            self.identity.new_id("object"),
            ObjectKind.SPELL_COPY,
            Zone.STACK,
            controller,
            controller,
            copied_from_object_id=original.object_id,
            copy_kind=CopyKind.SPELL_COPY,
            copiable_values_snapshot_id=self.identity.new_id("copy-snapshot"),
            copy_creation_event_id=event.event_id,
            copy_target_choice_id=choice.choice_id,
            created_by_event_id=event.event_id,
            current_characteristics=deepcopy(original.current_characteristics),
            identity_visible_to=set(self.state.players),
            was_cast=False,
        )
        self.state.objects[copy.object_id] = copy
        self.zones.register(copy)
        self.state.pending_actions.append(action.action_id)
        return copy

    def copy_permanent_token(
        self,
        original: GameObject,
        controller: str,
        cause_action: Action,
        *,
        haste: bool,
        delayed: str,
    ) -> GameObject:
        if not self._is_permanent(original):
            raise IllegalAction("token-copy source must be a permanent")
        event = self._event("TOKEN_COPY_CREATED", cause_action, copied_from=original.object_id)
        characteristics = deepcopy(original.current_characteristics)
        if haste:
            keywords = set(characteristics.get("keywords", []))
            keywords.add("Haste")
            characteristics["keywords"] = sorted(keywords)
        token = GameObject(
            self.identity.new_id("object"),
            ObjectKind.TOKEN_OBJECT,
            Zone.BATTLEFIELD,
            controller,
            controller,
            copy_kind=CopyKind.TOKEN_COPY,
            copied_from_object_id=original.object_id,
            copiable_values_snapshot_id=self.identity.new_id("copy-snapshot"),
            copy_creation_event_id=event.event_id,
            current_characteristics=characteristics,
            permanent_status={"tap": "UNTAPPED", "face": "FACE_UP", "phase": "PHASED_IN"},
            identity_visible_to=set(self.state.players),
        )
        self.state.objects[token.object_id] = token
        self.zones.register(token)
        self._queue_etb(token)
        if delayed == "EXILE_AT_NEXT_END_STEP":
            delayed_event = self._event("DELAYED_TRIGGER_CREATED", cause_action)
            trigger = GameObject(
                self.identity.new_id("object"),
                ObjectKind.TRIGGERED_ABILITY,
                Zone.NONE,
                None,
                controller,
                source_object_id=token.object_id,
                created_by_event_id=delayed_event.event_id,
                current_characteristics={
                    "ability": {
                        "ability_id": "twinflame:delayed-exile",
                        "kind": "TRIGGERED",
                        "trigger": "NEXT_END_STEP",
                        "target_schema": {"kind": "NONE", "min": 0, "max": 0, "unique": True},
                        "effect": {
                            "kind": "EXILE_OBJECTS",
                            "objects": [self._target_data(TargetRef(token.object_id))],
                        },
                    },
                    "trigger_context": {},
                    "choice_hints": {},
                },
                was_cast=False,
            )
            self.state.objects[trigger.object_id] = trigger
            self.state.delayed_triggers.append(trigger.object_id)
        return token

    def cast(
        self,
        actor: str,
        card_object_id: str,
        targets: tuple[TargetRef, ...] = (),
        face: int = 0,
        x_value: int = 0,
        mode: str | None = None,
        choices: dict[str, Any] | None = None,
        *,
        _record: bool = True,
    ) -> GameObject:
        card = self.state.objects[card_object_id]
        face_data = self._selected_face(card, face)
        spell_ability = self._selected_spell_ability(face_data, mode)
        effect = dict(spell_ability.get("effect", {}))
        if effect.get("target_count_from_x") and len(targets) != x_value:
            raise IllegalAction("the number of targets must equal the chosen value of X")
        return super().cast(
            actor,
            card_object_id,
            targets,
            face,
            x_value,
            mode,
            choices,
            _record=_record,
        )

    def check_state_based_actions(self) -> None:
        super().check_state_based_actions()
        if self.state.terminal.status != "TERMINAL":
            return
        for trigger_id in self.state.waiting_triggers:
            trigger = self.state.objects[trigger_id]
            trigger.retired = True
            trigger.ceased_to_exist = True
        self.state.waiting_triggers.clear()


_CORE_INITIALIZER = _CoreGameExecutor.__init__


def _guarded_core_initializer(
    self: _CoreGameExecutor,
    state: GameState,
    seed: str = "phase-a",
    *,
    replaying: bool = False,
) -> None:
    if type(self) is _CoreGameExecutor:
        raise UnsupportedCapability(
            "internal executor core cannot be instantiated directly; "
            "use mtg_kernel.engine.GameExecutor"
        )
    _CORE_INITIALIZER(self, state, seed, replaying=replaying)


setattr(_CoreGameExecutor, "__init__", _guarded_core_initializer)


GameExecutor = HardenedGameExecutor


__all__ = ["GameExecutor", "MAIN_PHASES", "PERMANENT_TYPES"]
