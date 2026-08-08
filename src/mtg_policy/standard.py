"""Deterministic candidate policies over hidden-information-safe observations."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any

from mtg_policy.broker import ObservedAction
from mtg_policy.config import PolicyBundle

_FORBIDDEN_OBSERVATION_KEYS = {
    "library_order",
    "future_events",
    "future_random_outcomes",
    "card_instance_ids",
    "object_ids",
}


@dataclass(frozen=True)
class KeepDecision:
    keep: bool
    hand_size: int
    reason: str
    features: dict[str, int]


class StandardPolicy:
    """One precommitted strategy hypothesis, not an asserted optimal policy."""

    def __init__(self, bundle: PolicyBundle) -> None:
        self.bundle = bundle

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
    def _public_action_tiebreak(action: ObservedAction) -> str:
        """Return a stable tie-break derived only from policy-visible action semantics.

        Broker handles are revocable capability tokens bound to the full engine state.
        They must never become a strategic preference because their state binding can
        include information that is intentionally absent from the policy observation.
        """

        public = {
            "identity": action.identity,
            "kind": action.kind,
            "mana_value": action.mana_value,
            "metadata": action.metadata,
            "tags": action.tags,
            "target_count": action.target_count,
        }
        encoded = json.dumps(
            public,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
        return hashlib.sha256(b"standard-policy-public-action-v1\0" + encoded).hexdigest()

    def choose_optional_trigger(self, effect_kind: str) -> bool:
        """Choose a supported optional trigger from public effect classification.

        The exact deck currently has one optional trigger: Curiosity's card draw.
        Keep this effect-based and fail closed so a future optional effect cannot be
        silently accepted merely because it was added to the deck.
        """
        if effect_kind == "DRAW":
            return True
        raise ValueError(f"unsupported optional trigger effect for standard policy: {effect_kind}")

    def select_action(
        self, observation: dict[str, Any], actions: tuple[ObservedAction, ...]
    ) -> str:
        self._validate_observation(observation)
        if not actions:
            raise ValueError("standard policy received no legal actions")

        def score(action: ObservedAction) -> tuple[int, int, int, str]:
            tags = set(action.tags)
            value = 0
            if action.kind == "PLAY_LAND":
                value += 80
            if "ADD_MANA" in tags or "MANA_ABILITY" in tags:
                value += 65
            if "COMBO_COMPONENT" in tags:
                value += 50 if self.bundle.value("glint_horn_use") == "cast_for_value" else 35
            if "PROTECTION" in tags:
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
                identities = {
                    str(value) for value in action.metadata.get("attacker_identities", ())
                }
                value += 30 * attacker_count + 25 * opponent_count + 20 * pirate_count
                if "Malcolm, Keen-Eyed Navigator" in identities:
                    value += 25
                if "Glint-Horn Buccaneer" in identities:
                    value += 20
                if attacker_count == 0:
                    value -= 60
            if action.kind == "PASS_PRIORITY":
                value -= 100
            return (
                value,
                -action.mana_value,
                -action.target_count,
                self._public_action_tiebreak(action),
            )

        return max(actions, key=score).handle
