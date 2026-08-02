"""Versioned, contextual strategic evaluation outside the rules kernel."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from types import MappingProxyType
from typing import Any

from mtg_cards.full_deck import RULES_BY_NAME
from mtg_kernel.strategic_choices import PublicCard

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EVALUATOR = ROOT / "configs/evaluators/contextual_combo_v1.yaml"
ACCESSIBLE_COMBO_ZONES = {"HAND", "BATTLEFIELD", "COMMAND", "EXILE"}
SCORE_SCALE = 1_000_000


def score_to_microunits(value: float) -> int:
    """Encode policy scores without placing floats in the deterministic game state."""

    return int(round(value * SCORE_SCALE))


def _canonical_without_hash(payload: Mapping[str, Any]) -> bytes:
    body = {key: value for key, value in payload.items() if key != "config_sha256"}
    return json.dumps(
        body,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def declared_effect_kinds() -> frozenset[str]:
    kinds: set[str] = set()
    for abilities in RULES_BY_NAME.values():
        for ability in abilities:
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
    return frozenset(kinds)


@dataclass(frozen=True)
class EvaluatorConfig:
    evaluator_id: str
    algorithm_version: str
    config_sha256: str
    land_curve: Mapping[int, int]
    weights: Mapping[str, float]
    effect_features: Mapping[str, tuple[str, ...]]
    combo_packages: Mapping[str, tuple[str, ...]]
    tutor_priority_orders: Mapping[str, tuple[str, ...]]
    opponent_choice_mode: str
    dualcaster_loop_handling: str
    feature_crosses: tuple[str, ...]


@dataclass(frozen=True)
class PileEvaluation:
    score: float
    features: Mapping[str, int]
    card_scores: Mapping[str, float]
    completed_packages: tuple[str, ...]
    advanced_packages: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "score_microunits": score_to_microunits(self.score),
            "score_scale": SCORE_SCALE,
            "features": dict(self.features),
            "card_score_microunits": {
                name: score_to_microunits(value) for name, value in self.card_scores.items()
            },
            "completed_packages": list(self.completed_packages),
            "advanced_packages": list(self.advanced_packages),
        }


def load_evaluator_config(path: Path | None = None) -> EvaluatorConfig:
    source = path or DEFAULT_EVALUATOR
    payload = json.loads(source.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "strategic-evaluator-config-v1":
        raise ValueError("unsupported strategic evaluator schema")
    expected = hashlib.sha256(_canonical_without_hash(payload)).hexdigest()
    recorded = str(payload.get("config_sha256", ""))
    if recorded != expected:
        raise ValueError("strategic evaluator config hash mismatch")
    if payload.get("unknown_effect_policy") != "FAIL_CLOSED":
        raise ValueError("strategic evaluator must fail closed on unknown effects")

    raw_effects = payload.get("effect_features")
    if not isinstance(raw_effects, dict):
        raise ValueError("strategic evaluator omits effect classifications")
    declared = declared_effect_kinds()
    classified = {str(key) for key in raw_effects}
    if classified != declared:
        raise ValueError(
            "strategic evaluator effect coverage mismatch: "
            f"missing={sorted(declared - classified)}, extra={sorted(classified - declared)}"
        )
    effect_features: dict[str, tuple[str, ...]] = {}
    for kind, values in raw_effects.items():
        if not isinstance(values, list) or not values:
            raise ValueError(f"effect classification is empty: {kind}")
        effect_features[str(kind)] = tuple(str(value) for value in values)

    raw_weights = payload.get("weights")
    if not isinstance(raw_weights, dict):
        raise ValueError("strategic evaluator omits feature weights")
    weights = {str(key): float(value) for key, value in raw_weights.items()}
    used_features = {feature for values in effect_features.values() for feature in values}
    required_features = used_features | {
        "base_card",
        "needed_land",
        "excess_land",
        "combo_progress",
        "combo_completion",
        "combo_redundancy",
        "protection_when_combo_ready",
        "unpayable_protection",
    }
    missing_weights = required_features - weights.keys()
    if missing_weights:
        raise ValueError(f"strategic evaluator misses weights: {sorted(missing_weights)}")

    raw_curve = payload.get("land_curve")
    if not isinstance(raw_curve, dict):
        raise ValueError("strategic evaluator omits the land curve")
    land_curve = {int(key): int(value) for key, value in raw_curve.items()}
    if set(land_curve) != set(range(1, 11)):
        raise ValueError("strategic evaluator land curve must define Turns 1 through 10")

    raw_packages = payload.get("combo_packages")
    if not isinstance(raw_packages, dict) or not raw_packages:
        raise ValueError("strategic evaluator omits combo packages")
    packages = {
        str(name): tuple(str(card) for card in cards)
        for name, cards in raw_packages.items()
        if isinstance(cards, list) and cards
    }
    if len(packages) != len(raw_packages):
        raise ValueError("strategic evaluator contains an empty combo package")

    raw_priorities = payload.get("tutor_priority_orders")
    if not isinstance(raw_priorities, dict):
        raise ValueError("strategic evaluator omits tutor priority orders")
    priorities = {
        str(name): tuple(str(card) for card in cards)
        for name, cards in raw_priorities.items()
        if isinstance(cards, list)
    }

    loop_handling = str(payload.get("dualcaster_loop_handling", ""))
    if loop_handling != "FAIL_CLOSED_UNTIL_DETERMINISTIC_LOOP_ADJUDICATOR":
        raise ValueError("unsupported Dualcaster loop handling mode")

    return EvaluatorConfig(
        evaluator_id=str(payload["evaluator_id"]),
        algorithm_version=str(payload["algorithm_version"]),
        config_sha256=recorded,
        land_curve=MappingProxyType(dict(land_curve)),
        weights=_freeze(weights),
        effect_features=_freeze(effect_features),
        combo_packages=_freeze(packages),
        tutor_priority_orders=_freeze(priorities),
        opponent_choice_mode=str(payload.get("opponent_choice_mode", "")),
        dualcaster_loop_handling=loop_handling,
        feature_crosses=tuple(str(value) for value in payload.get("feature_crosses", ())),
    )


def load_learned_evaluator_config(
    snapshot_path: Path,
    base_path: Path | None = None,
) -> EvaluatorConfig:
    """Load a validated discovery snapshot as an adjustable evaluator button."""

    from mtg_policy.learning import load_evaluator_snapshot

    base = load_evaluator_config(base_path)
    snapshot = load_evaluator_snapshot(snapshot_path)
    if snapshot.status != "FROZEN_VALIDATED":
        raise ValueError("learned evaluator snapshot did not pass holdout validation")
    if (
        snapshot.parent_evaluator_id != base.evaluator_id
        or snapshot.parent_evaluator_sha256 != base.config_sha256
    ):
        raise ValueError("learned evaluator snapshot does not match its parent evaluator")
    required = set(base.weights) - {"intentional_neutral"}
    if set(snapshot.feature_schema) != required:
        raise ValueError(
            "learned evaluator snapshot is not activation-complete: "
            f"missing={sorted(required - set(snapshot.feature_schema))}, "
            f"extra={sorted(set(snapshot.feature_schema) - required)}"
        )
    learned = dict(base.weights)
    learned.update({key: float(value) for key, value in snapshot.learned_weights.items()})
    return replace(
        base,
        evaluator_id=snapshot.snapshot_id,
        config_sha256=snapshot.snapshot_sha256,
        weights=MappingProxyType(learned),
        algorithm_version=f"{base.algorithm_version}+{snapshot.schema_version}",
    )


class ContextualEvaluator:
    """Evaluate cards using current development and combo state, not static identity."""

    def __init__(self, config: EvaluatorConfig) -> None:
        self.config = config

    @staticmethod
    def _visible_names(observation: Mapping[str, Any]) -> Counter[str]:
        names: Counter[str] = Counter()
        objects = observation.get("objects", ())
        if not isinstance(objects, Sequence):
            return names
        actor = str(observation.get("player", ""))
        for raw in objects:
            if not isinstance(raw, Mapping):
                continue
            identity = raw.get("identity")
            zone = str(raw.get("zone", ""))
            if not identity or zone not in ACCESSIBLE_COMBO_ZONES:
                continue
            owner = raw.get("owner")
            controller = raw.get("controller")
            if zone == "HAND" or owner == actor or controller == actor:
                names[str(identity)] += 1
        return names

    @staticmethod
    def _lands_in_play(observation: Mapping[str, Any]) -> int:
        actor = str(observation.get("player", ""))
        total = 0
        objects = observation.get("objects", ())
        if not isinstance(objects, Sequence):
            return 0
        for raw in objects:
            if not isinstance(raw, Mapping):
                continue
            if raw.get("zone") != "BATTLEFIELD" or raw.get("controller") != actor:
                continue
            card_types = raw.get("card_types", ())
            if isinstance(card_types, Sequence) and "Land" in card_types:
                total += 1
        return total

    def _effect_feature_counts(self, card: PublicCard) -> Counter[str]:
        counts: Counter[str] = Counter()
        for kind in card.effect_kinds:
            features = self.config.effect_features.get(kind)
            if features is None:
                raise ValueError(f"unclassified strategic effect kind: {kind}")
            for feature in features:
                counts[feature] += 1
        return counts

    def evaluate_pile(
        self,
        cards: Sequence[PublicCard],
        observation: Mapping[str, Any],
    ) -> PileEvaluation:
        turn_data = observation.get("turn", {})
        turn = int(turn_data.get("number", 1)) if isinstance(turn_data, Mapping) else 1
        turn = max(1, min(10, turn))
        target_lands = int(self.config.land_curve[turn])
        lands_in_play = self._lands_in_play(observation)
        lands_needed = max(0, target_lands - lands_in_play)
        available = self._visible_names(observation)
        pile_names = Counter(card.identity for card in cards)

        features: Counter[str] = Counter()
        card_scores: dict[str, float] = {}
        land_index = 0
        total_mana = 0
        raw_pool = observation.get("mana_pool", {})
        if isinstance(raw_pool, Mapping):
            total_mana = sum(int(value) for value in raw_pool.values())

        for card in cards:
            local: Counter[str] = Counter({"base_card": 1})
            if "Land" in card.card_types:
                if land_index < lands_needed:
                    local["needed_land"] += 1
                else:
                    local["excess_land"] += 1
                land_index += 1
            local.update(self._effect_feature_counts(card))
            if local.get("protection", 0) and card.mana_value > total_mana:
                local["unpayable_protection"] += 1
            score = sum(self.config.weights[name] * count for name, count in local.items())
            card_scores[card.identity] = card_scores.get(card.identity, 0) + score
            features.update(local)

        completed: list[str] = []
        advanced: list[str] = []
        after = available + pile_names
        combo_ready = False
        for package, components in self.config.combo_packages.items():
            before_missing = [name for name in components if available[name] < components.count(name)]
            after_missing = [name for name in components if after[name] < components.count(name)]
            if before_missing and not after_missing:
                features["combo_completion"] += 1
                completed.append(package)
                combo_ready = True
            elif len(after_missing) < len(before_missing):
                features["combo_progress"] += len(before_missing) - len(after_missing)
                advanced.append(package)
            for name in set(components):
                redundant = max(0, after[name] - components.count(name))
                if redundant and pile_names[name]:
                    features["combo_redundancy"] += min(redundant, pile_names[name])
            if not after_missing:
                combo_ready = True
        if combo_ready and features.get("protection", 0):
            features["protection_when_combo_ready"] += features["protection"]

        score = sum(self.config.weights[name] * count for name, count in features.items())
        return PileEvaluation(
            score=score,
            features=MappingProxyType(dict(sorted(features.items()))),
            card_scores=MappingProxyType(dict(sorted(card_scores.items()))),
            completed_packages=tuple(sorted(completed)),
            advanced_packages=tuple(sorted(advanced)),
        )
