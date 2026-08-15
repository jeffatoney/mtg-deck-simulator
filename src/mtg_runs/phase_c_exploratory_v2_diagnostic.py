"""Arm-separated, non-authorized diagnostic execution for exploratory V2."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from mtg_runs.phase_c_exploratory_v2 import (
    ExploratoryV2DecisionRecord,
    recompute_decision_evidence_in_fresh_process,
    run_exploratory_v2_game_execution,
)
from mtg_search.directed_v2 import ARM_IDS, canonical_sha256, load_directed_arm_config

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "artifacts/phase-c-exploratory-v2-diagnostic"
SCORING_CONFIG = ROOT / "configs/evaluators/exploratory_v2_scoring.yaml"
FORBIDDEN_ROOTS = (
    ROOT / "artifacts/phase-c-shards",
    ROOT / "artifacts/phase-c-pilot",
)
_COMMANDERS = frozenset({"Malcolm, Keen-Eyed Navigator", "Breeches, Brazen Plunderer"})
_SEARCH_MARKERS = ("TUTOR", "SEARCH", "TRANSMUTE", "TYPECYCLE", "LANDCYCLE")
DIGEST_SEMANTICS = "EXACT_SERIALIZED_FILE_BYTES_V1"
GAME_SCHEMA = "phase-c-exploratory-v2-diagnostic-game-v2"
SUMMARY_SCHEMA = "phase-c-exploratory-v2-diagnostic-summary-v2"
MANIFEST_SCHEMA = "phase-c-exploratory-v2-diagnostic-manifest-v2"
_V1_MANIFEST_SCHEMA = "phase-c-exploratory-v2-diagnostic-manifest-v1"


def _assert_non_authorized_workspace(output_root: Path) -> None:
    if any(path.exists() for path in FORBIDDEN_ROOTS):
        raise ValueError("exploratory V2 diagnostic refuses a workspace with pilot artifact roots")
    forbidden_parts = {"phase-c-shards", "phase-c-pilot"}
    if forbidden_parts.intersection(output_root.parts):
        raise ValueError("exploratory V2 diagnostic output cannot target a pilot artifact root")


def _serialized_json_bytes(payload: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _write_json_bytes(path: Path, payload: Mapping[str, Any]) -> bytes:
    body = _serialized_json_bytes(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return body


def _file_record(*, relative_path: str, body: bytes) -> dict[str, Any]:
    return {
        "relative_path": relative_path,
        "byte_size": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
    }


def _scoring_digest() -> str:
    payload = json.loads(SCORING_CONFIG.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("exploratory V2 scoring config must be a JSON object")
    return canonical_sha256(payload)


def _selected_candidate(decision: ExploratoryV2DecisionRecord) -> Mapping[str, Any]:
    selected = [
        item
        for item in decision.candidate_evaluations
        if item.get("handle") == decision.selected_action
    ]
    if len(selected) != 1:
        raise ValueError("exploratory V2 decision does not identify exactly one selected candidate")
    return selected[0]


def _semantic_payload(candidate: Mapping[str, Any]) -> Mapping[str, Any]:
    semantic_key = str(candidate.get("semantic_key", ""))
    if not semantic_key.startswith("{"):
        return {}
    value = json.loads(semantic_key)
    return value if isinstance(value, Mapping) else {}


def _useful_discovery_classification(
    decision: ExploratoryV2DecisionRecord,
    candidate: Mapping[str, Any],
) -> str | None:
    semantic = _semantic_payload(candidate)
    kind = str(semantic.get("kind", ""))
    if kind == "PASS_PRIORITY" or not kind:
        return None
    identity = str(semantic.get("identity", ""))
    raw_tags = semantic.get("tags", ())
    tags = tuple(str(value).upper() for value in raw_tags) if isinstance(raw_tags, Sequence) else ()
    metadata = semantic.get("metadata")
    metadata_map = metadata if isinstance(metadata, Mapping) else {}
    score = candidate.get("score")
    score_map = score if isinstance(score, Mapping) else {}

    if bool(score_map.get("immediate_deterministic_access")) or bool(
        score_map.get("projected_deterministic_access")
    ):
        return "NEW_DETERMINISTIC_ACCESS_LINE"
    if str(score_map.get("conditional_access_status", "NONE")) in {"PROGRESS", "AVAILABLE"}:
        return "NEW_CONDITIONAL_ACCESS_LINE"
    if metadata_map.get("modes") or metadata_map.get("mode"):
        return "NEW_MODAL_SELECTION"
    if kind in {"ACTIVATE", "ACTIVATE_HAND"}:
        return "NEW_ACTIVATED_ABILITY_LINE"
    if identity in _COMMANDERS:
        return "NEW_COMMANDER_SEQUENCE"
    interaction_text = " ".join(
        (identity, kind, *tags, json.dumps(metadata_map, sort_keys=True))
    ).upper()
    if "DRAW" in interaction_text or "DISCARD" in interaction_text:
        return "NEW_DRAW_OR_DISCARD_SEQUENCE"
    if decision.selected_plan_or_package_id:
        return "NEW_PACKAGE_SEQUENCE"
    if kind == "PLAY_LAND" or int(score_map.get("mana_development_value", 0)) > 0:
        return "NEW_MANA_SEQUENCE"
    return None


def _record_useful_discovery(
    *,
    decision: ExploratoryV2DecisionRecord,
    candidate: Mapping[str, Any],
    signatures: Counter[str],
    classifications: Counter[str],
) -> bool:
    classification = _useful_discovery_classification(decision, candidate)
    if classification is None:
        return False
    signature = canonical_sha256(
        {
            "classification": classification,
            "purpose": decision.strategic_choice_purpose,
            "semantic_action": _semantic_payload(candidate),
            "package_id": decision.selected_plan_or_package_id,
        }
    )
    prior = signatures[signature]
    signatures[signature] += 1
    classifications["REVISITED_UNDEREXPLORED_LINE" if prior else classification] += 1
    return True


def _record_strategic_discovery(
    record: Mapping[str, Any],
    signatures: Counter[str],
    classifications: Counter[str],
) -> bool:
    purpose = str(record.get("strategic_choice_purpose", "")).upper()
    if purpose == "MULLIGAN" or not any(marker in purpose for marker in _SEARCH_MARKERS):
        return False
    selected_handle = record.get("selected_action")
    evaluations = record.get("candidate_evaluations")
    if not isinstance(selected_handle, str) or not isinstance(evaluations, Sequence):
        return False
    selected = [
        item
        for item in evaluations
        if isinstance(item, Mapping) and item.get("handle") == selected_handle
    ]
    if len(selected) != 1:
        return False
    signature = canonical_sha256(
        {
            "classification": "NEW_TUTOR_TARGET",
            "purpose": purpose,
            "semantic_key": selected[0].get("semantic_key"),
        }
    )
    prior = signatures[signature]
    signatures[signature] += 1
    classifications["REVISITED_UNDEREXPLORED_LINE" if prior else "NEW_TUTOR_TARGET"] += 1
    return True


def _counter_payment_records(replay_transcript: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    raw_choices = replay_transcript.get("choices", ())
    if not isinstance(raw_choices, Sequence):
        return ()
    records: list[Mapping[str, Any]] = []
    for choice in raw_choices:
        if not isinstance(choice, Mapping) or str(choice.get("kind", "")) != "COUNTER_UNLESS_PAY":
            continue
        selected = choice.get("selected")
        if isinstance(selected, Mapping) and selected.get("schema_version") == "counter-payment-choice-v2":
            records.append(selected)
    return tuple(records)


def artifact_schema_classification(manifest: Mapping[str, Any]) -> str:
    schema = str(manifest.get("schema_version", ""))
    if schema == MANIFEST_SCHEMA:
        return "FINAL_V2_EXACT_BYTES"
    if schema == _V1_MANIFEST_SCHEMA:
        return "SUPERSEDED_FOR_FINAL_CLOSEOUT"
    return "UNSUPPORTED"


def verify_exact_serialized_artifact(arm_root: Path) -> Mapping[str, Any]:
    """Verify a V2 arm from exact downloaded file bytes, with no key restoration."""

    manifest_path = arm_root / "NON_AUTHORIZED_DIAGNOSTIC-manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if not isinstance(manifest, Mapping):
        raise ValueError("diagnostic manifest must be a JSON object")
    classification = artifact_schema_classification(manifest)
    if classification != "FINAL_V2_EXACT_BYTES":
        raise ValueError(f"diagnostic manifest is not final exact-byte evidence: {classification}")
    if manifest.get("digest_semantics") != DIGEST_SEMANTICS:
        raise ValueError("diagnostic manifest digest semantics are not exact serialized bytes")

    raw_inventory = manifest.get("game_file_inventory")
    if not isinstance(raw_inventory, list) or not raw_inventory:
        raise ValueError("diagnostic manifest omits game-file inventory")
    inventory = [dict(item) for item in raw_inventory if isinstance(item, Mapping)]
    if len(inventory) != len(raw_inventory):
        raise ValueError("diagnostic game-file inventory is malformed")
    expected_order = sorted(inventory, key=lambda item: str(item.get("relative_path", "")))
    if inventory != expected_order:
        raise ValueError("diagnostic game-file inventory is not in canonical path order")
    if canonical_sha256(inventory) != manifest.get("game_file_inventory_sha256"):
        raise ValueError("diagnostic game-file inventory digest mismatch")

    listed_paths = {str(item["relative_path"]) for item in inventory}
    actual_paths = {
        path.relative_to(arm_root).as_posix()
        for path in (arm_root / "games").glob("*.json")
        if path.is_file()
    }
    if actual_paths != listed_paths:
        raise ValueError("diagnostic game-file set differs from the exact manifest inventory")
    for item in inventory:
        relative = str(item["relative_path"])
        body = (arm_root / relative).read_bytes()
        if len(body) != int(item.get("byte_size", -1)):
            raise ValueError(f"diagnostic game-file byte size mismatch: {relative}")
        if hashlib.sha256(body).hexdigest() != str(item.get("sha256", "")):
            raise ValueError(f"diagnostic game-file SHA-256 mismatch: {relative}")

    summary_path = arm_root / str(manifest.get("summary_file_path", ""))
    summary_body = summary_path.read_bytes()
    if len(summary_body) != int(manifest.get("summary_byte_size", -1)):
        raise ValueError("diagnostic summary byte size mismatch")
    if hashlib.sha256(summary_body).hexdigest() != manifest.get("summary_file_sha256"):
        raise ValueError("diagnostic summary exact file SHA-256 mismatch")
    summary = json.loads(summary_body)
    if not isinstance(summary, Mapping) or summary.get("schema_version") != SUMMARY_SCHEMA:
        raise ValueError("diagnostic summary schema is not final V2")
    if summary.get("game_file_inventory_sha256") != manifest.get("game_file_inventory_sha256"):
        raise ValueError("diagnostic summary and manifest inventory digests differ")
    return {
        "status": "PASS",
        "digest_semantics": DIGEST_SEMANTICS,
        "game_count": len(inventory),
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "summary_file_sha256": hashlib.sha256(summary_body).hexdigest(),
        "game_file_inventory_sha256": manifest["game_file_inventory_sha256"],
    }


def run_arm_diagnostic(*, arm_id: str, output_root: Path = DEFAULT_OUTPUT) -> Mapping[str, Any]:
    """Run the predetermined diagnostic seeds for exactly one V2 arm."""

    _assert_non_authorized_workspace(output_root)
    config = load_directed_arm_config(arm_id)
    if config.pilot_activation:
        raise ValueError("diagnostic refuses pilot-active arm config")
    scoring_sha256 = _scoring_digest()
    arm_root = output_root / arm_id.lower()
    game_file_inventory: list[dict[str, Any]] = []
    package_visitation: Counter[str] = Counter()
    actual_attempts: Counter[str] = Counter()
    discovery_signatures: Counter[str] = Counter()
    discovery_types: Counter[str] = Counter()
    selected_action_kinds: Counter[str] = Counter()
    replay_passes = 0
    decision_recompute_passes = 0
    baseline_retained = baseline_required = 0
    vectors_persisted = vectors_required = 0
    land_compliant = land_applicable = 0
    priority_decisions = 0
    standard_divergences = 0
    seeded_selections = 0
    useful_discovery_selections = 0
    games_with_productive_priority_action = 0
    counter_payment_choices = 0
    counter_payment_pay_available = 0
    counter_payment_pay_selected = 0
    counter_payment_decline_selected = 0
    counter_payment_replay_bindings = 0

    seeds = tuple(
        zip(
            config.diagnostic_environment_seeds,
            config.diagnostic_exploration_seeds,
            strict=True,
        )
    )
    for offset, (seed, exploration_seed) in enumerate(seeds, start=1):
        execution = run_exploratory_v2_game_execution(
            seed=seed,
            arm_id=arm_id,
            exploration_seed=exploration_seed,
            game_index=offset,
            through_turn=10,
            validate_fresh_replay=True,
        )
        game = execution.technical_game
        replay_passes += int(game.final_state_hash == game.fresh_replay_state_hash)
        fresh = recompute_decision_evidence_in_fresh_process(
            seed=seed,
            arm_id=arm_id,
            exploration_seed=exploration_seed,
            game_index=offset,
            through_turn=10,
        )
        reproduced = (
            fresh.get("final_state_hash") == game.final_state_hash
            and fresh.get("replay_digest") == game.replay_digest
            and fresh.get("decision_evidence_sha256") == game.decision_evidence_sha256
        )
        decision_recompute_passes += int(reproduced)
        if not reproduced:
            raise ValueError("fresh-process V2 decision recomputation diverged")
        baseline_retained += game.baseline_candidate_retained
        baseline_required += game.baseline_candidate_required
        vectors_persisted += game.candidate_score_vectors_persisted
        vectors_required += game.candidate_score_vectors_required
        land_compliant += game.land_guardrail_compliant
        land_applicable += game.land_guardrail_applicable

        productive_this_game = False
        for decision in game.decisions:
            priority_decisions += 1
            standard_divergences += int(
                decision.selected_action != decision.standard_baseline_handle
            )
            seeded_selections += int(decision.randomness_affected_selection)
            if decision.selected_plan_or_package_id:
                package_visitation[decision.selected_plan_or_package_id] += 1
            selected = _selected_candidate(decision)
            semantic = _semantic_payload(selected)
            kind = str(semantic.get("kind", "UNKNOWN"))
            selected_action_kinds[kind] += 1
            if kind != "PASS_PRIORITY":
                productive_this_game = True
            useful_discovery_selections += int(
                _record_useful_discovery(
                    decision=decision,
                    candidate=selected,
                    signatures=discovery_signatures,
                    classifications=discovery_types,
                )
            )
        games_with_productive_priority_action += int(productive_this_game)
        for strategic in game.strategic_choice_records:
            useful_discovery_selections += int(
                _record_strategic_discovery(
                    strategic,
                    discovery_signatures,
                    discovery_types,
                )
            )
        for combo in execution.measurement.combo_records:
            if combo.attempted:
                actual_attempts[combo.package] += 1

        payment_records = _counter_payment_records(execution.replay_transcript)
        counter_payment_choices += len(payment_records)
        counter_payment_pay_available += sum(
            bool(record.get("pay_legally_available")) for record in payment_records
        )
        counter_payment_pay_selected += sum(
            str(record.get("outcome", "")) == "PAY" for record in payment_records
        )
        counter_payment_decline_selected += sum(
            str(record.get("outcome", "")) == "DECLINE" for record in payment_records
        )
        counter_payment_replay_bindings += sum(
            isinstance(record.get("replay_binding"), Mapping) for record in payment_records
        )

        payload = {
            "schema_version": GAME_SCHEMA,
            "digest_semantics": DIGEST_SEMANTICS,
            "artifact_classification": "NON_AUTHORIZED_DIAGNOSTIC",
            "authorized_execution": False,
            "pilot_result": False,
            "arm_id": arm_id,
            "arm_config_sha256": config.config_sha256,
            "scoring_config_sha256": scoring_sha256,
            "game_index": offset,
            "technical_game": game.to_dict(),
            "measurement": execution.measurement.to_dict(),
            "resolution_choice_records": [dict(record) for record in payment_records],
            "fresh_policy_recompute": dict(fresh),
        }
        relative_path = f"games/game-{offset:04d}.json"
        body = _write_json_bytes(arm_root / relative_path, payload)
        game_file_inventory.append(_file_record(relative_path=relative_path, body=body))

    game_count = len(game_file_inventory)
    duplicate_discoveries = sum(count - 1 for count in discovery_signatures.values() if count > 1)
    unique_discoveries = len(discovery_signatures)
    selected_nonpass = sum(
        count for kind, count in selected_action_kinds.items() if kind != "PASS_PRIORITY"
    )
    selected_pass = selected_action_kinds.get("PASS_PRIORITY", 0)
    game_file_inventory.sort(key=lambda item: str(item["relative_path"]))
    inventory_sha256 = canonical_sha256(game_file_inventory)
    summary = {
        "schema_version": SUMMARY_SCHEMA,
        "digest_semantics": DIGEST_SEMANTICS,
        "artifact_classification": "NON_AUTHORIZED_DIAGNOSTIC",
        "authorized_execution": False,
        "pilot_measurement_artifacts_created": 0,
        "arm_id": arm_id,
        "reporting_label": config.reporting_label,
        "arm_config_sha256": config.config_sha256,
        "scoring_config_sha256": scoring_sha256,
        "environment_seed_sha256": canonical_sha256(config.diagnostic_environment_seeds),
        "exploration_seed_sha256": canonical_sha256(config.diagnostic_exploration_seeds),
        "game_count": game_count,
        "fresh_transcript_replay_pass": replay_passes,
        "fresh_transcript_replay_fail": game_count - replay_passes,
        "fresh_policy_recompute_pass": decision_recompute_passes,
        "fresh_policy_recompute_fail": game_count - decision_recompute_passes,
        "baseline_candidate_retained": baseline_retained,
        "baseline_candidate_required": baseline_required,
        "candidate_score_vectors_persisted": vectors_persisted,
        "candidate_score_vectors_required": vectors_required,
        "land_guardrail_compliant": land_compliant,
        "land_guardrail_applicable": land_applicable,
        "priority_decision_count": priority_decisions,
        "standard_divergence_count": standard_divergences,
        "seeded_selection_count": seeded_selections,
        "selected_action_kind_counts": dict(sorted(selected_action_kinds.items())),
        "selected_pass_priority_count": selected_pass,
        "selected_nonpass_action_count": selected_nonpass,
        "games_with_productive_priority_action": games_with_productive_priority_action,
        "package_visitation": dict(sorted(package_visitation.items())),
        "actual_attempts": dict(sorted(actual_attempts.items())),
        "unique_canonical_interaction_signatures": unique_discoveries,
        "useful_discovery_selection_count": useful_discovery_selections,
        "discovery_types": dict(sorted(discovery_types.items())),
        "duplicate_discovery_count": duplicate_discoveries,
        "duplicate_discovery_rate": (
            duplicate_discoveries / sum(discovery_signatures.values())
            if discovery_signatures
            else 0.0
        ),
        "discovery_yield_per_game": unique_discoveries / game_count,
        "counter_payment_choice_count": counter_payment_choices,
        "counter_payment_pay_available_count": counter_payment_pay_available,
        "counter_payment_pay_selected_count": counter_payment_pay_selected,
        "counter_payment_decline_selected_count": counter_payment_decline_selected,
        "counter_payment_replay_binding_count": counter_payment_replay_bindings,
        "game_file_inventory": game_file_inventory,
        "game_file_inventory_sha256": inventory_sha256,
        # Retained name, but v2 semantics are explicitly the ordered exact-file inventory.
        "game_payload_sha256": inventory_sha256,
    }
    summary_path = "NON_AUTHORIZED_DIAGNOSTIC-summary.json"
    summary_body = _write_json_bytes(arm_root / summary_path, summary)
    manifest = {
        "schema_version": MANIFEST_SCHEMA,
        "digest_semantics": DIGEST_SEMANTICS,
        "artifact_classification": "NON_AUTHORIZED_DIAGNOSTIC",
        "authorized_execution": False,
        "pilot_activation": False,
        "arm_id": arm_id,
        "reporting_label": config.reporting_label,
        "arm_config_sha256": config.config_sha256,
        "scoring_config_sha256": scoring_sha256,
        "environment_seeds": list(config.diagnostic_environment_seeds),
        "exploration_seeds": list(config.diagnostic_exploration_seeds),
        "environment_seed_sha256": canonical_sha256(config.diagnostic_environment_seeds),
        "exploration_seed_sha256": canonical_sha256(config.diagnostic_exploration_seeds),
        "summary_file_path": summary_path,
        "summary_byte_size": len(summary_body),
        "summary_file_sha256": hashlib.sha256(summary_body).hexdigest(),
        "game_file_inventory": game_file_inventory,
        "game_file_inventory_sha256": inventory_sha256,
        "game_count": game_count,
    }
    _write_json_bytes(arm_root / "NON_AUTHORIZED_DIAGNOSTIC-manifest.json", manifest)
    _assert_non_authorized_workspace(output_root)
    verify_exact_serialized_artifact(arm_root)
    return summary


def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arm-id", required=True, choices=sorted(ARM_IDS))
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    summary = run_arm_diagnostic(arm_id=args.arm_id, output_root=args.output_root)
    print(json.dumps(summary, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
