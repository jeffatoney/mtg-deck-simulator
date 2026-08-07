"""Frozen paired-environment design and paired Phase C analysis."""

from __future__ import annotations

import hashlib
import json
import math
import random
from collections import Counter
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

PAIRED_GAME_COUNT = 200
PAIRS_PER_STANDARD_SHARD = 20
PAIRED_CHECKPOINT_TURN = 8
PAIRED_CI_METHOD = "DETERMINISTIC_PAIRED_BOOTSTRAP_PERCENTILE_V1"
PAIRED_CI_CONFIDENCE = 0.95
PAIRED_BOOTSTRAP_RESAMPLES = 10_000
PAIR_SELECTION_RULE = "FIRST_20_OF_EACH_STANDARD_SHARD"
PRIMARY_OUTCOME = "LEGAL_DETERMINISTIC_TABLE_WIN_ACCESS_BY_TURN_8"
SECONDARY_OUTCOME = "EARLIEST_LEGAL_DETERMINISTIC_TABLE_WIN_ACCESS_TURN"
SECONDARY_CENSORING_RULE = "NO_IMPUTATION_BOTH_ACCESS_TURN_SHIFT_ONLY"
PILOT_EFFECT_THRESHOLD_RULE = "NO_NUMERIC_ACTION_THRESHOLD_PRECOMMITTED"
REPORTING_SENTENCE = (
    "These figures measure combo assembly speed against opponents who take no actions. "
    "They are not win rates and do not predict performance against interactive opponents."
)


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _derive_seeds(namespace: str, count: int) -> tuple[int, ...]:
    return tuple(
        int.from_bytes(hashlib.sha256(f"{namespace}:{index}".encode()).digest()[:8], "big")
        for index in range(1, count + 1)
    )


def _pair_id(standard_game_index: int, environment_seed: int) -> str:
    return hashlib.sha256(
        f"phase-c-pair-v1:{standard_game_index}:{environment_seed}".encode()
    ).hexdigest()[:24]


@dataclass(frozen=True)
class PairingPlan:
    exploratory_environment_seeds: tuple[int, ...]
    exploratory_search_seeds: tuple[int, ...]
    paired_standard_game_indexes: tuple[int, ...]
    pair_ids: tuple[str, ...]
    exploratory_environment_sha256: str
    exploratory_search_sha256: str
    pair_assignment_sha256: str

    def __post_init__(self) -> None:
        fields = (
            self.exploratory_environment_seeds,
            self.exploratory_search_seeds,
            self.paired_standard_game_indexes,
            self.pair_ids,
        )
        if any(len(value) != PAIRED_GAME_COUNT for value in fields):
            raise ValueError("Phase C pairing plan must contain exactly 200 pairs")
        if len(set(self.exploratory_environment_seeds)) != PAIRED_GAME_COUNT:
            raise ValueError("paired environment seeds contain duplicates")
        if len(set(self.exploratory_search_seeds)) != PAIRED_GAME_COUNT:
            raise ValueError("exploratory search seeds contain duplicates")
        if len(set(self.paired_standard_game_indexes)) != PAIRED_GAME_COUNT:
            raise ValueError("paired standard game indexes contain duplicates")
        if len(set(self.pair_ids)) != PAIRED_GAME_COUNT:
            raise ValueError("pair IDs contain duplicates")
        if set(self.exploratory_environment_seeds).intersection(self.exploratory_search_seeds):
            raise ValueError("environment and search seed domains overlap")

    def assignment_rows(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            {
                "pair_id": pair_id,
                "standard_game_index": standard_index,
                "environment_seed": environment_seed,
                "search_seed": search_seed,
            }
            for pair_id, standard_index, environment_seed, search_seed in zip(
                self.pair_ids,
                self.paired_standard_game_indexes,
                self.exploratory_environment_seeds,
                self.exploratory_search_seeds,
                strict=True,
            )
        )


