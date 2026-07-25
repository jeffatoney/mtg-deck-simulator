"""Phase A recovery gate and immutable-style evidence writer."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

from mtg_sim.structured_cards import OPERATIONS, VERTICAL_SLICE

ROOT = Path(__file__).resolve().parents[2]
RESULT = ROOT / "artifacts/recovery/kernel/result.json"
PROHIBITED = (
    "battlefield.append",
    "hand.append",
    "library.insert",
    "graveyard.append",
    "exile.append",
    "stack.append",
    "phase =",
    "won =",
    "lost =",
    "setattr(",
)


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def architecture_guard() -> list[str]:
    findings: list[str] = []
    for path in (ROOT / "src/mtg_sim/structured_cards.py",):
        text = path.read_text()
        ast.parse(text)
        for pattern in PROHIBITED:
            if pattern in text:
                findings.append(f"{path.relative_to(ROOT)}: prohibited {pattern}")
    return findings


def run_kernel_recovery() -> dict[str, Any]:
    findings = architecture_guard()
    # Phase A cannot be certified while these vertical-slice behaviors are not
    # yet expressed by the canonical executor. Keep production locked and make
    # the command fail rather than converting scaffolding coverage into a claim.
    findings.extend(
        [
            "P1: canonical mana-cost determination and payment are incomplete",
            "P1: Abrade modes and target resolution are incomplete",
            "P1: Glint-Horn activation and Dualcaster/Twinflame copy loop are incomplete",
            "P1: GameExecutor legacy smoke run still owns a separate turn loop",
        ]
    )
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, check=True, capture_output=True
    ).stdout.strip()
    dirty = bool(
        subprocess.run(
            ["git", "status", "--porcelain"], cwd=ROOT, text=True, check=True, capture_output=True
        ).stdout
    )
    sources = [
        ROOT / "docs/source/MagicCompRules_2026-06-19.txt",
        ROOT / "docs/source/oracle/snapshot_v1.json",
        ROOT / "docs/source/decklist.txt",
        ROOT / "docs/source/commanders.txt",
    ]
    inventory = json.loads((ROOT / "configs/kernel-migration.json").read_text())
    migrated = [row for row in inventory["cards"] if row["status"] == "MIGRATED"]
    pending = [row for row in inventory["cards"] if row["status"] == "PENDING_PHASE_B"]
    passed = not findings and len(VERTICAL_SLICE) == 10 and len(migrated) == 10 and bool(pending)
    report: dict[str, Any] = {
        "phase": "A",
        "git_commit": commit,
        "clean_tree": not dirty,
        "source_hashes": {str(p.relative_to(ROOT)): _hash(p) for p in sources},
        "tests": {
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "xfailed": 0,
            "note": "pytest counts are supplied by CI; kernel self-checks follow",
        },
        "architecture_invariants": {"passed": not findings, "findings": findings},
        "object_zone_gate": "PASS" if passed else "FAIL",
        "casting_stack_priority": "PASS" if passed else "FAIL",
        "trigger": "PASS" if passed else "FAIL",
        "turn_cleanup": "PASS" if passed else "FAIL",
        "external_object": "PASS" if passed else "FAIL",
        "replay": "PASS" if passed else "FAIL",
        "effect_operations": sorted(OPERATIONS),
        "vertical_slice_card_count": len(migrated),
        "pending_phase_b_count": len(pending),
        "p1_findings": findings,
        "p2_findings": [],
        "production_lock_status": "LOCKED",
        "pr_29": "Regression source only; import-time monkeypatch architecture not imported",
        "status": "PASS" if passed else "FAIL",
    }
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    RESULT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report
