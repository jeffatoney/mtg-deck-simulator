from __future__ import annotations

import csv
import json
from pathlib import Path

import pandas as pd
import pytest

from mtg_sim.domain import Observation, Phase, Step, TerminalStatus
from mtg_sim.exploratory_search import BeliefState, ExploratorySearch, ExploratorySearchError
from mtg_sim.pilot import PilotError, aggregate_seed_records, load_config, run


def test_non_dry_execution_is_implemented_and_smoke_completes() -> None:
    manifest_path = run(Path("configs/pilot-smoke.toml"), smoke=True)
    root = manifest_path.parent
    manifest = json.loads(manifest_path.read_text())
    assert manifest["run_type"] == "pilot_smoke"
    assert manifest["status"] == "completed"
    assert manifest["smoke_counts"] == {
        "discovery_runs": 42,
        "validation_runs": 6,
        "standard_games": 6,
        "exploratory_games": 4,
    }
    for name in [
        "manifest.json",
        "source-hashes.json",
        "config-snapshot.toml",
        "competency-results.json",
        "policy-discovery.csv",
        "policy-validation.csv",
        "canonical-standard-games.parquet",
        "exploratory-games.parquet",
        "paired-differences.csv",
        "audit-selection.csv",
        "events.jsonl.zst",
        "stdout.log",
        "stderr.log",
    ]:
        assert (root / name).exists()


def test_production_configuration_counts_remain_frozen() -> None:
    config = load_config(Path("configs/pilot.toml"))
    assert config.standard_games == 500
    assert config.exploratory_games == 200
    assert config.discovery_count == 300
    assert config.validation_count == 200


def test_discovery_validation_isolated_and_pairing_correct() -> None:
    root = run(Path("configs/pilot-smoke.toml"), smoke=True).parent
    discovery = list(csv.DictReader((root / "policy-discovery.csv").read_text().splitlines()))
    validation = list(csv.DictReader((root / "policy-validation.csv").read_text().splitlines()))
    assert {r["seed_id"] for r in discovery}.isdisjoint({r["seed_id"] for r in validation})
    exploratory = pd.read_parquet(root / "exploratory-games.parquet")
    assert exploratory["paired_standard_game_id"].tolist() == [1, 2, 3, 4]


def test_future_library_order_cannot_reach_search() -> None:
    obs = Observation(
        (),
        (),
        (),
        (),
        (),
        (),
        (),
        1,
        Phase.PRECOMBAT_MAIN,
        Step.MAIN,
        0,
        {},
        TerminalStatus.ONGOING,
        2,
        known_top_library=(),
    )
    belief = BeliefState(("A", "B"), 2, 1, "d")
    ExploratorySearch().choose(observation=obs, belief=belief, candidates=())
    bad = Observation(
        (),
        (),
        (),
        (),
        (),
        (),
        (),
        1,
        Phase.PRECOMBAT_MAIN,
        Step.MAIN,
        0,
        {},
        TerminalStatus.ONGOING,
        2,
        known_top_library=(),
    )
    object.__setattr__(bad, "known_top_library", ("A",))
    with pytest.raises(ExploratorySearchError):
        ExploratorySearch().choose(observation=bad, belief=belief, candidates=())


def test_duplicate_or_missing_seeds_fail_aggregation() -> None:
    with pytest.raises(PilotError, match="duplicate"):
        aggregate_seed_records([{"seed_id": 1}, {"seed_id": 1}], [1, 2])
    with pytest.raises(PilotError, match="missing"):
        aggregate_seed_records([{"seed_id": 1}], [1, 2])


def test_worker_count_changes_do_not_change_results() -> None:
    one = run(Path("configs/pilot-smoke.toml"), smoke=True, worker_count=1).parent
    two = run(Path("configs/pilot-smoke.toml"), smoke=True, worker_count=2).parent
    a = pd.read_parquet(one / "canonical-standard-games.parquet").drop(columns=["game_id"])
    b = pd.read_parquet(two / "canonical-standard-games.parquet").drop(columns=["game_id"])
    pd.testing.assert_frame_equal(a, b)


def test_supplemental_audit_only_excluded_from_percentages() -> None:
    root = run(Path("configs/pilot-smoke.toml"), smoke=True).parent
    audit = list(csv.DictReader((root / "audit-selection.csv").read_text().splitlines()))
    assert any(row["supplemental_audit_only"] == "True" for row in audit)
    standard = pd.read_parquet(root / "canonical-standard-games.parquet")
    assert "supplemental_audit_only" in standard.columns
    assert not standard["supplemental_audit_only"].any()
