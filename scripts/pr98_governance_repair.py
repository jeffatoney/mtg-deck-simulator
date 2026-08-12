#!/usr/bin/env python3
"""Apply the focused PR #98 governance repair, then let CI validate the result."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise SystemExit(f"{label}: expected exactly one anchor, found {text.count(old)}")
    return text.replace(old, new, 1)


def repair_phase_b_surface() -> None:
    path = ROOT / "scripts/_phase_b_paths.py"
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '    "docs/spec/phase-c/PHASE_C_PILOT_CONFIG.json",\n',
        "",
        "mutable config covered-path removal",
    )
    if '    "docs/spec/phase-c/NO_OPPONENT_POLICY_GUARDRAIL.json",\n' not in text:
        raise SystemExit("no-opponent guardrail must remain on the Phase B surface")
    path.write_text(text, encoding="utf-8")


def repair_phase_c_loader() -> None:
    path = ROOT / "src/mtg_runs/phase_c.py"
    text = path.read_text(encoding="utf-8")

    allowlist = '''_ACTIVATION_ALLOWLIST = {
    "docs/spec/phase-c/PHASE_C_PILOT_APPROVAL.json",
    "docs/spec/phase-c/PHASE_C_PILOT_CONFIG.json",
}
'''
    schema = allowlist + '''_CONFIG_TOP_LEVEL_KEYS = frozenset(
    {
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
        "schema_version",
        "stop_conditions",
    }
)
_CONFIG_SECTION_KEYS: dict[str, frozenset[str]] = {
    "authorization": frozenset(
        {"approved_at", "approved_by", "confirmation_token", "execution_allowed", "status"}
    ),
    "deck": frozenset({"commanders", "exact_library_count", "physical_card_count", "source"}),
    "exploratory_search": frozenset(
        {
            "bounded",
            "future_information_allowed",
            "post_result_optimization_allowed",
            "production_decision_layer_depth",
            "reported_separately",
            "rules_validation_required",
        }
    ),
    "full_study": frozenset(
        {"authorization_status", "execution_allowed", "exploratory_games", "standard_games"}
    ),
    "game_model": frozenset(
        {
            "blocking_modeled",
            "breeches_unknown_cards_added_as_deterministic_resources",
            "controlled_player_draws_on_turn_one",
            "end_after_controlled_turn",
            "glint_horn_may_attack_when_legal",
            "malcolm_may_connect_when_legal",
            "opponent_interaction_modeled",
            "opponent_wins_modeled",
            "opponents",
            "players",
        }
    ),
    "measurement": frozenset(
        {"additional_checkpoints", "objective", "primary_checkpoint", "required_outputs"}
    ),
    "mulligan": frozenset(
        {
            "candidate_hand_sizes",
            "refill_kept_hand_to",
            "rejected_hands_returned_and_shuffled",
            "stop_below_four",
        }
    ),
    "paired_analysis": frozenset(
        {
            "bootstrap_resamples",
            "checkpoint_turn",
            "confidence_interval_method",
            "confidence_level",
            "effect_threshold_rule",
            "mcnemar_test",
            "outcome_name",
            "paired_game_count",
            "pairs_per_standard_shard",
            "pair_selection_rule",
            "primary_outcome",
            "required_reporting_sentence",
            "secondary_censoring_rule",
            "secondary_outcome",
        }
    ),
    "pilot": frozenset(
        {
            "environment_seed_namespace",
            "exploratory_games",
            "exploratory_search_seed_namespace",
            "exploratory_shards",
            "standard_games",
            "standard_shards",
        }
    ),
    "policy": frozenset(
        {
            "evaluator_snapshot_id",
            "evaluator_snapshot_sha256",
            "exploratory_continuation_policy_config_id",
            "learning_plan_sha256",
            "policy_mutation_allowed",
            "standard_policy_config_hash",
            "standard_policy_config_id",
        }
    ),
    "prerequisites": frozenset(
        {
            "clean_engine_only",
            "legacy_import_allowed",
            "phase_a_verifier_required",
            "phase_b_certification_required",
            "phase_b_verifier_required",
            "post_merge_main_ci_required",
        }
    ),
}
_REQUIRED_OUTPUTS = (
    "opening_hand_records",
    "mulligan_depth",
    "checkpoint_table_win_access",
    "combo_access",
    "earliest_legal_attempt_turn",
    "actual_first_attempt_turn",
    "failure_labels",
    "card_measurements",
    "terminal_status",
    "replay_transcript",
    "immutable_run_manifest",
    "paired_turn8_analysis",
    "paired_earliest_access_timing",
    "aggregation_digest",
)
_STOP_CONDITIONS = (
    "PHASE_A_OR_PHASE_B_GATE_FAILURE",
    "SOURCE_OR_CONFIGURATION_DIGEST_DRIFT",
    "UNSUPPORTED_CAPABILITY_OR_STRATEGIC_BLOCKER",
    "HIDDEN_FUTURE_ACCESS",
    "POST_RESULT_POLICY_OPTIMIZATION",
    "LEGACY_EXECUTION_OR_IMPORT",
    "GAME_COUNT_OR_SEED_ASSIGNMENT_MISMATCH",
    "PAIRED_ENVIRONMENT_OR_SEARCH_SEED_MISMATCH",
    "STANDARD_EXPLORATORY_MODE_MIXING",
    "MANIFEST_REPLAY_OR_AGGREGATION_MISMATCH",
    "FULL_STUDY_ATTEMPT_BEFORE_SEPARATE_AUTHORIZATION",
)
'''
    text = replace_once(text, allowlist, schema, "schema constants")

    exact = '''def _exact(value: object, expected: object, label: str) -> None:
    if value != expected:
        raise PhaseCControlError(f"{label} must be {expected!r}, received {value!r}")
'''
    exact_with_keys = exact + '''\n\ndef _exact_keys(
    mapping: Mapping[str, Any], expected: frozenset[str], label: str
) -> None:
    actual = set(mapping)
    if actual != expected:
        missing = sorted(expected - actual)
        unknown = sorted(actual - expected)
        raise PhaseCControlError(
            f"{label} field set mismatch: missing={missing}, unknown={unknown}"
        )
'''
    text = replace_once(text, exact, exact_with_keys, "exact-key helper")

    old_scope = '''def _validate_scope(payload: Mapping[str, Any]) -> None:
    full_study = _mapping(payload.get("full_study"), "full_study")
    search = _mapping(payload.get("exploratory_search"), "exploratory_search")
    model = _mapping(payload.get("game_model"), "game_model")
    deck = _mapping(payload.get("deck"), "deck")
    measurement = _mapping(payload.get("measurement"), "measurement")
    mulligan = _mapping(payload.get("mulligan"), "mulligan")
    prerequisites = _mapping(payload.get("prerequisites"), "prerequisites")
    paired = _mapping(payload.get("paired_analysis"), "paired_analysis")
'''
    new_scope = '''def _validate_scope(payload: Mapping[str, Any]) -> None:
    _exact_keys(payload, _CONFIG_TOP_LEVEL_KEYS, "Phase C pilot configuration")
    authorization = _mapping(payload.get("authorization"), "authorization")
    full_study = _mapping(payload.get("full_study"), "full_study")
    search = _mapping(payload.get("exploratory_search"), "exploratory_search")
    model = _mapping(payload.get("game_model"), "game_model")
    deck = _mapping(payload.get("deck"), "deck")
    measurement = _mapping(payload.get("measurement"), "measurement")
    mulligan = _mapping(payload.get("mulligan"), "mulligan")
    prerequisites = _mapping(payload.get("prerequisites"), "prerequisites")
    paired = _mapping(payload.get("paired_analysis"), "paired_analysis")
    pilot = _mapping(payload.get("pilot"), "pilot")
    policy = _mapping(payload.get("policy"), "policy")
    for label, section in (
        ("authorization", authorization),
        ("deck", deck),
        ("exploratory_search", search),
        ("full_study", full_study),
        ("game_model", model),
        ("measurement", measurement),
        ("mulligan", mulligan),
        ("paired_analysis", paired),
        ("pilot", pilot),
        ("policy", policy),
        ("prerequisites", prerequisites),
    ):
        _exact_keys(section, _CONFIG_SECTION_KEYS[label], label)
'''
    text = replace_once(text, old_scope, new_scope, "closed config schema")

    text = replace_once(
        text,
        '    _exact(full_study.get("execution_allowed"), False, "full-study flag")\n',
        '    _exact(\n        full_study.get("authorization_status"),\n        "LOCKED_PENDING_POST_PILOT_REVIEW",\n        "full-study authorization status",\n    )\n'
        '    _exact(full_study.get("execution_allowed"), False, "full-study flag")\n',
        "full-study status",
    )
    text = replace_once(
        text,
        '    _exact(model.get("opponent_wins_modeled"), False, "opponent wins")\n',
        '    _exact(model.get("opponent_wins_modeled"), False, "opponent wins")\n'
        '    _exact(model.get("glint_horn_may_attack_when_legal"), True, "Glint-Horn attack model")\n'
        '    _exact(model.get("malcolm_may_connect_when_legal"), True, "Malcolm connection model")\n',
        "attack/connect assumptions",
    )
    objective = '''    _exact(
        measurement.get("objective"),
        "MAXIMIZE_LEGAL_DETERMINISTIC_TABLE_WIN_ACCESS",
        "measurement objective",
    )
'''
    text = replace_once(
        text,
        objective,
        objective
        + '    _exact(measurement.get("required_outputs"), list(_REQUIRED_OUTPUTS), "required outputs")\n',
        "required outputs",
    )
    reporting = '''    _exact(
        paired.get("required_reporting_sentence"), REPORTING_SENTENCE, "paired reporting sentence"
    )
'''
    text = replace_once(
        text,
        reporting,
        reporting
        + '    _exact(payload.get("stop_conditions"), list(_STOP_CONDITIONS), "stop conditions")\n',
        "stop conditions",
    )

    old_namespaces = '''    environment_namespace = str(pilot.get("environment_seed_namespace", ""))
    search_namespace = str(pilot.get("exploratory_search_seed_namespace", ""))
    if not environment_namespace or not search_namespace:
        raise PhaseCControlError(
            "environment and exploratory search seed namespaces must be nonempty"
        )
    if environment_namespace == search_namespace:
        raise PhaseCControlError(
            "environment and exploratory search seed namespaces must be distinct"
        )
'''
    new_namespaces = '''    environment_namespace = str(pilot.get("environment_seed_namespace", ""))
    search_namespace = str(pilot.get("exploratory_search_seed_namespace", ""))
    _exact(
        environment_namespace,
        "phase-c-pilot-standard-v1",
        "standard environment seed namespace",
    )
    _exact(
        search_namespace,
        "phase-c-pilot-exploratory-search-v1",
        "exploratory search seed namespace",
    )
'''
    text = replace_once(text, old_namespaces, new_namespaces, "seed namespaces")

    policy_validation = '''    if not policy_id or not evaluator_id:
        raise PhaseCControlError("Phase C policy identity is incomplete")
    if not all(_is_sha256(value) for value in (policy_hash, evaluator_hash, learning_hash)):
        raise PhaseCControlError("Phase C policy digests are incomplete")
'''
    policy_frozen = policy_validation + '''    _exact(policy_id, "anchor_balanced", "standard policy config ID")
    _exact(
        policy_hash,
        "d10bc384f254ab7684ea62b45340d86349f36e4d9786a9d639a9c7c6ce38f800",
        "standard policy config hash",
    )
    _exact(evaluator_id, "contextual_combo_v1", "evaluator snapshot ID")
    _exact(
        evaluator_hash,
        "86c5e07daaa86362a38fad7a66d712443e32ba8af743bcaaa15576207264eca2",
        "evaluator snapshot hash",
    )
    _exact(
        learning_hash,
        "4884586c492c62cfd009c0a53c6d4ddd888274771c10efddc2b1853745a685e2",
        "learning plan hash",
    )
'''
    text = replace_once(text, policy_validation, policy_frozen, "frozen policy identity")

    path.write_text(text, encoding="utf-8")


def rewrite_governance_tests() -> None:
    path = ROOT / "tests/phase_c/test_phase_c_governance_binding.py"
    path.write_text(
        '''from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

import pytest

import mtg_runs.phase_c as phase_c

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import _phase_b_paths  # noqa: E402

CONFIG_PATH = "docs/spec/phase-c/PHASE_C_PILOT_CONFIG.json"
GUARDRAIL_PATH = "docs/spec/phase-c/NO_OPPONENT_POLICY_GUARDRAIL.json"
HANDOFF_PROTOCOL = ROOT / "docs/audit/handoff/PROTOCOL.md"
PILOT_WORKFLOW = ROOT / ".github/workflows/phase-c-pilot.yml"


def test_phase_b_certification_surface_is_disjoint_from_activation_allowlist() -> None:
    assert set(_phase_b_paths.COVERED_PATHS).isdisjoint(phase_c._ACTIVATION_ALLOWLIST)
    assert CONFIG_PATH in phase_c._ACTIVATION_ALLOWLIST
    assert CONFIG_PATH not in _phase_b_paths.COVERED_PATHS
    assert GUARDRAIL_PATH in _phase_b_paths.COVERED_PATHS


def test_pilot_workflow_checks_phase_b_before_authorization_without_deadlock() -> None:
    text = PILOT_WORKFLOW.read_text(encoding="utf-8")
    assert text.index("Durable Phase B certification") < text.index(
        "Validate implementation and governance-only activation"
    )
    assert set(_phase_b_paths.COVERED_PATHS).isdisjoint(phase_c._ACTIVATION_ALLOWLIST)


def test_activation_config_mutation_does_not_stale_phase_b_surface(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for relative in (CONFIG_PATH, GUARDRAIL_PATH):
        source = ROOT / relative
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    monkeypatch.setattr(_phase_b_paths, "ROOT", tmp_path)
    monkeypatch.setattr(_phase_b_paths, "COVERED_PATHS", (GUARDRAIL_PATH,))
    before_surface = _phase_b_paths.all_digests()
    config_path = tmp_path / CONFIG_PATH
    before_config_sha = hashlib.sha256(config_path.read_bytes()).hexdigest()

    payload = json.loads(config_path.read_text(encoding="utf-8"))
    authorization = payload["authorization"]
    assert isinstance(authorization, dict)
    authorization.update(
        {
            "execution_allowed": True,
            "status": "AUTHORIZED",
            "approved_by": "Jeff Toney",
            "approved_at": "2026-08-12T00:00:00Z",
        }
    )
    config_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\\n", encoding="utf-8")

    after_config_sha = hashlib.sha256(config_path.read_bytes()).hexdigest()
    after_surface = _phase_b_paths.all_digests()
    assert after_config_sha != before_config_sha
    assert after_surface == before_surface


def test_no_opponent_guardrail_mutation_changes_phase_b_certification_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = ROOT / GUARDRAIL_PATH
    target = tmp_path / GUARDRAIL_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    monkeypatch.setattr(_phase_b_paths, "ROOT", tmp_path)
    monkeypatch.setattr(_phase_b_paths, "COVERED_PATHS", (GUARDRAIL_PATH,))
    before_paths = _phase_b_paths.all_digests()
    before_aggregate = _phase_b_paths.aggregate_digest(before_paths)
    target.write_text(target.read_text(encoding="utf-8") + "\\n", encoding="utf-8")
    after_paths = _phase_b_paths.all_digests()
    after_aggregate = _phase_b_paths.aggregate_digest(after_paths)
    assert after_paths[GUARDRAIL_PATH] != before_paths[GUARDRAIL_PATH]
    assert after_aggregate != before_aggregate


def test_handoff_protocol_requires_machine_state_reconciliation() -> None:
    text = " ".join(HANDOFF_PROTOCOL.read_text(encoding="utf-8").split())
    assert "## Machine-state reconciliation checklist" in text
    for required in (
        "PR merged",
        "Exact `main` identified",
        "CI green",
        "Certification current",
        "Handoff current",
        "Diagnostic completed",
        "Audit completed",
        "Report created",
        "Owner package ready",
        "byte count greater than zero",
        "workflow run ID and head SHA",
    ):
        assert required in text
''',
        encoding="utf-8",
    )


def rewrite_study_tests() -> None:
    path = ROOT / "tests/phase_c/test_phase_c_study_binding.py"
    path.write_text(
        '''from __future__ import annotations

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
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\\n", encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("section", "key", "value", "message"),
    [
        ("paired_analysis", "primary_outcome", "WIN_RATE", "paired primary outcome"),
        ("paired_analysis", "outcome_name", "RENAMED", "paired outcome name"),
        ("paired_analysis", "effect_threshold_rule", "ACT_ON_ANYTHING", "paired effect-threshold rule"),
        ("paired_analysis", "secondary_outcome", "INVALID_SECONDARY", "paired secondary outcome"),
        ("paired_analysis", "secondary_censoring_rule", "IMPUTE_TURN_11", "paired secondary censoring rule"),
        ("paired_analysis", "checkpoint_turn", 7, "paired checkpoint"),
        ("measurement", "primary_checkpoint", 7, "primary checkpoint"),
        ("paired_analysis", "required_reporting_sentence", "This is a renamed statement.", "paired reporting sentence"),
        ("deck", "exact_library_count", 97, "exact library count"),
        ("deck", "physical_card_count", 99, "physical card count"),
        ("deck", "source", "docs/source/not-the-deck.txt", "deck source"),
        ("pilot", "environment_seed_namespace", "mutated-standard-namespace", "standard environment seed namespace"),
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
''',
        encoding="utf-8",
    )


def strengthen_activation_regression() -> None:
    path = ROOT / "tests/phase_c/test_phase_c_control.py"
    text = path.read_text(encoding="utf-8")
    anchor = '''    assert loaded_approval.implementation_commit == implementation
    assert context.implementation_tree == tree
    assert activation != implementation
'''
    text = replace_once(
        text,
        anchor,
        anchor + '    assert not (root / "artifacts").exists()\n',
        "activation no-artifact assertion",
    )
    path.write_text(text, encoding="utf-8")


def main() -> None:
    repair_phase_b_surface()
    repair_phase_c_loader()
    rewrite_governance_tests()
    rewrite_study_tests()
    strengthen_activation_regression()


if __name__ == "__main__":
    main()
