"""Versioned, hidden-information-safe directed exploration primitives for Phase C V2."""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]

AGGRESSIVE_ARM = "EXPLORATORY_AGGRESSIVE_V2"
ALT_PACKAGE_ARM = "EXPLORATORY_ALT_PACKAGE_NO_GLINT_TUTOR_V2"
INTERACTION_ARM = "EXPLORATORY_INTERACTION_DISCOVERY_V2"
ARM_IDS = frozenset({AGGRESSIVE_ARM, ALT_PACKAGE_ARM, INTERACTION_ARM})

_ARM_PATHS = {
    AGGRESSIVE_ARM: ROOT / "configs/evaluators/exploratory_aggressive_v2.yaml",
    ALT_PACKAGE_ARM: ROOT / "configs/evaluators/exploratory_alt_package_v2.yaml",
    INTERACTION_ARM: ROOT / "configs/evaluators/exploratory_interaction_discovery_v2.yaml",
}

_ALLOWED_CONSTRAINT_STATUS = frozenset({"ALLOWED", "NOT_APPLICABLE"})


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    """Hash an audit value without introducing implementation-specific ordering."""

    return hashlib.sha256(_canonical(value)).hexdigest()


@dataclass(frozen=True)
class DirectedArmConfig:
    """Frozen selection and continuation controls for one exploratory arm."""

    schema_version: str
    arm_id: str
    reporting_label: str
    objective: tuple[str, ...]
    selection_method: str
    top_k: int
    novelty_weight_microunits: int
    equivalence_window: Mapping[str, int]
    continuation_method: str
    continuation_action_limit: int
    no_glint_horn_tutoring: bool
    discovery_primary: bool
    pilot_activation: bool
    diagnostic_environment_seeds: tuple[int, ...]
    diagnostic_exploration_seeds: tuple[int, ...]
    config_sha256: str

    def __post_init__(self) -> None:
        if self.schema_version != "phase-c-exploratory-arm-v2":
            raise ValueError("unsupported exploratory V2 arm schema")
        if self.arm_id not in ARM_IDS:
            raise ValueError(f"unsupported exploratory V2 arm: {self.arm_id}")
        if self.selection_method != "SEEDED_WEIGHTED_TOP_K_WITH_HARD_OBJECTIVE_GATES":
            raise ValueError("unsupported exploratory V2 selection method")
        if self.top_k < 1 or self.top_k > 8:
            raise ValueError("exploratory V2 top_k must be within 1..8")
        if self.novelty_weight_microunits < 0:
            raise ValueError("novelty weight cannot be negative")
        if self.continuation_method != "ONE_DEVIATION_THEN_STANDARD_VISIBLE_HORIZON":
            raise ValueError("unsupported exploratory V2 continuation method")
        if self.continuation_action_limit < 1 or self.continuation_action_limit > 32:
            raise ValueError("exploratory V2 continuation limit must be within 1..32")
        if self.pilot_activation:
            raise ValueError("exploratory V2 implementation config cannot activate a pilot")
        if len(self.diagnostic_environment_seeds) != len(self.diagnostic_exploration_seeds):
            raise ValueError("diagnostic environment/search seed counts differ")
        if not self.diagnostic_environment_seeds:
            raise ValueError("exploratory V2 config requires diagnostic seeds")
        if len(set(self.diagnostic_environment_seeds)) != len(self.diagnostic_environment_seeds):
            raise ValueError("diagnostic environment seeds contain duplicates")
        if len(set(self.diagnostic_exploration_seeds)) != len(self.diagnostic_exploration_seeds):
            raise ValueError("diagnostic exploration seeds contain duplicates")
        if set(self.diagnostic_environment_seeds).intersection(self.diagnostic_exploration_seeds):
            raise ValueError("environment and exploration seed domains must be disjoint")
        if len(self.config_sha256) != 64:
            raise ValueError("exploratory V2 config digest is invalid")


