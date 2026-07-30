"""Dedicated Phase A clean-engine acceptance command."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def _run(command: str) -> dict[str, Any]:
    completed = subprocess.run(
        command, cwd=ROOT, shell=True, text=True, capture_output=True, check=False
    )
    return {
        "command": command,
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_phase_a_run() -> int:
    """Run the clean Phase A gate and write one immutable result."""
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    branch = subprocess.check_output(
        ["git", "branch", "--show-current"], cwd=ROOT, text=True
    ).strip()
    clean = not subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=ROOT, text=True
    ).strip()
    commands = [
        "uv run --no-sync python scripts/check_clean_engine_boundary.py",
        "uv run --no-sync python scripts/check_identity_lock.py",
        "uv run --no-sync python scripts/check_phase_a_authority.py",
        "uv run --no-sync pytest -q -ra tests/phase_a",
    ]
    results = [_run(command) for command in commands]
    pytest_output = results[-1]["stdout"] + results[-1]["stderr"]

    def count(label: str) -> int:
        match = re.search(rf"(\d+) {label}", pytest_output)
        return int(match.group(1)) if match else 0

    mapping_path = ROOT / "automation/phase-a-test-mapping.json"
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    collected = _run("uv run --no-sync pytest --collect-only -q tests/phase_a")
    node_output = collected["stdout"]
    mapping_ok = all(
        node in node_output for nodes in mapping["requirements"].values() for node in nodes
    )
    pilot_locked = not (ROOT / ".github/workflows/pilot-simulation.yml").exists()
    unsupported = [
        "CONTINUOUS_EFFECT_FOLLOWS_PERMANENT_SPELL",
        "STATIC_GRANTED_ABILITY_FOLLOWS_PERMANENT_SPELL",
        "PREVENTION_EFFECT_FOLLOWS_PERMANENT_SPELL",
        "PERMANENT_REFERENCES_CAST_COST_INFORMATION",
        "ENCHANTED_PERMANENT_LEAVE_TRIGGER_FINDS_AURAS",
        "LAND_PLAY_PERMISSION_FINDS_NEW_PERMANENT",
        "MADNESS_POST_RESOLUTION_TRACKING",
        "STICKER_RETENTION",
    ]
    passed = (
        clean
        and mapping_ok
        and pilot_locked
        and collected["exit_code"] == 0
        and all(r["exit_code"] == 0 for r in results)
    )
    run_id = f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{commit[:12]}"
    artifact = ROOT / "artifacts/engine/phase-a" / run_id / "result.json"
    artifact.parent.mkdir(parents=True, exist_ok=False)
    result = {
        "schema_version": "phase-a-result-v1",
        "run_id": run_id,
        "commit": commit,
        "branch": branch,
        "clean_tree_before_run": clean,
        "commands": results + [collected],
        "counts": {
            "pass": count("passed"),
            "fail": count("failed"),
            "skip": count("skipped"),
            "xfail": count("xfailed"),
        },
        "blocking_requirement_tests": mapping["requirements"],
        "rules_source_sha256": _sha(ROOT / "docs/source/MagicCompRules_2026-06-19.txt"),
        "oracle_source_sha256": _sha(ROOT / "docs/source/oracle/snapshot_v1.json"),
        "architecture_boundary": "PASS" if results[0]["exit_code"] == 0 else "FAIL",
        "authority_map": "PASS" if results[2]["exit_code"] == 0 else "FAIL",
        "evidence_classification": "CLEAN_ENGINE_PRODUCTION_PATH",
        "replay_and_hash": "PASS" if results[-1]["exit_code"] == 0 else "FAIL",
        "pilot_lock": "PASS" if pilot_locked else "FAIL",
        "mapping": "PASS" if mapping_ok else "FAIL",
        "unsupported_capabilities": unsupported,
        "unsupported_behavior": "HARD_VALIDATION_FAILURE",
        "legacy_evidence_used": False,
        "status": "PASS" if passed else "FAIL",
    }
    artifact.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": result["status"],
                "artifact": str(artifact.relative_to(ROOT)),
                "counts": result["counts"],
            },
            indent=2,
        )
    )
    return 0 if passed else 1
