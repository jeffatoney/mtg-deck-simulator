from __future__ import annotations

import hashlib
import json
from pathlib import Path

from mtg_runs.phase_c import _derive_seeds, build_pilot_seed_plan, load_phase_c_config

ROOT = Path(__file__).resolve().parents[2]
HOLDOUT_PATH = ROOT / "docs/spec/phase-c/PREPILOT_TECHNICAL_HOLDOUT.json"


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def test_precommitted_technical_holdout_is_domain_separated_from_pilot() -> None:
    holdout = json.loads(HOLDOUT_PATH.read_text(encoding="utf-8"))
    seed_plan = holdout["seed_plan"]
    seeds = _derive_seeds(str(seed_plan["namespace"]), int(seed_plan["count"]))
    pilot = build_pilot_seed_plan(load_phase_c_config())

    assert len(seeds) == 64
    assert len(set(seeds)) == 64
    assert hashlib.sha256(_canonical(seeds)).hexdigest() == seed_plan["canonical_tuple_sha256"]
    assert not set(seeds).intersection(pilot.standard)
    assert not set(seeds).intersection(pilot.exploratory_search)
    assert holdout["authorized_pilot_measurement"] is False
    assert holdout["authorized_full_study_measurement"] is False
    assert holdout["execution_contract"]["pilot_artifact_creation_forbidden"] is True