@dataclass(frozen=True)
class CandidateScoreVector:
    """Complete persisted score vector for one considered strategic candidate."""

    immediate_deterministic_access: bool
    projected_deterministic_access: bool
    earliest_projected_access_turn: int | None
    known_package_progress: int
    mana_development_value: int
    relevant_resource_preservation: int
    card_selection_or_tutor_value: int
    conditional_access_status: str
    novelty_value: int
    arm_constraint_status: str
    action_cost: int
    reason_codes: tuple[str, ...]
    final_candidate_rank: int | None = None

    def __post_init__(self) -> None:
        if self.earliest_projected_access_turn is not None and self.earliest_projected_access_turn < 1:
            raise ValueError("earliest projected access turn must be positive")
        for field_name in (
            "known_package_progress",
            "mana_development_value",
            "relevant_resource_preservation",
            "card_selection_or_tutor_value",
            "novelty_value",
            "action_cost",
        ):
            if int(getattr(self, field_name)) < 0:
                raise ValueError(f"candidate score field cannot be negative: {field_name}")
        if self.conditional_access_status not in {"NONE", "PROGRESS", "AVAILABLE"}:
            raise ValueError("candidate conditional-access status is invalid")
        if not self.arm_constraint_status:
            raise ValueError("candidate arm constraint status is required")
        if self.final_candidate_rank is not None and self.final_candidate_rank < 1:
            raise ValueError("candidate final rank must be positive")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DirectedCandidate:
    """Policy-safe candidate wrapper used by the generic selector."""

    handle: str
    semantic_key: str
    score: CandidateScoreVector
    pruned_reason: str | None = None

    def __post_init__(self) -> None:
        if not self.handle or not self.semantic_key:
            raise ValueError("directed candidate requires a handle and semantic key")
        if self.pruned_reason is None and self.score.arm_constraint_status not in _ALLOWED_CONSTRAINT_STATUS:
            raise ValueError("ineligible candidate requires an explicit pruning reason")


@dataclass(frozen=True)
class DirectedSelection:
    """Auditable result of one deterministic directed-selection decision."""

    arm_id: str
    baseline_handle: str
    candidates: tuple[DirectedCandidate, ...]
    eligible_top_k: tuple[str, ...]
    selected_handle: str
    selection_reason: str
    randomness_affected_selection: bool
    exploration_seed_digest: str

    def __post_init__(self) -> None:
        handles = {candidate.handle for candidate in self.candidates}
        if self.baseline_handle not in handles:
            raise ValueError("STANDARD baseline candidate was not retained")
        if self.selected_handle not in handles:
            raise ValueError("selected exploratory candidate is absent")
        if self.selected_handle not in self.eligible_top_k:
            raise ValueError("selected exploratory candidate is not in eligible top-k")
        ranks = [candidate.score.final_candidate_rank for candidate in self.candidates]
        if any(rank is None for rank in ranks):
            raise ValueError("every candidate must persist its final rank")