def build_pairing_plan(
    standard_environment_seeds: Sequence[int],
    *,
    search_seed_namespace: str,
    standard_shards: int,
) -> PairingPlan:
    standard = tuple(int(value) for value in standard_environment_seeds)
    if len(standard) != 500 or len(set(standard)) != 500:
        raise ValueError("paired pilot requires exactly 500 unique standard environment seeds")
    if standard_shards != 10 or len(standard) % standard_shards:
        raise ValueError("paired pilot requires ten equal standard shards")
    shard_size = len(standard) // standard_shards
    if shard_size != 50:
        raise ValueError("paired pilot standard shard size must be 50")
    paired_indexes = tuple(
        shard * shard_size + offset + 1
        for shard in range(standard_shards)
        for offset in range(PAIRS_PER_STANDARD_SHARD)
    )
    exploratory_environment = tuple(standard[index - 1] for index in paired_indexes)
    search_seeds = _derive_seeds(search_seed_namespace, PAIRED_GAME_COUNT)
    pair_ids = tuple(
        _pair_id(index, seed)
        for index, seed in zip(paired_indexes, exploratory_environment, strict=True)
    )
    rows = tuple(
        {
            "pair_id": pair_id,
            "standard_game_index": index,
            "environment_seed": env,
            "search_seed": search,
        }
        for pair_id, index, env, search in zip(
            pair_ids, paired_indexes, exploratory_environment, search_seeds, strict=True
        )
    )
    return PairingPlan(
        exploratory_environment_seeds=exploratory_environment,
        exploratory_search_seeds=search_seeds,
        paired_standard_game_indexes=paired_indexes,
        pair_ids=pair_ids,
        exploratory_environment_sha256=_digest(exploratory_environment),
        exploratory_search_sha256=_digest(search_seeds),
        pair_assignment_sha256=_digest(rows),
    )


def _mcnemar_exact_two_sided(exploratory_only: int, standard_only: int) -> float:
    discordant = exploratory_only + standard_only
    if discordant == 0:
        return 1.0
    lower = min(exploratory_only, standard_only)
    numerator = sum(math.comb(discordant, k) for k in range(lower + 1))
    p_value = min(1.0, 2.0 * numerator / (2**discordant))
    return float(p_value)


def _paired_bootstrap_percentile_ci(
    differences: Sequence[int],
    *,
    resamples: int = PAIRED_BOOTSTRAP_RESAMPLES,
    confidence: float = PAIRED_CI_CONFIDENCE,
) -> tuple[float, float]:
    values = tuple(int(value) for value in differences)
    if len(values) != PAIRED_GAME_COUNT or any(value not in {-1, 0, 1} for value in values):
        raise ValueError("paired bootstrap requires exactly 200 {-1,0,1} differences")
    seed_material = _digest(
        {
            "method": PAIRED_CI_METHOD,
            "confidence": confidence,
            "resamples": resamples,
            "differences": values,
        }
    )
    rng = random.Random(int(seed_material[:16], 16))
    n = len(values)
    samples = [sum(values[rng.randrange(n)] for _ in range(n)) / n for _ in range(resamples)]
    samples.sort()
    alpha = (1.0 - confidence) / 2.0
    lower_index = max(0, int(math.floor((resamples - 1) * alpha)))
    upper_index = min(resamples - 1, int(math.ceil((resamples - 1) * (1.0 - alpha))))
    return samples[lower_index], samples[upper_index]


