"""Non-authorized 700-seed Phase C diagnostic execution.

This module deliberately reuses the production game execution path while refusing
Phase C authorization and pilot artifact creation. Its only persistent outputs are
diagnostic JSON reports containing pass/fail execution metadata and distinct errors.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from mtg_runs.phase_c import (
    DEFAULT_CONFIG,
    PhaseCConfiguration,
    PhaseCControlError,
    _git as _phase_c_git,
    build_pilot_seed_plan,
    build_pilot_shard_assignment,
    load_phase_c_config,
)
from mtg_runs.phase_c_runner import run_phase_c_game_execution

ROOT = Path(__file__).resolve().parents[2]
DIAGNOSTIC_SCHEMA = "phase-c-prepilot-diagnostic-v1"
DIAGNOSTIC_SUMMARY_SCHEMA = "phase-c-prepilot-diagnostic-summary-v1"
FORBIDDEN_PILOT_ARTIFACT_ROOTS = (
    Path("artifacts/phase-c-shards"),
    Path("artifacts/phase-c-pilot"),
)
NO_OPPONENT_GUARDRAIL = ROOT / "docs/spec/phase-c/NO_OPPONENT_POLICY_GUARDRAIL.json"
PHASE_A_CERTIFICATION = ROOT / "docs/audit/phase-a-certification/CERTIFICATION.json"
PHASE_B_CERTIFICATION = ROOT / "docs/audit/phase-b-certification/CERTIFICATION.json"
DIAGNOSTIC_WORKFLOW = ROOT / ".github/workflows/phase-c-diagnostic.yml"
PROVENANCE_FIELDS = (
    "implementation_sha",
    "implementation_tree",
    "config_sha256",
    "no_opponent_policy_guardrail_sha256",
    "phase_a_certification_sha256",
    "phase_b_certification_sha256",
    "diagnostic_workflow_sha256",
    "diagnostic_run_id",
    "workflow_head_sha",
)


@dataclass(frozen=True)
class DiagnosticGameRecord:
    mode: str
    game_index: int
    seed: int
    pair_id: str | None
    paired_standard_game_index: int | None
    search_seed: int | None
    status: str
    controlled_turns_completed: int | None = None
    terminal_status: str | None = None
    command_count: int | None = None
    replay_digest: str | None = None
    final_state_hash: str | None = None
    fresh_replay_state_hash: str | None = None
    error_type: str | None = None
    reason: str | None = None
    error_signature: str | None = None

    def __post_init__(self) -> None:
        if self.mode not in {"STANDARD", "EXPLORATORY"}:
            raise ValueError("diagnostic game mode must be STANDARD or EXPLORATORY")
        if self.status == "PASS":
            if (
                self.error_type is not None
                or self.reason is not None
                or self.error_signature is not None
            ):
                raise ValueError("passing diagnostic game cannot contain error metadata")
            if not self.final_state_hash or self.fresh_replay_state_hash != self.final_state_hash:
                raise ValueError("passing diagnostic game requires matching fresh replay state")
        elif self.status == "FAIL":
            if not self.error_type or self.reason is None or not self.error_signature:
                raise ValueError("failing diagnostic game requires complete error metadata")
        else:
            raise ValueError("diagnostic game status must be PASS or FAIL")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _repository_file_sha256(path: Path) -> str:
    if not path.is_file():
        raise PhaseCControlError(f"diagnostic provenance file is missing: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_identity(root: Path) -> tuple[str, str]:
    return (
        _phase_c_git(root, "rev-parse", "HEAD"),
        _phase_c_git(root, "rev-parse", "HEAD^{tree}"),
    )


def _repository_provenance(config: PhaseCConfiguration) -> dict[str, str]:
    implementation_sha, implementation_tree = _git_identity(ROOT)
    return {
        "implementation_sha": implementation_sha,
        "implementation_tree": implementation_tree,
        "config_sha256": config.sha256,
        "no_opponent_policy_guardrail_sha256": _repository_file_sha256(NO_OPPONENT_GUARDRAIL),
        "phase_a_certification_sha256": _repository_file_sha256(PHASE_A_CERTIFICATION),
        "phase_b_certification_sha256": _repository_file_sha256(PHASE_B_CERTIFICATION),
        "diagnostic_workflow_sha256": _repository_file_sha256(DIAGNOSTIC_WORKFLOW),
        "diagnostic_run_id": os.environ.get("GITHUB_RUN_ID", "LOCAL"),
        "workflow_head_sha": os.environ.get("GITHUB_SHA", implementation_sha),
    }


def _error_metadata(exc: Exception) -> tuple[str, str, str]:
    error_type = type(exc).__name__
    reason = str(exc)
    signature = hashlib.sha256(_canonical({"error_type": error_type, "reason": reason})).hexdigest()
    return error_type, reason, signature


def _require_non_authorized_config(config: PhaseCConfiguration) -> None:
    if config.execution_allowed:
        raise PhaseCControlError("diagnostic execution refuses an authorized Phase C configuration")
    if config.authorization_status != "LOCKED_PENDING_OWNER_APPROVAL":
        raise PhaseCControlError(
            "diagnostic execution requires LOCKED_PENDING_OWNER_APPROVAL configuration"
        )


def _assert_no_pilot_artifacts(root: Path) -> None:
    present = [
        str(path)
        for relative in FORBIDDEN_PILOT_ARTIFACT_ROOTS
        if (path := root / relative).exists()
    ]
    if present:
        raise PhaseCControlError(
            f"diagnostic execution refuses a workspace containing pilot artifact roots: {present}"
        )


def _validate_diagnostic_output_root(output_root: Path) -> None:
    forbidden_names = {path.name for path in FORBIDDEN_PILOT_ARTIFACT_ROOTS}
    if any(part in forbidden_names for part in output_root.parts):
        raise PhaseCControlError("diagnostic output root cannot be a pilot artifact root")


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _distinct_errors(records: Sequence[DiagnosticGameRecord]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for record in records:
        if record.status != "FAIL":
            continue
        assert record.error_signature is not None
        assert record.error_type is not None
        assert record.reason is not None
        item = grouped.setdefault(
            record.error_signature,
            {
                "error_signature": record.error_signature,
                "error_type": record.error_type,
                "reason": record.reason,
                "count": 0,
                "occurrences": [],
            },
        )
        item["count"] = int(item["count"]) + 1
        occurrences = item["occurrences"]
        if not isinstance(occurrences, list):
            raise ValueError("diagnostic error occurrence collection is malformed")
        occurrences.append(
            {
                "mode": record.mode,
                "game_index": record.game_index,
                "seed": record.seed,
            }
        )
    return [grouped[key] for key in sorted(grouped)]


def run_diagnostic_shard(
    *,
    mode: str,
    shard_index: int,
    output_root: Path,
    config_path: Path = DEFAULT_CONFIG,
    root: Path = ROOT,
) -> Mapping[str, Any]:
    """Run one non-authorized production-equivalent diagnostic shard."""
    mode = mode.upper()
    _validate_diagnostic_output_root(output_root)
    _assert_no_pilot_artifacts(root)
    config = load_phase_c_config(config_path)
    _require_non_authorized_config(config)
    provenance = _repository_provenance(config)
    seeds = build_pilot_seed_plan(config)
    assignment = build_pilot_shard_assignment(config, seeds, mode=mode, shard_index=shard_index)

    records: list[DiagnosticGameRecord] = []
    for offset, seed in enumerate(assignment.seeds):
        game_index = assignment.first_game_index + offset
        try:
            execution = run_phase_c_game_execution(
                seed=seed,
                mode=mode,
                search_seed=assignment.search_seeds[offset],
                pair_id=assignment.pair_ids[offset],
                paired_standard_game_index=assignment.paired_standard_game_indexes[offset],
                policy_config_id=config.policy_config_id,
                through_turn=10,
                validate_fresh_replay=True,
                policy_actions=True,
            )
            technical = execution.technical_game
            if technical.pilot_result or technical.authorized_pilot_result:
                raise PhaseCControlError("diagnostic execution produced a pilot-classified result")
            records.append(
                DiagnosticGameRecord(
                    mode=mode,
                    game_index=game_index,
                    seed=seed,
                    pair_id=assignment.pair_ids[offset],
                    paired_standard_game_index=assignment.paired_standard_game_indexes[offset],
                    search_seed=assignment.search_seeds[offset],
                    status="PASS",
                    controlled_turns_completed=technical.controlled_turns_completed,
                    terminal_status=technical.terminal_status,
                    command_count=technical.command_count,
                    replay_digest=technical.replay_digest,
                    final_state_hash=technical.final_state_hash,
                    fresh_replay_state_hash=technical.fresh_replay_state_hash,
                )
            )
        except Exception as exc:  # diagnostic purpose is to retain every distinct failure
            error_type, reason, signature = _error_metadata(exc)
            records.append(
                DiagnosticGameRecord(
                    mode=mode,
                    game_index=game_index,
                    seed=seed,
                    pair_id=assignment.pair_ids[offset],
                    paired_standard_game_index=assignment.paired_standard_game_indexes[offset],
                    search_seed=assignment.search_seeds[offset],
                    status="FAIL",
                    error_type=error_type,
                    reason=reason,
                    error_signature=signature,
                )
            )

    failed = sum(record.status == "FAIL" for record in records)
    payload: dict[str, Any] = {
        **provenance,
        "schema_version": DIAGNOSTIC_SCHEMA,
        "diagnostic_only": True,
        "authorized_execution": False,
        "pilot_result": False,
        "pilot_measurement_artifacts_created": 0,
        "pilot_artifact_count": 0,
        "mode": mode,
        "shard_index": assignment.shard_index,
        "shard_count": assignment.shard_count,
        "first_game_index": assignment.first_game_index,
        "last_game_index": assignment.last_game_index,
        "game_count": len(records),
        "pass_count": len(records) - failed,
        "fail_count": failed,
        "config_sha256": config.sha256,
        "standard_seed_sha256": seeds.standard_sha256,
        "exploratory_seed_sha256": seeds.exploratory_sha256,
        "exploratory_search_seed_sha256": seeds.exploratory_search_sha256,
        "pair_assignment_sha256": seeds.pair_assignment_sha256,
        "production_equivalent_execution": True,
        "fresh_replay_required": True,
        "records": [record.to_dict() for record in records],
        "distinct_errors": _distinct_errors(records),
    }
    report_path = output_root / mode.lower() / f"shard-{shard_index:02d}" / "diagnostic-shard.json"
    _write_json(report_path, payload)
    _assert_no_pilot_artifacts(root)
    return payload


def _load_report(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise PhaseCControlError(f"diagnostic report is not a JSON object: {path}")
    return value


def aggregate_diagnostic_reports(
    *,
    shard_root: Path,
    output_root: Path,
    root: Path = ROOT,
) -> Mapping[str, Any]:
    """Collect all 700 diagnostic results and deduplicate their exact failures."""
    _validate_diagnostic_output_root(output_root)
    _assert_no_pilot_artifacts(root)
    paths = sorted(shard_root.rglob("diagnostic-shard.json"))
    reports = [_load_report(path) for path in paths]
    if len(reports) != 20:
        raise PhaseCControlError(
            f"diagnostic aggregate requires exactly 20 shard reports, found {len(reports)}"
        )
    provenance = {field: reports[0].get(field) for field in PROVENANCE_FIELDS}
    missing_provenance = [field for field, value in provenance.items() if not value]
    if missing_provenance:
        raise PhaseCControlError(f"diagnostic shard provenance is incomplete: {missing_provenance}")
    for report in reports[1:]:
        mismatched = [
            field for field in PROVENANCE_FIELDS if report.get(field) != provenance[field]
        ]
        if mismatched:
            raise PhaseCControlError(
                f"diagnostic aggregate rejects mixed provenance fields: {mismatched}"
            )

    seen_shards: set[tuple[str, int]] = set()
    records: list[DiagnosticGameRecord] = []
    for report in reports:
        if report.get("schema_version") != DIAGNOSTIC_SCHEMA:
            raise PhaseCControlError("diagnostic shard schema mismatch")
        if (
            report.get("diagnostic_only") is not True
            or report.get("authorized_execution") is not False
        ):
            raise PhaseCControlError("diagnostic shard is not explicitly non-authorized")
        if report.get("pilot_measurement_artifacts_created") != 0:
            raise PhaseCControlError("diagnostic shard claims pilot measurement artifact creation")
        mode = str(report.get("mode", ""))
        shard_index = int(report.get("shard_index", -1))
        key = (mode, shard_index)
        if key in seen_shards:
            raise PhaseCControlError(f"duplicate diagnostic shard report: {key}")
        seen_shards.add(key)
        raw_records = report.get("records")
        if not isinstance(raw_records, list):
            raise PhaseCControlError("diagnostic shard records are malformed")
        for raw in raw_records:
            if not isinstance(raw, Mapping):
                raise PhaseCControlError("diagnostic game record is malformed")
            records.append(DiagnosticGameRecord(**dict(raw)))

    expected_shards = {(mode, index) for mode in ("STANDARD", "EXPLORATORY") for index in range(10)}
    if seen_shards != expected_shards:
        raise PhaseCControlError("diagnostic shard set is incomplete or unexpected")
    standard_count = sum(record.mode == "STANDARD" for record in records)
    exploratory_count = sum(record.mode == "EXPLORATORY" for record in records)
    if standard_count != 500 or exploratory_count != 200 or len(records) != 700:
        raise PhaseCControlError(
            "diagnostic aggregate requires exactly 500 STANDARD and 200 EXPLORATORY records"
        )
    keys = {(record.mode, record.game_index) for record in records}
    if len(keys) != 700:
        raise PhaseCControlError("diagnostic aggregate contains duplicate game indexes")

    failed = sum(record.status == "FAIL" for record in records)
    standard_failed = sum(
        record.status == "FAIL" and record.mode == "STANDARD" for record in records
    )
    exploratory_failed = sum(
        record.status == "FAIL" and record.mode == "EXPLORATORY" for record in records
    )
    distinct = _distinct_errors(records)
    fresh_replay_pass_count = len(records) - failed
    summary: dict[str, Any] = {
        **provenance,
        "schema_version": DIAGNOSTIC_SUMMARY_SCHEMA,
        "status": "PASS" if failed == 0 else "FAIL",
        "diagnostic_only": True,
        "authorized_execution": False,
        "pilot_result": False,
        "pilot_measurement_artifacts_created": 0,
        "pilot_artifact_count": 0,
        "expected_game_count": 700,
        "game_count": len(records),
        "standard_game_count": standard_count,
        "exploratory_game_count": exploratory_count,
        "standard_attempted": standard_count,
        "standard_passed": standard_count - standard_failed,
        "standard_failed": standard_failed,
        "exploratory_attempted": exploratory_count,
        "exploratory_passed": exploratory_count - exploratory_failed,
        "exploratory_failed": exploratory_failed,
        "pass_count": len(records) - failed,
        "fail_count": failed,
        "distinct_error_count": len(distinct),
        "distinct_errors": distinct,
        "production_equivalent_execution": True,
        "fresh_replay_required": True,
        "fresh_replay_pass_count": fresh_replay_pass_count,
        "fresh_replay_validation_status": (
            "PASS" if fresh_replay_pass_count == len(records) else "INCOMPLETE"
        ),
    }
    _write_json(output_root / "diagnostic-summary.json", summary)
    _assert_no_pilot_artifacts(root)
    return summary


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    shard = subparsers.add_parser("shard")
    shard.add_argument("--mode", choices=("STANDARD", "EXPLORATORY"), required=True)
    shard.add_argument("--shard-index", type=int, required=True)
    shard.add_argument("--output-root", type=Path, required=True)

    aggregate = subparsers.add_parser("aggregate")
    aggregate.add_argument("--shard-root", type=Path, required=True)
    aggregate.add_argument("--output-root", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "shard":
            report = run_diagnostic_shard(
                mode=str(args.mode),
                shard_index=int(args.shard_index),
                output_root=Path(args.output_root),
            )
            compact = {
                key: report[key]
                for key in (
                    "mode",
                    "shard_index",
                    "game_count",
                    "pass_count",
                    "fail_count",
                    "distinct_errors",
                )
            }
            print(json.dumps(compact, indent=2, sort_keys=True))
            return 1 if int(report["fail_count"]) else 0
        summary = aggregate_diagnostic_reports(
            shard_root=Path(args.shard_root),
            output_root=Path(args.output_root),
        )
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 1 if summary["status"] != "PASS" else 0
    except (PhaseCControlError, ValueError, OSError, json.JSONDecodeError) as exc:
        print(
            json.dumps(
                {"status": "BLOCKED", "error_type": type(exc).__name__, "reason": str(exc)},
                indent=2,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
