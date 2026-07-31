"""Positive and negative tests for the Phase A golden-transcript approval gate."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_phase_a_golden_transcripts import (  # noqa: E402
    canonical_bytes,
    validate_golden_transcripts,
)

SOURCE_DIR = ROOT / "docs/audit/phase-a-golden-transcripts"


def _approval_digest(path: Path) -> str:
    document = json.loads(path.read_text(encoding="utf-8"))
    return hashlib.sha256(canonical_bytes(document)).hexdigest()


def _sandbox(tmp_path: Path, *, approve: bool) -> tuple[Path, Path, set[str]]:
    root = tmp_path / "repo"
    destination = root / "docs/audit/phase-a-golden-transcripts"
    shutil.copytree(SOURCE_DIR, destination)
    approvals_path = destination / "APPROVALS.json"
    approvals = json.loads(approvals_path.read_text(encoding="utf-8"))
    nodes: set[str] = set()
    for entry in approvals["approvals"]:
        transcript = json.loads((root / entry["path"]).read_text(encoding="utf-8"))
        nodes.add(transcript["machine"]["test_node"])
        if not approve:
            entry["status"] = "PENDING_OWNER_APPROVAL"
            entry["approved_by"] = None
            entry["approved_at"] = None
            entry["approval_statement"] = None
    if not approve:
        approvals_path.write_text(
            json.dumps(approvals, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return root, approvals_path, nodes


def test_five_digest_bound_owner_approvals_pass(tmp_path: Path) -> None:
    root, approvals, nodes = _sandbox(tmp_path, approve=True)
    result = validate_golden_transcripts(
        root / "docs/audit/phase-a-golden-transcripts/transcripts",
        approvals,
        collected_nodes=nodes,
        root=root,
    )
    assert result["status"] == "PASS"
    assert result["count"] == 5
    assert len({item["sha256"] for item in result["transcripts"]}) == 5


def test_pending_owner_approval_fails_closed(tmp_path: Path) -> None:
    root, approvals, nodes = _sandbox(tmp_path, approve=False)
    with pytest.raises(ValueError, match="owner approval is pending"):
        validate_golden_transcripts(
            root / "docs/audit/phase-a-golden-transcripts/transcripts",
            approvals,
            collected_nodes=nodes,
            root=root,
            expected_approval_document_sha256=_approval_digest(approvals),
        )


def test_unbound_approval_statement_fails_closed(tmp_path: Path) -> None:
    root, approvals_path, nodes = _sandbox(tmp_path, approve=True)
    approvals = json.loads(approvals_path.read_text(encoding="utf-8"))
    approvals["approvals"][0]["approval_statement"] = "Approved."
    approvals_path.write_text(
        json.dumps(approvals, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="approval statement is not bound"):
        validate_golden_transcripts(
            root / "docs/audit/phase-a-golden-transcripts/transcripts",
            approvals_path,
            collected_nodes=nodes,
            root=root,
            expected_approval_document_sha256=_approval_digest(approvals_path),
        )


def test_forged_owner_identity_fails_closed(tmp_path: Path) -> None:
    root, approvals_path, nodes = _sandbox(tmp_path, approve=True)
    approvals = json.loads(approvals_path.read_text(encoding="utf-8"))
    approvals["approvals"][0]["approved_by"] = "Phase A test approver"
    approvals_path.write_text(
        json.dumps(approvals, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="owner approval identity"):
        validate_golden_transcripts(
            root / "docs/audit/phase-a-golden-transcripts/transcripts",
            approvals_path,
            collected_nodes=nodes,
            root=root,
            expected_approval_document_sha256=_approval_digest(approvals_path),
        )


def test_transcript_change_after_approval_is_rejected(tmp_path: Path) -> None:
    root, approvals, nodes = _sandbox(tmp_path, approve=True)
    transcript_path = next(
        (root / "docs/audit/phase-a-golden-transcripts/transcripts").glob("*.json")
    )
    transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
    transcript["plain_english"].append("Unapproved semantic drift.")
    transcript_path.write_text(
        json.dumps(transcript, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="approval digest mismatch"):
        validate_golden_transcripts(
            root / "docs/audit/phase-a-golden-transcripts/transcripts",
            approvals,
            collected_nodes=nodes,
            root=root,
        )