def _validated_turn(value: object, label: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 10:
        raise ValueError(f"{label} must be an integer Turn 1-10 or null")
    return value


def build_paired_earliest_access_timing(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Build the secondary paired timing description without imputing censored turns."""
    rows = [dict(record) for record in records]
    if len(rows) != PAIRED_GAME_COUNT:
        raise ValueError("paired earliest-access timing requires exactly 200 records")
    pair_ids = [str(row.get("pair_id", "")) for row in rows]
    if any(not pair_id for pair_id in pair_ids) or len(set(pair_ids)) != PAIRED_GAME_COUNT:
        raise ValueError("paired earliest-access timing requires 200 unique pair IDs")

    both = standard_only = exploratory_only = neither = 0
    shifts: list[int] = []
    standard_turns: Counter[int] = Counter()
    exploratory_turns: Counter[int] = Counter()
    for row in rows:
        standard_turn = _validated_turn(
            row.get("standard_earliest_access_turn"), "standard earliest access turn"
        )
        exploratory_turn = _validated_turn(
            row.get("exploratory_earliest_access_turn"), "exploratory earliest access turn"
        )
        if standard_turn is not None:
            standard_turns[standard_turn] += 1
        if exploratory_turn is not None:
            exploratory_turns[exploratory_turn] += 1
        if standard_turn is not None and exploratory_turn is not None:
            both += 1
            shifts.append(exploratory_turn - standard_turn)
        elif standard_turn is not None:
            standard_only += 1
        elif exploratory_turn is not None:
            exploratory_only += 1
        else:
            neither += 1

    shift_counts = Counter(shifts)
    return {
        "schema_version": "phase-c-paired-earliest-access-timing-v1",
        "analysis_role": "SECONDARY_DESCRIPTIVE",
        "outcome_name": SECONDARY_OUTCOME,
        "censoring_rule": SECONDARY_CENSORING_RULE,
        "pair_count": PAIRED_GAME_COUNT,
        "both_access_by_turn10": both,
        "standard_only_access_by_turn10": standard_only,
        "exploratory_only_access_by_turn10": exploratory_only,
        "neither_access_by_turn10": neither,
        "paired_turn_shift_count": len(shifts),
        "paired_turn_shift_excluded_censored_count": PAIRED_GAME_COUNT - len(shifts),
        "paired_turn_shift_mean_exploratory_minus_standard": (
            sum(shifts) / len(shifts) if shifts else None
        ),
        "paired_turn_shift_counts": {str(key): shift_counts[key] for key in sorted(shift_counts)},
        "standard_earliest_access_turn_counts": {
            str(key): standard_turns[key] for key in sorted(standard_turns)
        },
        "exploratory_earliest_access_turn_counts": {
            str(key): exploratory_turns[key] for key in sorted(exploratory_turns)
        },
        "effect_threshold_rule": PILOT_EFFECT_THRESHOLD_RULE,
        "pair_records_sha256": _digest(rows),
    }


def build_paired_turn8_analysis(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    rows = [dict(record) for record in records]
    if len(rows) != PAIRED_GAME_COUNT:
        raise ValueError("paired Turn-8 analysis requires exactly 200 records")
    pair_ids = [str(row.get("pair_id", "")) for row in rows]
    if any(not pair_id for pair_id in pair_ids) or len(set(pair_ids)) != PAIRED_GAME_COUNT:
        raise ValueError("paired Turn-8 analysis requires 200 unique pair IDs")
    both = standard_only = exploratory_only = neither = 0
    differences: list[int] = []
    for row in rows:
        standard = bool(row["standard_access"])
        exploratory = bool(row["exploratory_access"])
        if standard and exploratory:
            both += 1
        elif standard:
            standard_only += 1
        elif exploratory:
            exploratory_only += 1
        else:
            neither += 1
        differences.append(int(exploratory) - int(standard))
    standard_access_count = both + standard_only
    exploratory_access_count = both + exploratory_only
    difference = (exploratory_only - standard_only) / PAIRED_GAME_COUNT
    lower, upper = _paired_bootstrap_percentile_ci(differences)
    p_value = _mcnemar_exact_two_sided(exploratory_only, standard_only)
    return {
        "schema_version": "phase-c-paired-turn8-analysis-v2",
        "analysis_role": "PRIMARY",
        "primary_outcome": PRIMARY_OUTCOME,
        "checkpoint_turn": PAIRED_CHECKPOINT_TURN,
        "pair_count": PAIRED_GAME_COUNT,
        "both_access": both,
        "standard_only_access": standard_only,
        "exploratory_only_access": exploratory_only,
        "neither_access": neither,
        "standard_access_count": standard_access_count,
        "exploratory_access_count": exploratory_access_count,
        "standard_access_rate": standard_access_count / PAIRED_GAME_COUNT,
        "exploratory_access_rate": exploratory_access_count / PAIRED_GAME_COUNT,
        "paired_access_rate_difference": difference,
        "discordant_pair_count": standard_only + exploratory_only,
        "mcnemar_test": "EXACT_TWO_SIDED",
        "mcnemar_exact_two_sided_p_value": p_value,
        "confidence_interval_method": PAIRED_CI_METHOD,
        "confidence_level": PAIRED_CI_CONFIDENCE,
        "bootstrap_resamples": PAIRED_BOOTSTRAP_RESAMPLES,
        "paired_access_rate_difference_ci": {"lower": lower, "upper": upper},
        "reporting_metric": "LEGAL_DETERMINISTIC_TABLE_WIN_ACCESS",
        "required_reporting_sentence": REPORTING_SENTENCE,
        "effect_threshold_rule": PILOT_EFFECT_THRESHOLD_RULE,
        "pair_records_sha256": _digest(rows),
    }


__all__ = [
    "PAIR_SELECTION_RULE",
    "PAIRED_BOOTSTRAP_RESAMPLES",
    "PAIRED_CHECKPOINT_TURN",
    "PAIRED_CI_CONFIDENCE",
    "PAIRED_CI_METHOD",
    "PAIRED_GAME_COUNT",
    "PAIRS_PER_STANDARD_SHARD",
    "PILOT_EFFECT_THRESHOLD_RULE",
    "PRIMARY_OUTCOME",
    "PairingPlan",
    "REPORTING_SENTENCE",
    "SECONDARY_CENSORING_RULE",
    "SECONDARY_OUTCOME",
    "build_paired_earliest_access_timing",
    "build_paired_turn8_analysis",
    "build_pairing_plan",
]
