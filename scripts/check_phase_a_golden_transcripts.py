"""Validate the five exact, digest-bound, owner-approved Phase A transcripts."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TRANSCRIPT_DIR = ROOT / "docs/audit/phase-a-golden-transcripts/transcripts"
DEFAULT_APPROVALS = ROOT / "docs/audit/phase-a-golden-transcripts/APPROVALS.json"
TRANSCRIPT_SCHEMA = "phase-a-golden-transcript-v1"
APPROVAL_SCHEMA = "phase-a-golden-transcript-approvals-v1"
REQUIRED_COUNT = 5
EXPECTED_OWNER_NAME = "Jeff Toney"
EXPECTED_APPROVAL_DOCUMENT_SHA256 = (
    "d78be11d330df0bccbee4439556da6ae000683d4ccacce83d90ad8ed5de8174b"
)


def canonical_bytes(value: Any) -> bytes:
    """Return the project's integer-only canonical JSON representation."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def transcript_digest(value: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _iso_timestamp(value: str) -> bool:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _collected_phase_a_nodes(root: Path) -> set[str]:
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "tests/phase_a"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise ValueError(
            "Phase A test collection failed while validating golden transcripts: "
            f"{completed.stdout}{completed.stderr}"
        )
    return {
        line.strip()
        for line in completed.stdout.splitlines()
        if line.strip().startswith("tests/phase_a/") and "::" in line
    }


def validate_golden_transcripts(
    transcript_dir: Path = DEFAULT_TRANSCRIPT_DIR,
    approvals_path: Path = DEFAULT_APPROVALS,
    *,
    collected_nodes: set[str] | None = None,
    root: Path = ROOT,
    expected_approval_document_sha256: str = EXPECTED_APPROVAL_DOCUMENT_SHA256,
    expected_owner_name: str = EXPECTED_OWNER_NAME,
) -> dict[str, Any]:
    if not approvals_path.is_file():
        raise ValueError(f"approval record is missing: {approvals_path}")
    approval_document = json.loads(approvals_path.read_text(encoding="utf-8"))
    approval_document_sha256 = hashlib.sha256(canonical_bytes(approval_document)).hexdigest()
    if approval_document_sha256 != expected_approval_document_sha256:
        raise ValueError("golden transcript approval record is not owner-anchored")
    if approval_document.get("schema_version") != APPROVAL_SCHEMA:
        raise ValueError("golden transcript approval schema is unsupported")
    if approval_document.get("required_count") != REQUIRED_COUNT:
        raise ValueError("golden transcript approval record must require exactly five transcripts")

    paths = sorted(transcript_dir.glob("*.json"))
    if len(paths) != REQUIRED_COUNT:
        raise ValueError(f"expected exactly five transcript files, found {len(paths)}")
    approvals = approval_document.get("approvals")
    if not isinstance(approvals, list) or len(approvals) != REQUIRED_COUNT:
        raise ValueError("approval record must contain exactly five approval entries")
    approval_by_id = {
        str(entry.get("transcript_id")): entry for entry in approvals if isinstance(entry, dict)
    }
    if len(approval_by_id) != REQUIRED_COUNT:
        raise ValueError("approval transcript IDs must be unique")

    nodes = collected_nodes if collected_nodes is not None else _collected_phase_a_nodes(root)
    validated: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for path in paths:
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("schema_version") != TRANSCRIPT_SCHEMA:
            raise ValueError(f"unsupported transcript schema: {path}")
        transcript_id = str(document.get("transcript_id", ""))
        if not transcript_id or transcript_id in seen_ids:
            raise ValueError("transcript IDs must be nonempty and unique")
        seen_ids.add(transcript_id)
        plain = document.get("plain_english")
        machine = document.get("machine")
        if (
            not isinstance(plain, list)
            or not plain
            or not all(isinstance(item, str) and item.strip() for item in plain)
        ):
            raise ValueError(f"plain-English representation is incomplete: {transcript_id}")
        if not isinstance(machine, dict):
            raise ValueError(f"machine representation is missing: {transcript_id}")
        test_node = str(machine.get("test_node", ""))
        if test_node not in nodes:
            raise ValueError(f"machine test node is not collected: {test_node}")

        digest = transcript_digest(document)
        approval = approval_by_id.get(transcript_id)
        if approval is None:
            raise ValueError(f"approval entry is missing: {transcript_id}")
        expected_path = str(path.relative_to(root))
        if approval.get("path") != expected_path:
            raise ValueError(f"approval path mismatch: {transcript_id}")
        if approval.get("sha256") != digest:
            raise ValueError(f"approval digest mismatch: {transcript_id}")
        if approval.get("status") != "APPROVED":
            raise ValueError(f"owner approval is pending: {transcript_id}")
        approved_by = str(approval.get("approved_by", "")).strip()
        approved_at = str(approval.get("approved_at", "")).strip()
        statement = str(approval.get("approval_statement", "")).strip()
        if approved_by != expected_owner_name or not _iso_timestamp(approved_at):
            raise ValueError(f"owner approval identity or timestamp is invalid: {transcript_id}")
        if transcript_id not in statement or digest not in statement:
            raise ValueError(f"approval statement is not bound to ID and digest: {transcript_id}")
        validated.append(
            {
                "transcript_id": transcript_id,
                "path": expected_path,
                "sha256": digest,
                "test_node": test_node,
            }
        )

    if set(approval_by_id) != seen_ids:
        raise ValueError("approval entries and transcript files do not identify the same set")
    return {
        "schema_version": "phase-a-golden-transcript-validation-v1",
        "status": "PASS",
        "count": len(validated),
        "owner_approval_anchor": {
            "approved_by": expected_owner_name,
            "approval_document_sha256": approval_document_sha256,
        },
        "transcripts": validated,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transcript-dir", type=Path, default=DEFAULT_TRANSCRIPT_DIR)
    parser.add_argument("--approvals", type=Path, default=DEFAULT_APPROVALS)
    args = parser.parse_args()
    try:
        result = validate_golden_transcripts(args.transcript_dir, args.approvals)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "FAIL", "reason": str(exc)}, indent=2))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
