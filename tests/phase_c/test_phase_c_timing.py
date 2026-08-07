from __future__ import annotations

import json

import pytest

from mtg_runs.phase_c import DEFAULT_CONFIG, load_phase_c_config
from mtg_runs.phase_c_pairing import (
    PILOT_EFFECT_THRESHOLD_RULE,
    PRIMARY_OUTCOME,
    SECONDARY_CENSORING_RULE,
    SECONDARY_OUTCOME,
    build_paired_earliest_access_timing,
    build_paired_turn8_analysis,
)


def _timing_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index in range(200):
        category = index % 4
        standard_turn: int | None
        exploratory_turn: int | None
        if category == 0:
            standard_turn, exploratory_turn = 8, 7
        elif category == 1:
            standard_turn, exploratory_turn = 8, None
        elif category == 2:
            standard_turn, exploratory_turn = None, 7
        else:
            standard_turn, exploratory_turn = None, None
        rows.append(
            {
                "pair_id": f"{index + 1:024x}"[-24:],
                "standard_earliest_access_turn": standard_turn,
                "exploratory_earliest_access_turn": exploratory_turn,
            }
        )
    return rows


def test_secondary_timing_reports_censoring_without_imputation() -> None:
    result = build_paired_earliest_access_timing(_timing_rows())
    assert result["analysis_role"] == "SECONDARY_DESCRIPTIVE"
    assert result["outcome_name"] == SECONDARY_OUTCOME
    assert result["censoring_rule"] == SECONDARY_CENSORING_RULE
    assert result["both_access_by_turn10"] == 50
    assert result["standard_only_access_by_turn10"] == 50
    assert result["exploratory_only_access_by_turn10"] == 50
    assert result["neither_access_by_turn10"] == 50
    assert result["paired_turn_shift_count"] == 50
    assert result["paired_turn_shift_excluded_censored_count"] == 150
    assert result["paired_turn_shift_mean_exploratory_minus_standard"] == -1.0
    assert result["paired_turn_shift_counts"] == {"-1": 50}
    assert result["effect_threshold_rule"] == PILOT_EFFECT_THRESHOLD_RULE
    assert "11" not in result["standard_earliest_access_turn_counts"]
    assert "11" not in result["exploratory_earliest_access_turn_counts"]


def test_secondary_timing_rejects_imputed_turn_eleven() -> None:
    rows = _timing_rows()
    rows[0]["exploratory_earliest_access_turn"] = 11
    with pytest.raises(ValueError, match="Turn 1-10 or null"):
        build_paired_earliest_access_timing(rows)


def test_primary_turn8_analysis_stays_primary_and_separate() -> None:
    rows = [
        {
            "pair_id": f"{index + 1:024x}"[-24:],
            "standard_access": index % 2 == 0,
            "exploratory_access": index % 3 == 0,
        }
        for index in range(200)
    ]
    result = build_paired_turn8_analysis(rows)
    assert result["analysis_role"] == "PRIMARY"
    assert result["primary_outcome"] == PRIMARY_OUTCOME
    assert result["checkpoint_turn"] == 8
    assert "secondary_earliest_access_timing" not in result


def test_locked_config_encodes_primary_secondary_and_no_numeric_threshold() -> None:
    load_phase_c_config()
    payload = json.loads(DEFAULT_CONFIG.read_text(encoding="utf-8"))
    paired = payload["paired_analysis"]
    assert paired["primary_outcome"] == PRIMARY_OUTCOME
    assert paired["secondary_outcome"] == SECONDARY_OUTCOME
    assert paired["secondary_censoring_rule"] == SECONDARY_CENSORING_RULE
    assert paired["effect_threshold_rule"] == PILOT_EFFECT_THRESHOLD_RULE
    assert "paired_turn8_analysis" in payload["measurement"]["required_outputs"]
    assert "paired_earliest_access_timing" in payload["measurement"]["required_outputs"]
