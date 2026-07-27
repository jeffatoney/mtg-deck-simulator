from __future__ import annotations
import json
from pathlib import Path
import pytest
from .reference_adapter import run_scenario

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = sorted((ROOT / "tests/fixtures/golden-replays").glob("*.json"))


@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda path: path.stem)
def test_golden_replay(fixture: Path) -> None:
    expected = json.loads(fixture.read_text())
    actual = run_scenario(
        {"scenario_id": expected["scenario_id"], "scenario_version": 1, "replay": True}
    )["replay"]
    assert actual == expected
