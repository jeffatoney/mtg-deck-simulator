"""Raw Phase B measurements with deterministic validation and aggregation."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

CHECKPOINTS = (5, 6, 8, 10)
FAILURE_LABELS = {
    "mana_shortage",
    "color_shortage",
    "tapped_land_delay",
    "protection_mana_shortage",
    "action_density_shortage",
    "tutor_without_cast_mana",
    "interaction_only_hand",
    "sequencing_failure",
    "other_documented_cause",
}
COMBO_PACKAGES = {
    "malcolm_glint_horn",
    "dualcaster_twinflame",
    "dualcaster_electroduplicate",
    "niv_mizzet_curiosity",
    "lightning_rig_crab_umbra_malcolm",
    "psychosis_crawler_draw",
    "tutor_created_access",
    "hybrid_line",
    "recovery_line",
}


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


@dataclass(frozen=True)
class OpeningHandMeasurement:
    hand_number: int
    nominal_size: int
    card_names: tuple[str, ...]
    kept: bool
    refill_cards: tuple[str, ...] = ()
    refill_changed_combo_access: bool = False
    refill_changed_mana_access: bool = False

    def __post_init__(self) -> None:
        if self.nominal_size not in {4, 5, 6, 7}:
            raise ValueError("opening-hand nominal size must be 7, 6, 5, or 4")
        if len(self.card_names) != self.nominal_size:
            raise ValueError("opening-hand identities do not match nominal size")
        if self.hand_number < 1:
            raise ValueError("hand_number must be positive")


@dataclass(frozen=True)
class ComboMeasurement:
    package: str
    turn: int
    pieces_assembled: bool
    legally_executable: bool
    sufficient_mana: bool
    usable_protection: bool
    attempted: bool
    resolved: bool
    full_table_kill: bool
    conditional_kill_or_takeover: bool

    def __post_init__(self) -> None:
        if self.package not in COMBO_PACKAGES:
            raise ValueError(f"unknown measured combo package: {self.package}")
        if self.turn < 1:
            raise ValueError("combo measurement turn must be positive")
        if self.full_table_kill and not self.resolved:
            raise ValueError("a full table kill must be a resolved line")
        if self.resolved and not self.attempted:
            raise ValueError("a resolved line must have been attempted")


@dataclass(frozen=True)
class CardMeasurement:
    card_name: str
    drawn: int = 0
    cast: int = 0
    turns_held: int = 0
    stranded: int = 0
    stranded_reasons: tuple[str, ...] = ()
    cast_without_outcome_improvement: int = 0
    contributions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.card_name:
            raise ValueError("card measurement requires an identity")
        counts = (
            self.drawn,
            self.cast,
            self.turns_held,
            self.stranded,
            self.cast_without_outcome_improvement,
        )
        if any(value < 0 for value in counts):
            raise ValueError("card measurement counts cannot be negative")


@dataclass(frozen=True)
class DivergenceMeasurement:
    paired_seed: int
    standard_result: str
    exploratory_result: str
    first_decision_divergence: str
    visible_information: Mapping[str, Any]
    win_turn_change: int | None
    narrow_condition: bool
    branches_searched: int
    nodes_evaluated: int
    depth_reached: int
    selected_before_future_draws: bool

    def __post_init__(self) -> None:
        if self.branches_searched < 0 or self.nodes_evaluated < 0 or self.depth_reached < 0:
            raise ValueError("divergence search counts cannot be negative")
        forbidden = {"library_order", "future_events", "future_random_outcomes"}
        if forbidden.intersection(self.visible_information):
            raise ValueError("divergence record exposes forbidden future information")


@dataclass(frozen=True)
class GameMeasurement:
    schema_version: str
    game_index: int
    seed: int
    mode: str
    policy_config_id: str
    opening_hands: tuple[OpeningHandMeasurement, ...]
    kept_at: int
    checkpoint_table_win_access: Mapping[int, bool]
    failure_labels: Mapping[int, tuple[str, ...]]
    primary_failure: Mapping[int, str | None]
    combo_records: tuple[ComboMeasurement, ...]
    earliest_legal_attempt_turn: int | None
    actual_first_attempt_turn: int | None
    attempt_package: str | None
    attempt_timing: str | None
    usable_protection_count: int
    protection_in_hand_not_payable: bool
    protection_category_mismatch: bool
    independent_second_line_available: bool
    card_records: tuple[CardMeasurement, ...]
    divergence: DivergenceMeasurement | None = None
    search_decisions: tuple[Mapping[str, Any], ...] = ()
    future_information_rejections: int = 0
    post_result_optimization_rejections: int = 0
    terminal_status: str = "ACTIVE"
    terminal_turn: int | None = None
    extra: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.schema_version != "phase-b-game-measurement-v1":
            raise ValueError("unsupported measurement schema")
        if self.game_index < 1:
            raise ValueError("game_index must be positive")
        if self.mode not in {"STANDARD", "EXPLORATORY", "AUDIT_ONLY"}:
            raise ValueError("measurement mode is unsupported")
        if self.kept_at not in {4, 5, 6, 7}:
            raise ValueError("kept_at must be 7, 6, 5, or 4")
        if set(self.checkpoint_table_win_access) != set(CHECKPOINTS):
            raise ValueError("checkpoint access must contain Turns 5, 6, 8, and 10")
        if set(self.failure_labels) != set(CHECKPOINTS):
            raise ValueError("failure labels must contain all four checkpoints")
        if set(self.primary_failure) != set(CHECKPOINTS):
            raise ValueError("primary failure must contain all four checkpoints")
        for turn in CHECKPOINTS:
            labels = self.failure_labels[turn]
            unknown = set(labels) - FAILURE_LABELS
            if unknown:
                raise ValueError(f"unknown failure labels at Turn {turn}: {sorted(unknown)}")
            primary = self.primary_failure[turn]
            if primary is not None and primary not in labels:
                raise ValueError("primary failure must be one of the applicable labels")
        if self.attempt_package is not None and self.attempt_package not in COMBO_PACKAGES:
            raise ValueError("attempt package is not in the frozen package set")
        if self.attempt_timing not in {None, "IMMEDIATE", "DELAYED"}:
            raise ValueError("attempt timing must be immediate, delayed, or absent")
        if self.usable_protection_count < 0:
            raise ValueError("usable protection count cannot be negative")
        if self.future_information_rejections < 0 or self.post_result_optimization_rejections < 0:
            raise ValueError("safeguard rejection counts cannot be negative")
        if self.terminal_status != "ACTIVE" and self.terminal_turn is None:
            raise ValueError("terminal records require a terminal turn")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MeasurementSummary:
    schema_version: str
    game_denominator: int
    mode_denominators: Mapping[str, int]
    keep_level_denominators: Mapping[int, int]
    checkpoint_access_numerators: Mapping[int, int]
    checkpoint_access_denominators: Mapping[int, int]
    failure_label_counts: Mapping[str, int]
    combo_attempt_counts: Mapping[str, int]
    combo_kill_counts: Mapping[str, int]
    earliest_legal_attempt_turn_counts: Mapping[int, int]
    actual_first_attempt_turn_counts: Mapping[int, int]
    terminal_turn_counts: Mapping[int, int]
    never_legal_attempt_count: int
    never_attempted_count: int
    future_information_rejections: int
    post_result_optimization_rejections: int
    raw_measurement_sha256: str


def measurement_digest(records: Sequence[GameMeasurement]) -> str:
    ordered = sorted((record.to_dict() for record in records), key=lambda row: row["game_index"])
    return hashlib.sha256(_canonical(ordered)).hexdigest()


def aggregate_measurements(records: Sequence[GameMeasurement]) -> MeasurementSummary:
    if not records:
        raise ValueError("cannot aggregate an empty measurement set")
    indexes = [record.game_index for record in records]
    seeds = [record.seed for record in records]
    if len(indexes) != len(set(indexes)):
        raise ValueError("measurement game indexes contain duplicates")
    if len(seeds) != len(set(seeds)):
        raise ValueError("measurement seeds contain duplicates")

    modes: Counter[str] = Counter()
    keep_levels: Counter[int] = Counter()
    access: Counter[int] = Counter()
    failures: Counter[str] = Counter()
    attempts: Counter[str] = Counter()
    kills: Counter[str] = Counter()
    earliest_turns: Counter[int] = Counter()
    actual_turns: Counter[int] = Counter()
    terminal_turns: Counter[int] = Counter()
    never_legal = 0
    never_attempted = 0
    future_rejections = 0
    post_result_rejections = 0
    for record in records:
        modes[record.mode] += 1
        keep_levels[record.kept_at] += 1
        future_rejections += record.future_information_rejections
        post_result_rejections += record.post_result_optimization_rejections
        if record.earliest_legal_attempt_turn is None:
            never_legal += 1
        else:
            earliest_turns[record.earliest_legal_attempt_turn] += 1
        if record.actual_first_attempt_turn is None:
            never_attempted += 1
        else:
            actual_turns[record.actual_first_attempt_turn] += 1
        if record.terminal_turn is not None:
            terminal_turns[record.terminal_turn] += 1
        for turn in CHECKPOINTS:
            access[turn] += int(record.checkpoint_table_win_access[turn])
            failures.update(record.failure_labels[turn])
        for combo in record.combo_records:
            attempts[combo.package] += int(combo.attempted)
            kills[combo.package] += int(combo.full_table_kill)
    denominator = len(records)
    return MeasurementSummary(
        schema_version="phase-b-measurement-summary-v1",
        game_denominator=denominator,
        mode_denominators=dict(sorted(modes.items())),
        keep_level_denominators=dict(sorted(keep_levels.items())),
        checkpoint_access_numerators={turn: access[turn] for turn in CHECKPOINTS},
        checkpoint_access_denominators={turn: denominator for turn in CHECKPOINTS},
        failure_label_counts=dict(sorted(failures.items())),
        combo_attempt_counts=dict(sorted(attempts.items())),
        combo_kill_counts=dict(sorted(kills.items())),
        earliest_legal_attempt_turn_counts=dict(sorted(earliest_turns.items())),
        actual_first_attempt_turn_counts=dict(sorted(actual_turns.items())),
        terminal_turn_counts=dict(sorted(terminal_turns.items())),
        never_legal_attempt_count=never_legal,
        never_attempted_count=never_attempted,
        future_information_rejections=future_rejections,
        post_result_optimization_rejections=post_result_rejections,
        raw_measurement_sha256=measurement_digest(records),
    )
