"""Deterministic candidate policies over hidden-information-safe observations."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mtg_policy.broker import ObservedAction
from mtg_policy.config import PolicyBundle
from mtg_policy.public_actions import (
    PolicyActionView,
    PublicActionKey,
    public_action_classes,
    resolve_selected_action_handle,
)

ROOT = Path(__file__).resolve().parents[2]
_GUARDRAIL_PATH = ROOT / "docs/spec/phase-c/NO_OPPONENT_POLICY_GUARDRAIL.json"

_FORBIDDEN_OBSERVATION_KEYS = {
    "library_order",
    "future_events",
    "future_random_outcomes",
    "card_instance_ids",
    "object_ids",
}

# In the frozen no-opponent-action model these effect kinds have no represented
# positive consequence when every selected target is P0-owned/controlled. They
# remain legal and remain visible to EXPLORATORY; this is STANDARD ranking only.
_NO_OPPONENT_DEFENSIVE_SELF_EFFECTS = frozenset(
    {
        "COUNTER",
        "COUNTER_IF",
        "COUNTER_UNLESS_PAY",
        "COUNTER_UNLESS_PAY_EXILE",
        "COUNTER_TARGETING_CONTROLLER",
        "LIBRARY_SECOND",
    }
)

# Arcane Denial is deliberately distinct: its delayed draws are represented by
# the frozen evaluator, so the legal action stays searchable. STANDARD should not
# be forced into it merely because legacy PASS carried a -100 score, however.
_NO_OPPONENT_NEUTRAL_SELF_EFFECTS = frozenset({"COUNTER_WITH_DELAYED_DRAWS"})
_NO_OPPONENT_REVIEWED_SELF_EFFECTS = (
    _NO_OPPONENT_DEFENSIVE_SELF_EFFECTS | _NO_OPPONENT_NEUTRAL_SELF_EFFECTS
)


def _validated_opponent_interaction_mode(requested: bool) -> bool:
    """Bind the reviewed no-opponent mode to the frozen Phase C machine config.

    Interactive use remains the default and needs no Phase C dependency. Requesting
    the special no-opponent ranking is fail-closed: the guardrail must name the
    canonical config field, the config must contain a boolean, and it must equal the
    guardrail-required value. A future study-config change therefore cannot silently
    leave STANDARD in a stale hardcoded mode.
    """
    if requested:
        return True
    guardrail = json.loads(_GUARDRAIL_PATH.read_text(encoding="utf-8"))
    binding = guardrail.get("model_binding")
    if not isinstance(binding, dict):
        raise ValueError("no-opponent policy guardrail omits its model binding")
    if binding.get("json_pointer") != "/game_model/opponent_interaction_modeled":
        raise ValueError("no-opponent policy guardrail points at an unexpected config field")
    config_path = binding.get("config_path")
    if not isinstance(config_path, str) or not config_path:
        raise ValueError("no-opponent policy guardrail omits its config path")
    config = json.loads((ROOT / config_path).read_text(encoding="utf-8"))
    game_model = config.get("game_model")
    if not isinstance(game_model, dict):
        raise ValueError("Phase C config omits game_model for no-opponent policy binding")
    actual = game_model.get("opponent_interaction_modeled")
    required = binding.get("required_value")
    if not isinstance(actual, bool) or not isinstance(required, bool):
        raise ValueError("no-opponent policy binding values must be booleans")
    if actual != required:
        raise ValueError("no-opponent policy guardrail disagrees with the frozen Phase C config")
    return actual


@dataclass(frozen=True)
class KeepDecision:
    keep: bool
    hand_size: int
    reason: str
    features: dict[str, int]


class StandardPolicy:
    """One precommitted strategy hypothesis, not an asserted optimal policy."""

    def __init__(self, bundle: PolicyBundle, *, opponent_interaction_modeled: bool = True) -> None:
        self.bundle = bundle
        self.opponent_interaction_modeled = _validated_opponent_interaction_mode(
            opponent_interaction_modeled
        )

    @staticmethod
    def hand_features(
        card_names: tuple[str, ...], card_types: tuple[tuple[str, ...], ...]
    ) -> dict[str, int]:
        if len(card_names) != len(card_types):
            raise ValueError("hand names and type records differ in length")
        lands = sum("Land" in types for types in card_types)
        mana = lands + sum(
            name
            in {
                "Sol Ring",
                "Arcane Signet",
                "Fellwar Stone",
                "Mind Stone",
                "Izzet Signet",
                "Prismatic Lens",
            }
            for name in card_names
        )
        tutors = sum(
            name
            in {
                "Drift of Phantasms",
                "Muddle the Mixture",
                "Dizzy Spell",
                "Step Through",
                "Vedalken Aethermage",
                "Long-Term Plans",
                "Invert // Invent",
            }
            for name in card_names
        )
        combo = sum(
            name
            in {
                "Glint-Horn Buccaneer",
                "Dualcaster Mage",
                "Twinflame",
                "Electroduplicate",
                "Curiosity",
                "Niv-Mizzet, the Firemind",
            }
            for name in card_names
        )
        return {
            "lands": lands,
            "mana": mana,
            "tutors": tutors,
            "combo": combo,
            "actions": len(card_names) - lands,
        }

    def decide_keep(
        self,
        hand_size: int,
        card_names: tuple[str, ...],
        card_types: tuple[tuple[str, ...], ...],
    ) -> KeepDecision:
        if hand_size not in {4, 5, 6, 7} or len(card_names) != hand_size:
            raise ValueError("mulligan policy requires an exact 7/6/5/4-card hand")
        features = self.hand_features(card_names, card_types)
        style = str(self.bundle.value("mulligan_style"))
        if hand_size == 4:
            keep = features["mana"] >= 2 and features["actions"] >= 1
        elif style == "aggressive":
            keep = features["mana"] >= 2 and (
                features["combo"] + features["tutors"] >= 1 or features["mana"] >= 3
            )
        elif style == "selective":
            keep = 2 <= features["lands"] <= 4 and features["actions"] >= 1
        else:
            raise ValueError(f"unsupported mulligan hypothesis: {style}")
        return KeepDecision(
            keep,
            hand_size,
            f"{self.bundle.policy_config_id}:{style}:{'keep' if keep else 'mulligan'}",
            features,
        )

    @staticmethod
    def _validate_observation(observation: dict[str, Any]) -> None:
        forbidden = _FORBIDDEN_OBSERVATION_KEYS.intersection(observation)
        if forbidden:
            raise ValueError(f"policy observation exposes forbidden keys: {sorted(forbidden)}")
        if "generation" not in observation or "turn" not in observation:
            raise ValueError("policy observation is incomplete")

    @staticmethod
    def _targets_are_all_actor_owned_or_controlled(
        observation: dict[str, Any], action: PolicyActionView
    ) -> bool:
        player = observation.get("player")
        if not isinstance(player, str) or not player:
            raise ValueError("no-opponent policy observation omits the acting player")
        target_handles = action.metadata.get("target_handles")
        if not isinstance(target_handles, (list, tuple)) or not target_handles:
            raise ValueError("reviewed no-opponent self-action omits target handles")
        raw_objects = observation.get("objects")
        if not isinstance(raw_objects, (list, tuple)):
            raise ValueError("no-opponent policy observation omits visible objects")
        objects_by_handle = {
            str(raw["handle"]): raw
            for raw in raw_objects
            if isinstance(raw, dict) and raw.get("handle") is not None
        }
        for raw_handle in target_handles:
            handle = str(raw_handle)
            if handle not in objects_by_handle:
                raise ValueError(
                    f"reviewed no-opponent self-action target handle is unresolved: {handle}"
                )
            raw = objects_by_handle[handle]
            if raw.get("controller") != player and raw.get("owner") != player:
                return False
        return True

    def _no_opponent_self_class(self, observation: dict[str, Any], action: PolicyActionView) -> str:
        if self.opponent_interaction_modeled:
            return "INTERACTIVE"
        effect_kinds = _NO_OPPONENT_REVIEWED_SELF_EFFECTS.intersection(action.tags)
        if not effect_kinds:
            return "ORDINARY"
        if not self._targets_are_all_actor_owned_or_controlled(observation, action):
            return "ORDINARY"
        if effect_kinds.intersection(_NO_OPPONENT_DEFENSIVE_SELF_EFFECTS):
            return "DEFENSIVE_SELF_ONLY"
        return "NEUTRAL_SELF_TRADEOFF"

    def choose_optional_trigger(self, effect_kind: str) -> bool:
        """Choose a supported optional trigger from public effect classification.

        The exact deck currently has one optional trigger: Curiosity's card draw.
        Keep this effect-based and fail closed so a future optional effect cannot be
        silently accepted merely because it was added to the deck.
        """
        if effect_kind == "DRAW":
            return True
        raise ValueError(f"unsupported optional trigger effect for standard policy: {effect_kind}")

    def select_public_action_key(
        self, observation: dict[str, Any], actions: tuple[ObservedAction, ...]
    ) -> PublicActionKey:
        """Select a public semantic action class without receiving capability handles."""

        self._validate_observation(observation)
        if not actions:
            raise ValueError("standard policy received no legal actions")
        action_classes = public_action_classes(actions)

        def score(action: PolicyActionView) -> tuple[int, int, int, int, int, str]:
            tags = set(action.tags)
            value = 0
            if action.kind == "PLAY_LAND":
                value += 80
            if "ADD_MANA" in tags or "MANA_ABILITY" in tags:
                value += 65
            if "COMBO_COMPONENT" in tags:
                value += 50 if self.bundle.value("glint_horn_use") == "cast_for_value" else 35
            if "PROTECTION" in tags and self.opponent_interaction_modeled:
                value += 45 if self.bundle.value("protection_plan") == "protected" else 10
            if "DRAW" in tags or "SCRY" in tags:
                value += 35 if self.bundle.value("velocity_plan") == "cantrip_first" else 20
            if action.identity == "Malcolm, Keen-Eyed Navigator":
                value += 70 if self.bundle.value("development_plan") == "malcolm_first" else 30
            if action.identity == "Breeches, Brazen Plunderer":
                value += 25 if self.bundle.value("breeches_timing") == "early" else 5
            if action.kind == "DECLARE_ATTACKERS":
                attacker_count = int(action.metadata.get("attacker_count", 0))
                opponent_count = int(action.metadata.get("opponent_count", 0))
                pirate_count = int(action.metadata.get("pirate_count", 0))
                identities = {str(item) for item in action.metadata.get("attacker_identities", ())}
                value += 30 * attacker_count + 25 * opponent_count + 20 * pirate_count
                if "Malcolm, Keen-Eyed Navigator" in identities:
                    value += 25
                if "Glint-Horn Buccaneer" in identities:
                    value += 20
                if attacker_count == 0:
                    value -= 60

            if self.opponent_interaction_modeled:
                if action.kind == "PASS_PRIORITY":
                    value -= 100
                return (
                    0,
                    value,
                    0,
                    -action.mana_value,
                    -action.target_count,
                    action.key.canonical_json,
                )

            classification = self._no_opponent_self_class(observation, action)
            if classification == "DEFENSIVE_SELF_ONLY":
                modeled_utility_class = -1
                pass_preference = 0
            elif classification == "NEUTRAL_SELF_TRADEOFF":
                modeled_utility_class = 0
                pass_preference = 0
            elif action.kind == "PASS_PRIORITY":
                modeled_utility_class = 0
                value = 0
                pass_preference = 1
            else:
                # Preserve the existing non-searching baseline for every action
                # outside the reviewed no-opponent self-interaction class. This is
                # why zero-scored productive actions such as Transmute still beat PASS.
                modeled_utility_class = 1
                pass_preference = 0
            return (
                modeled_utility_class,
                value,
                pass_preference,
                -action.mana_value,
                -action.target_count,
                action.key.canonical_json,
            )

        return max(action_classes, key=lambda candidate: score(candidate.action)).key

    def select_action(
        self, observation: dict[str, Any], actions: tuple[ObservedAction, ...]
    ) -> str:
        selected_key = self.select_public_action_key(observation, actions)
        return resolve_selected_action_handle(actions, selected_key)
