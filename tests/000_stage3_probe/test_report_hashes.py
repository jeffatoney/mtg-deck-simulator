from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PATHS = (
    "docs/audit/phase-c-postpilot/PHASE_C_MALCOLM_GLINT_HORN_WITNESS_AND_TERMINAL_DIAGNOSIS.json",
    "docs/audit/phase-c-postpilot/PHASE_C_MALCOLM_GLINT_HORN_WITNESS_AND_TERMINAL_DIAGNOSIS.md",
)


def test_stage3_report_hashes() -> None:
    result = {}
    for relative in PATHS:
        raw = (ROOT / relative).read_bytes()
        assert raw
        if relative.endswith(".json"):
            json.loads(raw)
        result[relative] = {
            "sha256": hashlib.sha256(raw).hexdigest(),
            "size_bytes": len(raw),
        }
    pytest.exit("STAGE3_REPORT_HASHES=" + json.dumps(result, sort_keys=True), returncode=1)
