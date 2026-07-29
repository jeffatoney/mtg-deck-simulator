"""Verify the frozen identity specification, approval record, and lock manifest."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
APPROVAL_PATH = ROOT / "docs/spec/identity/IDENTITY_MODEL_V2.0.0_APPROVAL_RECORD.json"
MANIFEST_PATH = ROOT / "docs/spec/identity/IDENTITY_MODEL_V2.0.0_LOCK_MANIFEST.txt"
EXPECTED_STATUS = "FROZEN_BINDING_FOR_PHASE_A"


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object in {path}")
    return value


def _require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def main() -> int:
    errors: list[str] = []

    for path in (APPROVAL_PATH, MANIFEST_PATH):
        _require(path.is_file(), f"missing required lock file: {path.relative_to(ROOT)}", errors)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    approval = _load_json(APPROVAL_PATH)
    document_value = approval.get("document")
    _require(isinstance(document_value, str), "approval record has no document path", errors)
    if not isinstance(document_value, str):
        document_value = ""

    document_path = ROOT / document_value
    _require(document_path.is_file(), f"missing approved document: {document_value}", errors)
    if not document_path.is_file():
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    document_bytes = document_path.read_bytes()
    _require(not document_bytes.startswith(b"\xef\xbb\xbf"), "approved document contains a BOM", errors)
    _require(b"\r\n" not in document_bytes, "approved document contains CRLF line endings", errors)

    actual_digest = hashlib.sha256(document_bytes).hexdigest()
    expected_digest = approval.get("document_sha256")
    _require(
        isinstance(expected_digest, str) and actual_digest == expected_digest,
        f"document digest mismatch: expected {expected_digest!r}, got {actual_digest}",
        errors,
    )
    _require(
        approval.get("digest_algorithm") == "SHA-256",
        "approval record digest_algorithm is not SHA-256",
        errors,
    )
    _require(
        approval.get("effective_status") == EXPECTED_STATUS,
        f"approval record effective_status is not {EXPECTED_STATUS}",
        errors,
    )
    _require(bool(approval.get("approved_by")), "approval record has no approver", errors)
    _require(bool(approval.get("approved_at")), "approval record has no approval timestamp", errors)

    expected_statement = f"APPROVE IDENTITY_MODEL_V2.0.0 SHA256 {actual_digest}"
    _require(
        approval.get("approval_statement") == expected_statement,
        "approval statement does not bind the actual document digest",
        errors,
    )

    manifest = MANIFEST_PATH.read_text(encoding="utf-8")
    required_manifest_lines = (
        f"Status: {EXPECTED_STATUS}",
        f"Canonical approved document: {document_value}",
        f"Document SHA-256: {actual_digest}",
        f"Approval statement: {expected_statement}",
    )
    for line in required_manifest_lines:
        _require(line in manifest, f"lock manifest is missing: {line}", errors)

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    print(
        json.dumps(
            {
                "status": "PASS",
                "effective_status": EXPECTED_STATUS,
                "document": document_value,
                "document_sha256": actual_digest,
                "approved_by": approval["approved_by"],
                "approved_at": approval["approved_at"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
