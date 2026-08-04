from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_pilot_and_full_study_remain_locked() -> None:
    assert not (ROOT / ".github/workflows/pilot-simulation.yml").exists()
    assert not (ROOT / "src/mtg_sim").exists()
