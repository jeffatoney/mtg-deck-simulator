from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
COMMANDS = (
    ("format", ["uv", "run", "ruff", "format", "--check", "--diff", "."], 0),
    ("ruff", ["uv", "run", "ruff", "check", "."], 0),
    ("mypy", ["uv", "run", "mypy", "src"], 0),
    ("continuous_combo_access", ["uv", "run", "pytest", "-q", "tests/phase_b/test_continuous_combo_access.py", "-vv"], 0),
    ("measurements", ["uv", "run", "pytest", "-q", "tests/phase_b/test_measurements.py", "-vv"], 0),
    ("glint_action_surface", ["uv", "run", "pytest", "-q", "tests/phase_b/test_glint_horn_action_surface.py", "-vv"], 0),
    ("policy_information_boundary", ["uv", "run", "pytest", "-q", "tests/phase_b/test_policy_information_boundary.py"], 0),
    ("policy_boundary_gate", ["uv", "run", "python", "scripts/check_policy_information_boundary.py"], 0),
    ("policy_broker", ["uv", "run", "pytest", "-q", "tests/phase_b/test_policy_broker.py"], 0),
    ("glint_transcript", ["uv", "run", "pytest", "-q", "tests/phase_b/transcripts/test_pb_t06_glint_curiosity.py"], 0),
    ("witness_contract", ["uv", "run", "pytest", "-q", "tests/phase_c/test_malcolm_glint_horn_witness_contract.py", "-vv"], 0),
    ("terminal_cleanup", ["uv", "run", "pytest", "-q", "tests/phase_c/test_phase_c_terminal_cleanup.py", "-vv"], 1),
    ("phase_c_700_regressions", ["uv", "run", "pytest", "-q", "tests/phase_c/test_phase_c_700_regressions.py", "-vv"], 0),
    ("phase_c_timing", ["uv", "run", "pytest", "-q", "tests/phase_c/test_phase_c_timing.py", "-vv"], 0),
    ("turn10", ["uv", "run", "python", "scripts/check_phase_c_turn10.py"], 0),
    ("repository_evidence", ["uv", "run", "python", "scripts/check_repository_evidence.py"], 0),
    ("repository_evidence_gate", ["uv", "run", "pytest", "-q", "tests/test_repository_evidence_gate.py"], 0),
)


def _tail(text: str, lines: int = 12) -> str:
    return "\n".join(text.splitlines()[-lines:])


def test_stage3_required_validation_commands() -> None:
    results = []
    for name, command, expected in COMMANDS:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        results.append(
            {
                "name": name,
                "command": " ".join(command),
                "expected_returncode": expected,
                "returncode": completed.returncode,
                "tail": _tail(completed.stdout),
            }
        )
        assert completed.returncode == expected, json.dumps(results, indent=2)
    pytest.exit(
        "STAGE3_REQUIRED_VALIDATION=" + json.dumps(results, sort_keys=True),
        returncode=1,
    )
