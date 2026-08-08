from __future__ import annotations

import base64
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

from scripts.audit_policy_choice_replay_conformance import audit_conformance
from scripts.build_interaction_integration_coverage import (
    build_integration_coverage,
    check_ledger,
)

ROOT = Path(__file__).resolve().parents[2]
LOCK = ROOT / "automation/interaction-coverage-lock.json"
LEDGER = ROOT / "automation/interaction-integration-coverage.json"
AGENT_A_INVENTORY_DIR = ROOT / "automation/agent-a-deck-interaction-manifest"
AGENT_A_ADJUDICATION = ROOT / "automation/agent-a-findings-adjudication.json"

SOURCE_COORDINATOR_PATHS = (
    ".github/workflows/interaction-coverage.yml",
    ".github/workflows/interaction-surface.yml",
    "automation/interaction-choice-contracts.json",
    "automation/interaction-coverage-lock.json",
    "automation/interaction-proof-bundle.schema.json",
    "automation/interaction-record.schema.json",
    "docs/audit/interaction-coverage/INTERACTION_COVERAGE_CONTRACT.md",
    "scripts/build_interaction_coverage_manifest.py",
    "scripts/check_interaction_candidate_lock.py",
    "tests/interaction_coverage/test_interaction_coverage_contract.py",
)

SOURCE_AGENT_A_PATHS = (
    "automation/agent-a-deck-interaction-manifest/part-000.b64",
    "automation/agent-a-deck-interaction-manifest/part-001.b64",
    "automation/agent-a-deck-interaction-manifest/part-002.b64",
    "automation/agent-a-findings-adjudication.json",
)

SOURCE_B_PATHS = (
    "docs/audit/interaction-coverage/AGENT_B_ENGINE_RULES_CONFORMANCE.md",
    "src/mtg_kernel/__init__.py",
    "src/mtg_kernel/interaction_rules_conformance.py",
    "src/mtg_kernel/prismari_rules_conformance.py",
    "src/mtg_policy/broker.py",
    "tests/interaction_coverage/test_engine_rules_conformance.py",
    "tests/phase_b/test_runtime_batch_four.py",
    "tests/phase_b/test_runtime_batch_twelve.py",
    "tests/phase_b/test_runtime_batch_twenty_eight.py",
)

SOURCE_C_BLOBS = {
    ".github/workflows/policy-choice-replay-conformance.yml": (
        "b9550fadb86925ae0a28c88b1583766bc3d91da6"
    ),
    "automation/strategic-choice-conformance.json": "50c6f873c271c29825100df3ccc9fa44c0d41de8",
    "docs/audit/interaction-coverage/AGENT_C_POLICY_CHOICE_REPLAY.md": (
        "d89b8d851e53db8baa5a27e0cfb3415ff0ea5422"
    ),
    "scripts/audit_policy_choice_replay_conformance.py": "4342dc34aa1a05c5636aac1a64f6dcd388ccd660",
    "tests/interaction_coverage/test_policy_choice_replay_conformance.py": (
        "31f9f0503ae7a03d3204eef015299b35bc6ff20a"
    ),
}

SOURCE_D_BLOBS = {
    ".github/workflows/phase-c-diagnostic.yml": "590e1eb8fc37c5cc4354dc61ca8f0b711a016ba0",
    "scripts/_phase_b_paths.py": "3fbd73295326b5e5fd28f5a9adcf3ee241a5311f",
    "src/mtg_runs/phase_c_diagnostic.py": "4f2885a561c3dea3aede253e621337d5d9c8cd3c",
    "tests/phase_c/test_phase_c_diagnostic.py": "959412095bd5da4a96e8981dba98d5e039b4b006",
}


def _git_blob(path: str) -> str:
    return subprocess.check_output(["git", "hash-object", path], cwd=ROOT, text=True).strip()


def _canonical_digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def test_candidate_denominator_and_integration_ledger_agree() -> None:
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    surface = ledger["surface"]

    assert lock["status"] == "PROVISIONAL_PENDING_AGENT_A_INTEGRATION"
    assert lock["record_count"] == 216
    assert lock["card_composition_record_count"] == 80
    assert lock["card_effect_record_count"] == 126
    assert lock["global_rule_record_count"] == 10
    assert lock["manifest_sha256"] == "sha256:" + ("0" * 64)
    assert lock["candidate_manifest_sha256"] == (
        "sha256:f976526e34d7297521b9c949c7e3a54905cb8bdaa62e7e3225627de294f8a6b5"
    )

    for key in (
        "record_count",
        "card_composition_record_count",
        "card_effect_record_count",
        "global_rule_record_count",
        "physical_card_count",
        "card_definition_count",
    ):
        assert surface[key] == lock[key]

    assert surface["manifest_sha256"] == lock["candidate_manifest_sha256"]
    assert surface["candidate_status"] == lock["status"]
    assert ledger["coverage"]["requirements"] == lock["record_count"]
    assert ledger["coverage"]["inventory_mapped"] == lock["record_count"]


