from __future__ import annotations

import json
from pathlib import Path

import pytest

from mtg_runs import phase_c_diagnostic as diagnostic
from mtg_runs.phase_c import PhaseCControlError


PROVENANCE = {
    "implementation_sha": "1" * 40,
    "implementation_tree": "2" * 40,
    "config_sha256": "3" * 64,
    "no_opponent_policy_guardrail_sha256": "4" * 64,
    "phase_a_certification_sha256": "5" * 64,
    "phase_b_certification_sha256": "6" * 64,
    "diagnostic_workflow_sha256": "7" * 64,
    "diagnostic_run_id": "123456789",
    "workflow_head_sha": "1" * 40,
}


def _record(mode: str, index: int) -> dict[str, object]:
    return diagnostic.DiagnosticGameRecord(
        mode=mode,
        game_index=index,
        seed=10_000 + index,
        pair_id=None,
        paired_standard_game_index=None,
        search_seed=None,
        status="PASS",
        controlled_turns_completed=10,
        terminal_status="TURN_LIMIT",
        command_count=100,
        replay_digest=f"replay-{mode}-{index}",
        final_state_hash=f"state-{mode}-{index}",
        fresh_replay_state_hash=f"state-{mode}-{index}",
    ).to_dict()


def _write_shards(root: Path) -> None:
    for mode, count, shard_size in (
        ("STANDARD", 500, 50),
        ("EXPLORATORY", 200, 20),
    ):
        for shard_index in range(10):
            first = shard_index * shard_size + 1
            records = [_record(mode, index) for index in range(first, first + shard_size)]
            payload = {
                **PROVENANCE,
                "schema_version": diagnostic.DIAGNOSTIC_SCHEMA,
                "diagnostic_only": True,
                "authorized_execution": False,
                "pilot_measurement_artifacts_created": 0,
                "mode": mode,
                "shard_index": shard_index,
                "records": records,
            }
            path = root / mode.lower() / f"shard-{shard_index:02d}" / "diagnostic-shard.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
        assert count == shard_size * 10


def test_diagnostic_summary_exposes_exact_provenance_counts_and_replay_status(
    tmp_path: Path,
) -> None:
    shard_root = tmp_path / "shards"
    _write_shards(shard_root)
    summary = diagnostic.aggregate_diagnostic_reports(
        shard_root=shard_root,
        output_root=tmp_path / "summary",
        root=tmp_path,
    )

    for key, value in PROVENANCE.items():
        assert summary[key] == value
    assert summary["status"] == "PASS"
    assert summary["standard_attempted"] == 500
    assert summary["standard_passed"] == 500
    assert summary["standard_failed"] == 0
    assert summary["exploratory_attempted"] == 200
    assert summary["exploratory_passed"] == 200
    assert summary["exploratory_failed"] == 0
    assert summary["pass_count"] == 700
    assert summary["fail_count"] == 0
    assert summary["distinct_error_count"] == 0
    assert summary["fresh_replay_pass_count"] == 700
    assert summary["fresh_replay_validation_status"] == "PASS"
    assert summary["pilot_artifact_count"] == 0


def test_diagnostic_aggregate_rejects_mixed_implementation_provenance(
    tmp_path: Path,
) -> None:
    shard_root = tmp_path / "shards"
    _write_shards(shard_root)
    target = shard_root / "standard" / "shard-00" / "diagnostic-shard.json"
    payload = json.loads(target.read_text(encoding="utf-8"))
    payload["implementation_sha"] = "f" * 40
    target.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    with pytest.raises(PhaseCControlError, match="mixed provenance"):
        diagnostic.aggregate_diagnostic_reports(
            shard_root=shard_root,
            output_root=tmp_path / "summary",
            root=tmp_path,
        )