def _load_payload(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError("exploratory V2 arm config must be a JSON object")
    return value


def load_directed_arm_config(arm_id: str, path: Path | None = None) -> DirectedArmConfig:
    """Load one immutable JSON-in-YAML arm config and compute its canonical digest."""

    if arm_id not in ARM_IDS:
        raise ValueError(f"unknown exploratory V2 arm: {arm_id}")
    source = path or _ARM_PATHS[arm_id]
    raw = _load_payload(source)
    if str(raw.get("arm_id", "")) != arm_id:
        raise ValueError("exploratory V2 arm config identity mismatch")
    seeds = raw.get("diagnostic_seeds")
    if not isinstance(seeds, Mapping):
        raise ValueError("exploratory V2 diagnostic seed block is missing")
    window = raw.get("equivalence_window")
    if not isinstance(window, Mapping):
        raise ValueError("exploratory V2 equivalence window is missing")
    payload = dict(raw)
    return DirectedArmConfig(
        schema_version=str(raw.get("schema_version", "")),
        arm_id=arm_id,
        reporting_label=str(raw.get("reporting_label", "")),
        objective=tuple(str(value) for value in raw.get("objective", ())),
        selection_method=str(raw.get("selection_method", "")),
        top_k=int(raw.get("top_k", 0)),
        novelty_weight_microunits=int(raw.get("novelty_weight_microunits", 0)),
        equivalence_window={str(key): int(value) for key, value in window.items()},
        continuation_method=str(raw.get("continuation_method", "")),
        continuation_action_limit=int(raw.get("continuation_action_limit", 0)),
        no_glint_horn_tutoring=bool(raw.get("no_glint_horn_tutoring", False)),
        discovery_primary=bool(raw.get("discovery_primary", False)),
        pilot_activation=bool(raw.get("pilot_activation", False)),
        diagnostic_environment_seeds=tuple(int(value) for value in seeds.get("environment", ())),
        diagnostic_exploration_seeds=tuple(int(value) for value in seeds.get("exploration", ())),
        config_sha256=canonical_sha256(payload),
    )


def _objective_key(arm_id: str, candidate: DirectedCandidate) -> tuple[Any, ...]:
    score = candidate.score
    earliest = -(score.earliest_projected_access_turn or 99)
    permitted = int(score.arm_constraint_status in _ALLOWED_CONSTRAINT_STATUS)
    if arm_id == INTERACTION_ARM:
        return (
            permitted,
            score.novelty_value,
            int(score.immediate_deterministic_access),
            int(score.projected_deterministic_access),
            earliest,
            score.known_package_progress,
            score.mana_development_value,
            score.relevant_resource_preservation,
            score.card_selection_or_tutor_value,
            -score.action_cost,
        )
    return (
        permitted,
        int(score.immediate_deterministic_access),
        int(score.projected_deterministic_access),
        earliest,
        score.known_package_progress,
        score.mana_development_value,
        score.relevant_resource_preservation,
        score.card_selection_or_tutor_value,
        int(score.conditional_access_status == "AVAILABLE"),
        -score.action_cost,
    )


def _rank_candidates(
    arm_id: str, candidates: Sequence[DirectedCandidate]
) -> tuple[DirectedCandidate, ...]:
    ordered = sorted(
        candidates,
        key=lambda item: (_objective_key(arm_id, item), item.semantic_key),
        reverse=True,
    )
    return tuple(replace(candidate, score=replace(candidate.score, final_candidate_rank=index)) for index, candidate in enumerate(ordered, start=1))


def _inside_equivalence_window(
    config: DirectedArmConfig,
    best: CandidateScoreVector,
    candidate: CandidateScoreVector,
) -> bool:
    if candidate.arm_constraint_status not in _ALLOWED_CONSTRAINT_STATUS:
        return False
    if candidate.immediate_deterministic_access != best.immediate_deterministic_access:
        return False
    if candidate.projected_deterministic_access != best.projected_deterministic_access:
        return False
    if candidate.earliest_projected_access_turn != best.earliest_projected_access_turn:
        return False
    window = config.equivalence_window
    comparisons = (
        ("known_package_progress", best.known_package_progress, candidate.known_package_progress),
        ("mana_development_value", best.mana_development_value, candidate.mana_development_value),
        (
            "relevant_resource_preservation",
            best.relevant_resource_preservation,
            candidate.relevant_resource_preservation,
        ),
        (
            "card_selection_or_tutor_value",
            best.card_selection_or_tutor_value,
            candidate.card_selection_or_tutor_value,
        ),
        ("action_cost", best.action_cost, candidate.action_cost),
    )
    if any(abs(left - right) > int(window.get(name, 0)) for name, left, right in comparisons):
        return False
    if config.discovery_primary and abs(best.novelty_value - candidate.novelty_value) > int(
        window.get("novelty_value", 0)
    ):
        return False
    return True


def select_directed_candidate(
    config: DirectedArmConfig,
    candidates: Sequence[DirectedCandidate],
    *,
    baseline_handle: str,
    exploration_seed: int,
    decision_id: str,
) -> DirectedSelection:
    """Rank candidates and make the only permitted seeded exploratory choice."""

    if not candidates:
        raise ValueError("directed exploration requires candidates")
    if len({candidate.handle for candidate in candidates}) != len(candidates):
        raise ValueError("directed candidate handles must be unique")
    if baseline_handle not in {candidate.handle for candidate in candidates}:
        raise ValueError("STANDARD baseline candidate must be retained before selection")

    ranked = _rank_candidates(config.arm_id, candidates)
    permitted = [
        candidate for candidate in ranked if candidate.score.arm_constraint_status in _ALLOWED_CONSTRAINT_STATUS and candidate.pruned_reason is None
    ]
    if not permitted:
        raise ValueError("exploratory V2 has no permitted legal candidate")
    best = permitted[0]
    eligible = [
        candidate
        for candidate in permitted
        if _inside_equivalence_window(config, best.score, candidate.score)
    ][: config.top_k]
    if not eligible:
        raise ValueError("exploratory V2 equivalence set is unexpectedly empty")

    material = f"phase-c-exploratory-v2:{config.arm_id}:{exploration_seed}:{decision_id}"
    seed_digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    if len(eligible) == 1:
        selected = eligible[0]
        reason = "STRICT_OBJECTIVE_BEST"
        randomness = False
    else:
        rng = random.Random(int(seed_digest[:16], 16))
        weights = [
            1_000_000 + config.novelty_weight_microunits * max(0, item.score.novelty_value)
            for item in eligible
        ]
        pick = rng.randrange(sum(weights))
        selected = eligible[-1]
        cursor = 0
        for item, weight in zip(eligible, weights, strict=True):
            cursor += weight
            if pick < cursor:
                selected = item
                break
        reason = "SEEDED_WEIGHTED_TOP_K"
        randomness = True

    return DirectedSelection(
        arm_id=config.arm_id,
        baseline_handle=baseline_handle,
        candidates=ranked,
        eligible_top_k=tuple(item.handle for item in eligible),
        selected_handle=selected.handle,
        selection_reason=reason,
        randomness_affected_selection=randomness,
        exploration_seed_digest=seed_digest,
    )


__all__ = [
    "AGGRESSIVE_ARM",
    "ALT_PACKAGE_ARM",
    "INTERACTION_ARM",
    "ARM_IDS",
    "CandidateScoreVector",
    "DirectedArmConfig",
    "DirectedCandidate",
    "DirectedSelection",
    "canonical_sha256",
    "load_directed_arm_config",
    "select_directed_candidate",
]
