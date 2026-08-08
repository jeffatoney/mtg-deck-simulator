from __future__ import annotations

import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
LOCK = ROOT / "automation/interaction-coverage-lock.json"
LEDGER = ROOT / "automation/interaction-integration-coverage.json"

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
    ".github/workflows/policy-choice-replay-conformance.yml": "b9550fadb86925ae0a28c88b1583766bc3d91da6",
    "automation/strategic-choice-conformance.json": "40bc7db4a61cb98ac12c259bd4966067e1fafcbb",
    "docs/audit/interaction-coverage/AGENT_C_POLICY_CHOICE_REPLAY.md": "d89b8d851e53db8baa5a27e0cfb3415ff0ea5422",
    "scripts/audit_policy_choice_replay_conformance.py": "4342dc34aa1a05c5636aac1a64f6dcd388ccd660",
    "tests/interaction_coverage/test_policy_choice_replay_conformance.py": "425123b5a1b61a0c78c9aa90e5a6ad22385547c2",
}

SOURCE_D_BLOBS = {
    ".github/workflows/phase-c-diagnostic.yml": "590e1eb8fc37c5cc4354dc61ca8f0b711a016ba0",
    "scripts/_phase_b_paths.py": "3fbd73295326b5e5fd28f5a9adcf3ee241a5311f",
    "src/mtg_runs/phase_c_diagnostic.py": "4f2885a561c3dea3aede253e621337d5d9c8cd3c",
    "tests/phase_c/test_phase_c_diagnostic.py": "959412095bd5da4a96e8981dba98d5e039b4b006",
}


def _git_blob(path: str) -> str:
    return subprocess.check_output(
        ["git", "hash-object", path], cwd=ROOT, text=True
    ).strip()


def test_frozen_denominator_and_integration_ledger_agree() -> None:
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    surface = ledger["surface"]

    assert lock["record_count"] == 216
    assert lock["card_composition_record_count"] == 80
    assert lock["card_effect_record_count"] == 126
    assert lock["global_rule_record_count"] == 10
    assert lock["manifest_sha256"] == (
        "sha256:20d767ea754841bf0f9bda378068c4c705e0b9f8f8f4be20ca15be1f24bb2cdc"
    )

    for key in (
        "record_count",
        "card_composition_record_count",
        "card_effect_record_count",
        "global_rule_record_count",
        "physical_card_count",
        "card_definition_count",
        "manifest_sha256",
    ):
        assert surface[key] == lock[key]

    assert ledger["coverage"]["requirements"] == lock["record_count"]
    assert ledger["coverage"]["inventory_mapped"] == lock["record_count"]


def test_agent_b_output_paths_survive_integration() -> None:
    missing = [path for path in SOURCE_B_PATHS if not (ROOT / path).is_file()]
    assert missing == []


def test_agent_c_outputs_are_preserved_byte_for_byte() -> None:
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
