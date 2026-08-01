"""Fail-closed tests for the twelve Phase B behavioral transcripts."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from check_phase_b_golden_transcripts import (  # noqa: E402
    approval_document_digest,
    validate_phase_b_transcripts,
)

SOURCE = ROOT / "docs/audit/phase-b-golden-transcripts"


def _nodes(root: Path) -> set[str]:
    approvals = json.loads((root / "APPROVALS.json").read_text(encoding="utf-8"))
    result = set()
    for entry in approvals["approvals"]:
        transcript = json.loads((ROOT / entry["path"]).read_text(encoding="utf-8"))
        result.add(transcript["machine"]["test_node"])
    return result


def test_twelve_digest_bound_transcript_candidates_execute_and_cover_all_families() -> None:
    result = validate_phase_b_transcripts(
        allow_pending=True,
        execute=False,
        collected_nodes=_nodes(SOURCE),
    )
    assert result["status"] == "CANDIDATE_PASS_PENDING_OWNER"
    assert result["count"] == 12
    assert len({item["family_id"] for item in result["transcripts"]}) == 12
    assert len({item["sha256"] for item in result["transcripts"]}) == 12


def test_pending_owner_approval_blocks_strict_phase_b_gate() -> None:
    with pytest.raises(ValueError, match="not owner-anchored|owner approval is pending"):
        validate_phase_b_transcripts(execute=False, collected_nodes=_nodes(SOURCE))


def test_transcript_change_after_digest_binding_is_rejected(tmp_path: Path) -> None:
    sandbox = tmp_path / "repo"
    destination = sandbox / "docs/audit/phase-b-golden-transcripts"
    shutil.copytree(SOURCE, destination)
    approvals_path = destination / "APPROVALS.json"
    approvals = json.loads(approvals_path.read_text(encoding="utf-8"))
    first = approvals["approvals"][0]
    transcript_path = sandbox / first["path"]
    document = json.loads(transcript_path.read_text(encoding="utf-8"))
    document["plain_english"].append("Unapproved semantic drift.")
    transcript_path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    approval_sha = approval_document_digest(approvals)
    with pytest.raises(ValueError, match="digest mismatch"):
        validate_phase_b_transcripts(
            destination / "transcripts",
            approvals_path,
            root=sandbox,
            collected_nodes=_nodes(SOURCE),
            expected_approval_document_sha256=approval_sha,
            allow_pending=True,
            execute=False,
        )