def test_provisional_candidate_lock_cannot_be_reported_as_frozen() -> None:
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    report = audit_conformance()

    assert lock["status"] == "PROVISIONAL_PENDING_AGENT_A_INTEGRATION"
    assert report["surface_frozen"] is False
    assert report["proof_status"] == "PROVISIONAL_UNTIL_COORDINATOR_FREEZE"


def test_committed_ledger_matches_the_complete_recomputed_report() -> None:
    report = build_integration_coverage()

    assert report["status"] == "BLOCKED_PROVISIONAL_SURFACE"
    assert report["surface"]["record_count"] == 216
    assert report["agent_a"]["finding_count"] == 16
    assert report["agent_a"]["pending_count"] == 16
    assert check_ledger(report, emit=False)


def test_ledger_checker_rejects_headline_and_previously_unchecked_falsifications(
    tmp_path: Path,
) -> None:
    report = build_integration_coverage()
    baseline = json.loads(LEDGER.read_text(encoding="utf-8"))
    mutation_paths: tuple[tuple[str, ...], ...] = (
        ("status",),
        ("coverage", "engine_blocker_families"),
        ("coverage", "live_policy_defects"),
        ("coverage", "records_requiring_no_strategic_policy"),
        ("coverage", "strategic_choice_classes_with_reviewed_routes"),
        ("coverage", "strategic_protocol_methods_required"),
        ("coverage", "strategic_protocol_methods_in_production_provider"),
        ("coverage", "strategic_protocol_methods_in_recorded_replay_provider"),
        ("remaining_engine_blockers",),
    )

    for index, path in enumerate(mutation_paths):
        falsified = json.loads(json.dumps(baseline))
        target = falsified
        for key in path[:-1]:
            target = target[key]
        current = target[path[-1]]
        if isinstance(current, bool):
            replacement: Any = not current
        elif isinstance(current, int):
            replacement = current + 1
        elif isinstance(current, str):
            replacement = current + "__FALSIFIED__"
        elif isinstance(current, list):
            replacement = [*current, "__FALSIFIED__"]
        else:
            raise AssertionError(f"unsupported mutation value at {path}: {type(current)!r}")
        assert replacement != current
        target[path[-1]] = replacement
        candidate = tmp_path / f"falsified-{index}.json"
        candidate.write_text(json.dumps(falsified), encoding="utf-8")
        assert not check_ledger(report, ledger_path=candidate, emit=False), path


def test_agent_a_artifact_is_complete_bound_and_adjudicated() -> None:
    encoded = "".join(
        path.read_text(encoding="ascii").strip()
        for path in sorted(AGENT_A_INVENTORY_DIR.glob("part-*.b64"))
    )
    inventory = json.loads(gzip.decompress(base64.b64decode(encoded)).decode("utf-8"))
    adjudication = json.loads(AGENT_A_ADJUDICATION.read_text(encoding="utf-8"))
    expected_digest = inventory.pop("agent_a_manifest_sha256")

    assert _canonical_digest(inventory) == expected_digest
    assert adjudication["agent_a_artifact_sha256"] == expected_digest
    assert len(inventory["blocking_findings"]) == 16
    assert {item["id"] for item in adjudication["findings"]} == {
        item["id"] for item in inventory["blocking_findings"]
    }


def test_coordinator_output_paths_survive_integration() -> None:
    missing = [path for path in SOURCE_COORDINATOR_PATHS if not (ROOT / path).is_file()]
    assert missing == []


def test_agent_a_output_paths_survive_integration() -> None:
    missing = [path for path in SOURCE_AGENT_A_PATHS if not (ROOT / path).is_file()]
    assert missing == []


def test_agent_b_output_paths_survive_integration() -> None:
    missing = [path for path in SOURCE_B_PATHS if not (ROOT / path).is_file()]
    assert missing == []


def test_agent_c_outputs_match_reviewed_integrated_pins() -> None:
    mismatches = {
        path: (_git_blob(path), expected)
        for path, expected in SOURCE_C_BLOBS.items()
        if _git_blob(path) != expected
    }
    assert mismatches == {}


def test_agent_d_executable_outputs_are_preserved_byte_for_byte() -> None:
    mismatches = {
        path: (_git_blob(path), expected)
        for path, expected in SOURCE_D_BLOBS.items()
        if _git_blob(path) != expected
    }
    assert mismatches == {}
