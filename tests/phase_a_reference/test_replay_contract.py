from __future__ import annotations

import json

import pytest

from .reference_adapter import ROOT, load_scenario, run_scenario, validate_replay_artifact

FIXTURES = sorted((ROOT / "tests/fixtures/golden-replays").glob("*.json"))


@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda path: path.stem)
def test_golden_replay(fixture) -> None:
    golden = json.loads(fixture.read_text())
    assert golden["review_status"] in {
        "draft-unreviewed",
        "rules-reviewed",
        "independently-reviewed",
    }
    first = run_scenario(load_scenario(golden["scenario_id"]))
    from mtg_kernel.replay import ReplayEngine

    replay = ReplayEngine.run(
        initial_state=first["initial_state"],
        actions=first["actions"],
        rng_streams=first["rng_streams"],
    )
    replay["actions"] = first["actions"]
    replay["rng_streams"] = first["rng_streams"]
    validate_replay_artifact(first, replay)
    for mutation in ("omit", "duplicate", "reorder", "alter"):
        with pytest.raises(Exception):
            ReplayEngine.run(
                initial_state=first["initial_state"],
                actions=first["actions"],
                rng_streams=first["rng_streams"],
                validation_probe=mutation,
            )
