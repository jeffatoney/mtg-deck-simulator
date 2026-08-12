from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

import mtg_runs.phase_c as phase_c
from mtg_runs.phase_c import (
    DEFAULT_CONFIG,
    PhaseCControlError,
    _parse_paired_analysis_configuration,
    load_phase_c_config,
)
from mtg_runs.phase_c_pairing import (
    build_paired_earliest_access_timing,
    build_paired_turn8_analysis,
)


def _payload() -> dict[str, object]:
    return json.loads(DEFAULT_CONFIG.read_text(encoding="utf-8"))


def _write(path: Path, payload: dict[str, object]) -> Path:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("section", "key", "value", "message"),
    [
        ("paired_analysis", "primary_outcome", "WIN_RATE", "paired primary outcome"),
        ("paired_analysis", "outcome_name", "RENAMED", "paired outcome name"),
        (
            "paired_analysis",
            "effect_threshold_rule",
            "ACT_ON_ANYTHING",
            "paired effect-threshold rule",
        ),
        ("paired_analysis", "secondary_outcome", "INVALID_SECONDARY", "paired secondary outcome"),
        (
            "paired_analysis",
            "secondary_censoring_rule",
            "IMPUTE_TURN_11",
            "paired secondary censoring rule",
        ),
        ("paired_analysis", "checkpoint_turn", 7, "paired checkpoint"),
        ("measurement", "primary_checkpoint", 7, "primary checkpoint"),
        (
            "paired_analysis",
            "required_reporting_sentence",
            "This is a renamed statement.",
            "paired reporting sentence",
        ),
        ("deck", "exact_library_count", 97, "exact library count"),
        ("deck", "physical_card_count", 99, "physical card count"),
        (
            "deck",
            "commanders",
            ["Malcolm, Keen-Eyed Navigator", "Not Breeches"],
            "deck commanders",
        ),
        ("deck", "source", "docs/source/not-the-deck.txt", "deck source"),
        (
            "pilot",
            "environment_seed_namespace",
            "mutated-standard-namespace",
            "standard environment seed namespace",
        ),
        ("policy", "standard_policy_config_id", "mutated-policy", "standard policy config ID"),
        ("policy", "evaluator_snapshot_id", "mutated-evaluator", "evaluator snapshot ID"),
    ],
)
def test_frozen_study_definition_mutations_fail_closed(
    tmp_path: Path, section: str, key: str, value: object, message: str
) -> None:
    payload = _payload()
    section_payload = payload[section]
    assert isinstance(section_payload, dict)
    assert section_payload.get(key) != value, "mutation must not be vacuous"
    section_payload[key] = value
    with pytest.raises(PhaseCControlError, match=message):
        load_phase_c_config(_write(tmp_path / f"{section}-{key}.json", payload))


@pytest.mark.parametrize(
    "section",
    [
        None,
        "authorization",
        "deck",
        "exploratory_search",
        "full_study",
        "game_model",
        "measurement",
        "mulligan",
        "paired_analysis",
        "pilot",
        "policy",
        "prerequisites",
    ],
)
def test_unknown_configuration_keys_fail_closed(tmp_path: Path, section: str | None) -> None:
    payload = _payload()
    if section is None:
        assert "injected_unreviewed_key" not in payload
        payload["injected_unreviewed_key"] = True
        filename = "top-level"
    else:
        section_payload = payload[section]
        assert isinstance(section_payload, dict)
        assert "injected_unreviewed_key" not in section_payload
        section_payload["injected_unreviewed_key"] = True
        filename = section
    with pytest.raises(PhaseCControlError, match="field set mismatch"):
        load_phase_c_config(_write(tmp_path / f"unknown-{filename}.json", payload))


def _controlled_analysis_fixture():
    payload = _payload()
    paired = deepcopy(payload["paired_analysis"])
    assert isinstance(paired, dict)
    paired.update(
        {
            "primary_outcome": "FIXTURE_PRIMARY_OUTCOME",
            "outcome_name": "FIXTURE_REPORTING_NAME",
            "secondary_outcome": "FIXTURE_SECONDARY_OUTCOME",
            "secondary_censoring_rule": "FIXTURE_CENSORING_RULE",
            "effect_threshold_rule": "FIXTURE_EFFECT_RULE",
            "required_reporting_sentence": "Fixture reporting sentence.",
            "checkpoint_turn": 6,
        }
    )
    return _parse_paired_analysis_configuration(paired)


def _primary_rows() -> list[dict[str, object]]:
    return [
        {
            "pair_id": f"pair-{index:03d}",
            "standard_access": index % 2 == 0,
            "exploratory_access": index % 3 == 0,
        }
        for index in range(1, 201)
    ]


def _secondary_rows() -> list[dict[str, object]]:
    return [
        {
            "pair_id": f"pair-{index:03d}",
            "standard_earliest_access_turn": 5 if index % 2 == 0 else None,
            "exploratory_earliest_access_turn": 4 if index % 3 == 0 else None,
        }
        for index in range(1, 201)
    ]


def test_analysis_default_path_consults_loaded_typed_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _controlled_analysis_fixture()
    monkeypatch.setattr(
        phase_c,
        "load_phase_c_config",
        lambda: SimpleNamespace(paired_analysis=fixture),
    )
    primary = build_paired_turn8_analysis(_primary_rows())
    secondary = build_paired_earliest_access_timing(_secondary_rows())
    assert primary["primary_outcome"] == fixture.primary_outcome
    assert primary["reporting_metric"] == fixture.outcome_name
    assert primary["checkpoint_turn"] == fixture.checkpoint_turn
    assert primary["effect_threshold_rule"] == fixture.effect_threshold_rule
    assert primary["required_reporting_sentence"] == fixture.required_reporting_sentence
    assert primary["confidence_interval_method"] == fixture.confidence_interval_method
    assert primary["confidence_level"] == fixture.confidence_level
    assert primary["bootstrap_resamples"] == fixture.bootstrap_resamples
    assert secondary["outcome_name"] == fixture.secondary_outcome
    assert secondary["censoring_rule"] == fixture.secondary_censoring_rule
    assert secondary["effect_threshold_rule"] == fixture.effect_threshold_rule
