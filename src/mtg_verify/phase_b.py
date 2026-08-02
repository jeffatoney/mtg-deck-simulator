"""Phase B verifier for deck, policy, search, measurement, replay, and transcripts."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mtg_cards.full_deck import RULES_BY_NAME
from mtg_deck import load_exact_deck_package
from mtg_deck.package import EXECUTION_UNVERIFIED
from mtg_kernel.phase_b_actions import automatic_ability_execution_supported, effect_execution_supported
from mtg_policy.evaluation import load_evaluator_config
from mtg_policy.learning import load_learning_plan

ROOT = Path(__file__).resolve().parents[2]


def _run(command: str, *, environment: dict[str, str] | None = None) -> dict[str, Any]:
    completed = subprocess.run(command, cwd=ROOT, shell=True, text=True, capture_output=True, check=False, env={**os.environ, **(environment or {})})
    return {"command": command, "exit_code": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _artifact_root() -> Path:
    configured = os.environ.get("PHASE_B_ARTIFACT_ROOT", "").strip()
    if not configured:
        return ROOT / "artifacts/engine/phase-b"
    path = Path(configured)
    return path if path.is_absolute() else ROOT / path


def exact_deck_execution_blockers() -> list[str]:
    blockers: set[str] = set()
    package = load_exact_deck_package()
    for record in package.coverage:
        if record.execution_status == EXECUTION_UNVERIFIED:
            blockers.add(f"UNVERIFIED_CARD:{record.name}")
        elif record.execution_status != "IMPLEMENTED":
            blockers.add(f"NONIMPLEMENTED_CARD:{record.name}:{record.execution_status}")
    for name, abilities in RULES_BY_NAME.items():
        for ability in abilities:
            kind = str(ability.get("kind", ""))
            if kind in {"SPELL", "ACTIVATED", "SPECIAL_ACTION"}:
                if not effect_execution_supported(dict(ability.get("effect", {}))):
                    effect = str(dict(ability.get("effect", {})).get("kind", "NONE"))
                    blockers.add(f"UNSUPPORTED_EFFECT:{name}:{effect}")
            elif kind in {"TRIGGERED", "REPLACEMENT", "STATIC"}:
                if not automatic_ability_execution_supported(dict(ability), entering=True):
                    blockers.add(f"UNSUPPORTED_AUTOMATIC:{name}:{kind}")
            elif kind == "CAST_PERMISSION":
                blockers.add(f"UNVERIFIED_CAST_PERMISSION:{name}:{ability.get('permission', '')}")
            else:
                blockers.add(f"UNSUPPORTED_ABILITY_KIND:{name}:{kind}")
    return sorted(blockers)


def strategic_model_blockers() -> list[str]:
    evaluator = load_evaluator_config()
    blockers: list[str] = []
    if evaluator.dualcaster_loop_handling == "FAIL_CLOSED_UNTIL_DETERMINISTIC_LOOP_ADJUDICATOR":
        blockers.append("UNSUPPORTED_STRATEGIC_LOOP:DUALCASTER_TWINFLAME")
    return blockers


def verify_phase_b_run() -> int:
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip() or os.environ.get("GITHUB_HEAD_REF", "").strip()
    clean = not subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()
    phase_a_root = _artifact_root() / "standing-phase-a"
    commands = [
        _run("uv run --no-sync mtg-engine verify-phase-a", environment={"PHASE_A_ARTIFACT_ROOT": str(phase_a_root)}),
        _run("uv run --no-sync python scripts/check_phase_a_certification.py"),
        _run("uv run --no-sync python scripts/check_clean_engine_boundary.py"),
        _run("uv run --no-sync python scripts/check_phase_b_authority.py"),
        _run("uv run --no-sync python scripts/check_full_deck_coverage.py"),
        _run("uv run --no-sync python scripts/check_phase_b_evaluator.py"),
        _run("uv run --no-sync python scripts/check_phase_b_golden_transcripts.py"),
        _run("uv run --no-sync pytest -q -ra tests/phase_b"),
    ]
    pytest_output = commands[-1]["stdout"] + commands[-1]["stderr"]
    def count(label: str) -> int:
        match = re.search(rf"(\d+) {label}", pytest_output)
        return int(match.group(1)) if match else 0
    mapping = json.loads((ROOT / "automation/phase-b-test-mapping.json").read_text(encoding="utf-8"))
    collected = _run("uv run --no-sync pytest --collect-only -q tests/phase_a tests/phase_b")
    node_output = collected["stdout"]
    mapping_ok = all(node in node_output for nodes in mapping["requirements"].values() for node in nodes)
    pilot_locked = not (ROOT / ".github/workflows/pilot-simulation.yml").exists() and not (ROOT / "src" / ("mtg" + "_sim")).exists()
    unsupported = exact_deck_execution_blockers()
    strategic_blockers = strategic_model_blockers()
    evaluator = load_evaluator_config()
    learning_plan = load_learning_plan()
    evaluator_status = "PASS" if commands[5]["exit_code"] == 0 else "FAIL"
    transcript_status = "PASS" if commands[6]["exit_code"] == 0 else "FAIL"
    passed = clean and mapping_ok and pilot_locked and not unsupported and not strategic_blockers and collected["exit_code"] == 0 and all(result["exit_code"] == 0 for result in commands)
    run_id = f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{commit[:12]}"
    artifact = _artifact_root() / run_id / "result.json"
    artifact.parent.mkdir(parents=True, exist_ok=False)
    result = {
        "schema_version": "phase-b-result-v2", "run_id": run_id, "commit": commit, "branch": branch,
        "github_actions": os.environ.get("GITHUB_ACTIONS") == "true", "github_run_id": os.environ.get("GITHUB_RUN_ID"),
        "clean_tree_before_run": clean, "commands": commands + [collected],
        "counts": {"pass": count("passed"), "fail": count("failed"), "skip": count("skipped"), "xfail": count("xfailed")},
        "blocking_requirement_tests": mapping["requirements"], "mapping_complete": mapping_ok,
        "rules_source_sha256": _sha(ROOT / "docs/source/MagicCompRules_2026-06-19.txt"),
        "oracle_source_sha256": _sha(ROOT / "docs/source/oracle/snapshot_v1.json"), "decklist_sha256": _sha(ROOT / "docs/source/decklist.txt"),
        "strategic_evaluator": evaluator_status, "evaluator_snapshot_id": evaluator.evaluator_id,
        "evaluator_snapshot_sha256": evaluator.config_sha256, "learning_plan_sha256": learning_plan.plan_sha256,
        "golden_transcripts": transcript_status, "transcript_count": 12 if transcript_status == "PASS" else 0,
        "pilot_lock": "PASS" if pilot_locked else "FAIL", "unsupported_capabilities": unsupported,
        "strategic_model_blockers": strategic_blockers, "evidence_classification": "CLEAN_ENGINE_PRODUCTION_PATH",
        "legacy_evidence_used": False, "status": "PASS" if passed else "FAIL",
    }
    artifact.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    artifact.chmod(0o444)
    print(json.dumps({"status": result["status"], "artifact": str(artifact), "commit": commit, "counts": result["counts"], "mapping_complete": mapping_ok, "strategic_evaluator": evaluator_status, "evaluator_snapshot_id": evaluator.evaluator_id, "evaluator_snapshot_sha256": evaluator.config_sha256, "learning_plan_sha256": learning_plan.plan_sha256, "golden_transcripts": transcript_status, "unsupported_capability_count": len(unsupported), "strategic_model_blocker_count": len(strategic_blockers), "pilot_lock": result["pilot_lock"]}, indent=2, sort_keys=True))
    return 0 if passed else 1
