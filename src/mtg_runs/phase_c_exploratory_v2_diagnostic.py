"""Arm-separated, non-authorized diagnostic execution for exploratory V2."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from mtg_runs.phase_c_exploratory_v2 import (
    recompute_decision_evidence_in_fresh_process,
    run_exploratory_v2_game_execution,
)
from mtg_search.directed_v2 import ARM_IDS, canonical_sha256, load_directed_arm_config

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "artifacts/phase-c-exploratory-v2-diagnostic"
FORBIDDEN_ROOTS = (
    ROOT / "artifacts/phase-c-shards",
    ROOT / "artifacts/phase-c-pilot",
)


def _assert_non_authorized_workspace(output_root: Path) -> None:
    if any(path.exists() for path in FORBIDDEN_ROOTS):
        raise ValueError("exploratory V2 diagnostic refuses a workspace with pilot artifact roots")
    forbidden_parts = {"phase-c-shards", "phase-c-pilot"}
    if forbidden_parts.intersection(output_root.parts):
        raise ValueError("exploratory V2 diagnostic output cannot target a pilot artifact root")


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _discovery_type(kind: str, purpose: str, package: str | None) -> str:
    if purpose == "TUTOR":
        return "NEW_TUTOR_TARGET"
    if kind == "PLAY_LAND":
        return "NEW_MANA_SEQUENCE"
    if kind in {"ACTIVATE", "ACTIVATE_HAND"}:
        return "NEW_ACTIVATED_ABILITY_LINE"
    if "COMMANDER" in kind:
        return "NEW_COMMANDER_SEQUENCE"
    if package:
        return "NEW_PACKAGE_SEQUENCE"
    return "REVISITED_UNDEREXPLORED_LINE"


def run_arm_diagnostic(*, arm_id: str, output_root: Path = DEFAULT_OUTPUT) -> Mapping[str, Any]:
    """Run the predetermined diagnostic seeds for exactly one V2 arm."""

    _assert_non_authorized_workspace(output_root)
    config = load_directed_arm_config(arm_id)
    if config.pilot_activation:
        raise ValueError("diagnostic refuses pilot-active arm config")
    arm_root = output_root / arm_id.lower()
    games: list[dict[str, Any]] = []
    package_visitation: Counter[str] = Counter()
    actual_attempts: Counter[str] = Counter()
    discovery_signatures: Counter[str] = Counter()
    discovery_types: Counter[str] = Counter()
    replay_passes = 0
    decision_recompute_passes = 0
    baseline_retained = baseline_required = 0
    vectors_persisted = vectors_required = 0
    land_compliant = land_applicable = 0

    for offset, (seed, exploration_seed) in enumerate(
        zip(
            config.diagnostic_environment_seeds,
            config.diagnostic_exploration_seeds,
            strict=True,
        ),
        start=1,
    ):
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
        for decision in game.decisions:
            if decision.selected_plan_or_package_id:
                package_visitation[decision.selected_plan_or_package_id] += 1
            selected = next(
                item
                for item in decision.candidate_evaluations
                if item.get("handle") == decision.selected_action
            )
            signature = str(selected.get("semantic_key", ""))
            if signature:
                discovery_signatures[signature] += 1
            kind = str(json.loads(signature).get("kind", "")) if signature.startswith("{") else ""
            discovery_types[
                _discovery_type(kind, decision.strategic_choice_purpose, decision.selected_plan_or_package_id)
            ] += 1
        for strategic in game.strategic_choice_records:
            if strategic.get("strategic_choice_purpose") == "TUTOR":
                signature = f"TUTOR:{strategic.get('selected_action')}"
                discovery_signatures[signature] += 1
                discovery_types["NEW_TUTOR_TARGET"] += 1
        for combo in execution.measurement.combo_records:
            if combo.attempted:
                actual_attempts[combo.package] += 1
        payload = {
            "schema_version": "phase-c-exploratory-v2-diagnostic-game-v1",
            "artifact_classification": "NON_AUTHORIZED_DIAGNOSTIC",
            "authorized_execution": False,
            "pilot_result": False,
            "arm_id": arm_id,
            "game_index": offset,
            "technical_game": game.to_dict(),
            "measurement": execution.measurement.to_dict(),
            "fresh_policy_recompute": dict(fresh),
        }
        _write_json(arm_root / "games" / f"game-{offset:04d}.json", payload)
        games.append(payload)

    game_count = len(games)
    duplicate_discoveries = sum(count - 1 for count in discovery_signatures.values() if count > 1)
    unique_discoveries = len(discovery_signatures)
    summary = {
        "schema_version": "phase-c-exploratory-v2-diagnostic-summary-v1",
        "artifact_classification": "NON_AUTHORIZED_DIAGNOSTIC",
        "authorized_execution": False,
        "pilot_measurement_artifacts_created": 0,
        "arm_id": arm_id,
        "reporting_label": config.reporting_label,
        "arm_config_sha256": config.config_sha256,
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
        "package_visitation": dict(sorted(package_visitation.items())),
        "actual_attempts": dict(sorted(actual_attempts.items())),
        "unique_canonical_interaction_signatures": unique_discoveries,
        "discovery_types": dict(sorted(discovery_types.items())),
        "duplicate_discovery_count": duplicate_discoveries,
        "duplicate_discovery_rate": (
            duplicate_discoveries / sum(discovery_signatures.values())
            if discovery_signatures
            else 0.0
        ),
        "discovery_yield_per_game": unique_discoveries / game_count,
        "game_payload_sha256": canonical_sha256(games),
    }
    manifest = {
        "schema_version": "phase-c-exploratory-v2-diagnostic-manifest-v1",
        "artifact_classification": "NON_AUTHORIZED_DIAGNOSTIC",
        "authorized_execution": False,
        "pilot_activation": False,
        "arm_id": arm_id,
        "arm_config_sha256": config.config_sha256,
        "environment_seeds": list(config.diagnostic_environment_seeds),
        "exploration_seeds": list(config.diagnostic_exploration_seeds),
        "environment_seed_sha256": canonical_sha256(config.diagnostic_environment_seeds),
        "exploration_seed_sha256": canonical_sha256(config.diagnostic_exploration_seeds),
        "summary_sha256": canonical_sha256(summary),
        "game_count": game_count,
    }
    _write_json(arm_root / "NON_AUTHORIZED_DIAGNOSTIC-summary.json", summary)
    _write_json(arm_root / "NON_AUTHORIZED_DIAGNOSTIC-manifest.json", manifest)
    _assert_non_authorized_workspace(output_root)
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
