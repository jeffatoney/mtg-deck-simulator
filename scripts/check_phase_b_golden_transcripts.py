#!/usr/bin/env python3
"""Validate and execute the digest-bound Phase B behavioral transcripts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from mtg_verify.transcript_evidence import (
    ALLOWED_EVENT_SOURCES,
    EVIDENCE_DIR_ENV,
    EVIDENCE_SCHEMA,
    subsequence_indexes,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = ROOT / "docs/audit/phase-b-golden-transcripts"
DEFAULT_TRANSCRIPTS = DEFAULT_ROOT / "transcripts"
DEFAULT_APPROVALS = DEFAULT_ROOT / "APPROVALS.json"
TRANSCRIPT_SCHEMA = "phase-b-golden-transcript-v1"
APPROVAL_SCHEMA = "phase-b-golden-transcript-approvals-v1"
REQUIRED_COUNT = 12
EXPECTED_OWNER = "Jeff Toney"
# Replaced only after the owner approves the exact IDs and digests.
OWNER_APPROVAL_DOCUMENT_SHA256 = "PENDING_OWNER_APPROVAL"
EVIDENCE_SCOPES = {
    "EXACT_DECK_INTEGRATION",
    "MECHANIC_ISOLATION",
    "POLICY_INTEGRATION",
    "REPLAY_AUDIT",
}
REQUIRED_FAMILIES = {
    "exact-deck-two-commanders",
    "league-mulligan-draw-back-seven",
    "malcolm-damaged-opponents-treasures",
    "breeches-unknown-exclusion",
    "dualcaster-twinflame-not-cast",
    "glint-horn-curiosity-terminal-order",
    "tutor-exactly-one-target",
    "modal-x-alternative-cost",
    "fact-or-fiction-minimizing",
    "hidden-future-denial-policy-search",
    "shared-broker-first-divergence",
    "replay-measurement-manifest-terminal-invariance",
}


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def transcript_digest(document: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(document)).hexdigest()


def approval_document_digest(document: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(document)).hexdigest()


def _iso_timestamp(value: str) -> bool:
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})", value))


def _collected_nodes(root: Path) -> set[str]:
    completed = subprocess.run(
        ["pytest", "--collect-only", "-q", "tests/phase_a", "tests/phase_b"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "PYTHONPATH": str(root / "src")},
    )
    if completed.returncode != 0:
        raise ValueError(
            f"could not collect transcript tests: {completed.stdout}{completed.stderr}"
        )
    return {
        line.strip()
        for line in completed.stdout.splitlines()
        if "::test_" in line and not line.lstrip().startswith("<")
    }


def _validate_execution_evidence(
    evidence_dir: Path,
    validated: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    paths = sorted(evidence_dir.glob("*.json"))
    if len(paths) != REQUIRED_COUNT:
        raise ValueError(
            f"expected 12 transcript evidence files, observed {len(paths)}: "
            f"{[path.name for path in paths]}"
        )
    evidence_records: list[dict[str, Any]] = []
    for transcript in validated:
        transcript_id = str(transcript["transcript_id"])
        path = evidence_dir / f"{transcript_id}.json"
        if not path.is_file():
            raise ValueError(f"named transcript test omitted evidence: {transcript_id}")
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("schema_version") != EVIDENCE_SCHEMA:
            raise ValueError(f"transcript evidence schema is unsupported: {transcript_id}")
        if document.get("transcript_id") != transcript_id:
            raise ValueError(f"transcript evidence ID differs: {transcript_id}")
        if document.get("event_source") != transcript["event_source"]:
            raise ValueError(f"transcript evidence source differs: {transcript_id}")
        required = document.get("required_event_order")
        observed = document.get("observed_event_order")
        matched = document.get("matched_indexes")
        if required != transcript["required_event_order"]:
            raise ValueError(f"transcript evidence requirements differ: {transcript_id}")
        if not isinstance(observed, list) or not all(isinstance(item, str) for item in observed):
            raise ValueError(f"transcript observed event stream is malformed: {transcript_id}")
        if not isinstance(matched, list) or not all(isinstance(item, int) for item in matched):
            raise ValueError(f"transcript matched indexes are malformed: {transcript_id}")
        expected_indexes = subsequence_indexes(required, observed)
        if expected_indexes is None or list(expected_indexes) != matched:
            raise ValueError(f"transcript required event order is not runtime-bound: {transcript_id}")
        evidence_records.append(
            {
                "transcript_id": transcript_id,
                "event_source": transcript["event_source"],
                "observed_event_count": len(observed),
                "matched_indexes": matched,
                "evidence_sha256": hashlib.sha256(canonical_bytes(document)).hexdigest(),
            }
        )
    return evidence_records


def validate_phase_b_transcripts(
    transcript_dir: Path = DEFAULT_TRANSCRIPTS,
    approvals_path: Path = DEFAULT_APPROVALS,
    *,
    root: Path = ROOT,
    collected_nodes: set[str] | None = None,
    expected_approval_document_sha256: str = OWNER_APPROVAL_DOCUMENT_SHA256,
    allow_pending: bool = False,
    execute: bool = True,
) -> dict[str, Any]:
    if not approvals_path.is_file():
        raise ValueError(f"approval record is missing: {approvals_path}")
    approval_document = json.loads(approvals_path.read_text(encoding="utf-8"))
    if approval_document.get("schema_version") != APPROVAL_SCHEMA:
        raise ValueError("Phase B transcript approval schema is unsupported")
    if approval_document.get("required_count") != REQUIRED_COUNT:
        raise ValueError("Phase B approval record must require exactly 12 transcripts")
    approval_sha = approval_document_digest(approval_document)

    paths = sorted(transcript_dir.glob("*.json"))
    if len(paths) != REQUIRED_COUNT:
        raise ValueError(f"expected exactly 12 transcript files, found {len(paths)}")
    approvals = approval_document.get("approvals")
    if not isinstance(approvals, list) or len(approvals) != REQUIRED_COUNT:
        raise ValueError("approval record must contain exactly 12 entries")
    approval_by_id = {
        str(entry.get("transcript_id")): entry for entry in approvals if isinstance(entry, dict)
    }
    if len(approval_by_id) != REQUIRED_COUNT:
        raise ValueError("approval transcript IDs must be unique")

    nodes = collected_nodes if collected_nodes is not None else _collected_nodes(root)
    validated: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_families: set[str] = set()
    for path in paths:
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("schema_version") != TRANSCRIPT_SCHEMA:
            raise ValueError(f"unsupported Phase B transcript schema: {path}")
        transcript_id = str(document.get("transcript_id", "")).strip()
        family_id = str(document.get("family_id", "")).strip()
        evidence_scope = str(document.get("evidence_scope", "")).strip()
        if evidence_scope not in EVIDENCE_SCOPES:
            raise ValueError(f"invalid evidence scope: {transcript_id}: {evidence_scope}")
        if not transcript_id or transcript_id in seen_ids:
            raise ValueError("Phase B transcript IDs must be nonempty and unique")
        if family_id not in REQUIRED_FAMILIES or family_id in seen_families:
            raise ValueError(f"invalid or duplicate mandatory family: {family_id}")
        seen_ids.add(transcript_id)
        seen_families.add(family_id)
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
        event_source = str(machine.get("event_source", ""))
        if event_source not in ALLOWED_EVENT_SOURCES:
            raise ValueError(f"machine event source is invalid: {transcript_id}: {event_source}")
        for key in (
            "preconditions",
            "ordered_operations",
            "required_event_order",
            "required_assertions",
        ):
            value = machine.get(key)
            if (
                not isinstance(value, list)
                or not value
                or not all(isinstance(item, str) and item.strip() for item in value)
            ):
                raise ValueError(f"machine {key} is incomplete: {transcript_id}")
        test_node = str(machine.get("test_node", ""))
        if test_node not in nodes:
            raise ValueError(f"machine test node is not collected: {test_node}")
        test_path = root / test_node.split("::", 1)[0]
        if not test_path.is_file() and root != ROOT:
            test_path = ROOT / test_node.split("::", 1)[0]
        if not test_path.is_file():
            raise ValueError(f"machine test source is missing: {test_node}")
        test_source = test_path.read_text(encoding="utf-8")
        combined_claims = " ".join(
            [str(document.get("title", "")), *plain, *machine.get("preconditions", ())]
        ).lower()
        if evidence_scope == "EXACT_DECK_INTEGRATION" and "build_exact_game" not in test_source:
            raise ValueError(f"exact-deck evidence does not use build_exact_game: {transcript_id}")
        if evidence_scope == "MECHANIC_ISOLATION" and "exact deck" in combined_claims:
            raise ValueError(
                f"mechanic-isolation transcript overclaims exact-deck evidence: {transcript_id}"
            )
        if evidence_scope == "POLICY_INTEGRATION" and not any(
            marker in test_source
            for marker in (
                "ActionBroker",
                "StandardPolicy",
                "BoundedExplorer",
                "PolicyStrategicChoiceProvider",
            )
        ):
            raise ValueError(
                f"policy-integration evidence does not execute policy surfaces: {transcript_id}"
            )
        if evidence_scope == "REPLAY_AUDIT" and "replay" not in test_source.lower():
            raise ValueError(f"replay-audit evidence does not execute replay: {transcript_id}")

        digest = transcript_digest(document)
        approval = approval_by_id.get(transcript_id)
        if approval is None:
            raise ValueError(f"approval entry is missing: {transcript_id}")
        expected_path = str(path.relative_to(root))
        if approval.get("path") != expected_path or approval.get("sha256") != digest:
            raise ValueError(f"approval path or digest mismatch: {transcript_id}")
        status = str(approval.get("status", ""))
        if allow_pending and status not in {"PENDING_OWNER_APPROVAL", "APPROVED"}:
            raise ValueError(f"invalid approval status: {transcript_id}")
        validated.append(
            {
                "transcript_id": transcript_id,
                "family_id": family_id,
                "evidence_scope": evidence_scope,
                "event_source": event_source,
                "required_event_order": list(machine["required_event_order"]),
                "path": expected_path,
                "sha256": digest,
                "test_node": test_node,
            }
        )

    if seen_families != REQUIRED_FAMILIES:
        raise ValueError(
            f"mandatory transcript family mismatch: {sorted(REQUIRED_FAMILIES - seen_families)}"
        )
    if set(approval_by_id) != seen_ids:
        raise ValueError("approval entries and transcript files identify different sets")

    execution: dict[str, Any] = {"status": "NOT_EXECUTED", "passed": 0, "evidence": []}
    if execute:
        command = ["pytest", "-q", *[str(item["test_node"]) for item in validated]]
        with tempfile.TemporaryDirectory(prefix="phase-b-transcript-evidence-") as temp:
            evidence_dir = Path(temp)
            completed = subprocess.run(
                command,
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
                env={
                    **os.environ,
                    "PYTHONPATH": str(root / "src"),
                    EVIDENCE_DIR_ENV: str(evidence_dir),
                },
            )
            if completed.returncode != 0:
                raise ValueError(
                    f"named Phase B transcript execution failed: {completed.stdout}{completed.stderr}"
                )
            match = re.search(r"(\d+) passed", completed.stdout + completed.stderr)
            passed = int(match.group(1)) if match else 0
            if passed != REQUIRED_COUNT:
                raise ValueError(f"expected 12 executed transcript tests, observed {passed}")
            evidence = _validate_execution_evidence(evidence_dir, validated)
        execution = {
            "status": "PASS",
            "passed": passed,
            "command": " ".join(command),
            "evidence": evidence,
        }

    # The owner anchor remains the final strict gate. It is deliberately checked
    # after runtime evidence so a pending candidate still exposes stale or invented
    # event contracts instead of stopping before the named tests run.
    if not allow_pending:
        if approval_sha != expected_approval_document_sha256:
            raise ValueError("Phase B transcript approval record is not owner-anchored")
        for transcript_id in sorted(seen_ids):
            approval = approval_by_id[transcript_id]
            if str(approval.get("status", "")) != "APPROVED":
                raise ValueError(f"owner approval is pending: {transcript_id}")
            approved_by = str(approval.get("approved_by", "")).strip()
            approved_at = str(approval.get("approved_at", "")).strip()
            statement = str(approval.get("approval_statement", "")).strip()
            digest = next(
                str(item["sha256"])
                for item in validated
                if item["transcript_id"] == transcript_id
            )
            if approved_by != EXPECTED_OWNER or not _iso_timestamp(approved_at):
                raise ValueError(
                    f"owner approval identity or timestamp is invalid: {transcript_id}"
                )
            if transcript_id not in statement or digest not in statement:
                raise ValueError(
                    f"approval statement is not bound to ID and digest: {transcript_id}"
                )

    return {
        "schema_version": "phase-b-golden-transcript-validation-v2",
        "status": "CANDIDATE_PASS_PENDING_OWNER" if allow_pending else "PASS",
        "count": len(validated),
        "approval_document_sha256": approval_sha,
        "execution": execution,
        "transcripts": validated,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transcript-dir", type=Path, default=DEFAULT_TRANSCRIPTS)
    parser.add_argument("--approvals", type=Path, default=DEFAULT_APPROVALS)
    parser.add_argument("--allow-pending", action="store_true")
    args = parser.parse_args()
    try:
        result = validate_phase_b_transcripts(
            args.transcript_dir,
            args.approvals,
            allow_pending=args.allow_pending,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "FAIL", "reason": str(exc)}, indent=2))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
