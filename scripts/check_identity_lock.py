"""Verify the frozen identity specification, approval record, and lock manifest.

The digest below is the anchor. Everything else in the lock -- the approval record,
the lock manifest, the approval statement -- is data that lives in the repository and
can be rewritten by anyone editing the repository. If this script derived its
expectation from that data, the check would be a tautology: edit the document,
recompute the digest, update the two companion files, and the "frozen" model would
report itself frozen. That was the state of this script before, and it was
demonstrated -- a one-line append plus a single `sed` rewrote a blocking requirement
out of IDENTITY_MODEL_V2.0.0 and this check still printed PASS.

Anchoring on a constant makes tampering *visible*: it now requires editing a tracked
script, which appears in the pull-request diff. It does not make tampering
*impossible* -- the constant lives in the same mutable tree, writable by the same
credential, in the same pull request as the document it anchors. It is tamper-evident,
not tamper-proof. Do not describe it as immutable.

The out-of-tree anchor closes that gap. When ``IDENTITY_MODEL_SHA256`` is set in the
environment (in CI, from a repository *variable*, which a pull request cannot alter),
the constant below, the environment value, and the bytes on disk must all agree. A
change to the tree alone therefore cannot win: editing the document and the constant
together still disagrees with the repository variable.

Under GitHub Actions the environment anchor is REQUIRED. A workflow that stops passing
it fails this check rather than silently downgrading to the in-tree constant.

Two residual holes require repository controls outside this script:

* this script could be edited in the same pull request to skip its own check;
* the workflow step invoking it could be deleted, or made non-required.

CODEOWNERS identifies the affected paths but does not enforce review by itself.
A protected-branch rule or repository ruleset must require the CI job and an
independent approval for gate changes. The repository variable is the external
digest anchor; branch protection is a separate human-configured control.

Rotating the identity model is a deliberate change in three places: the document and
its companions, EXPECTED_DOCUMENT_SHA256 here, and the repository variable -- the last
of which is a repository setting, not a commit.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

# --- the anchors ------------------------------------------------------------
EXPECTED_DOCUMENT_PATH = "docs/spec/identity/IDENTITY_MODEL_V2.0.0.md"
# In-tree anchor: tamper-evident. Must equal the repository variable below.
EXPECTED_DOCUMENT_SHA256 = "c839c16aa08ed6053233745fd2a35c38cbe4aadb16423ecac3d5390999af3ce6"
# Out-of-tree anchor: set in CI from vars.IDENTITY_MODEL_V2_SHA256, which lives in
# repository settings and cannot be changed by a pull request.
ENV_ANCHOR = "IDENTITY_MODEL_SHA256"
EXPECTED_STATUS = "FROZEN_BINDING_FOR_PHASE_A"
# ----------------------------------------------------------------------------

DOCUMENT_PATH = ROOT / EXPECTED_DOCUMENT_PATH
APPROVAL_PATH = ROOT / "docs/spec/identity/IDENTITY_MODEL_V2.0.0_APPROVAL_RECORD.json"
MANIFEST_PATH = ROOT / "docs/spec/identity/IDENTITY_MODEL_V2.0.0_LOCK_MANIFEST.txt"


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object in {path}")
    return value


def _require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def _git(*args: str) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(["git", *args], cwd=ROOT, check=False, capture_output=True, text=True)
    except OSError:
        return None


def _git_blob_sha(path: Path) -> str | None:
    """Content-addressed blob id, or None when git is unavailable.

    This is only a cross-check that the recorded blob id matches the bytes on disk.
    It is NOT an anchor: a blob id is a pure function of file content, so anyone
    editing the document can recompute it. EXPECTED_DOCUMENT_SHA256 is the anchor.
    """
    completed = _git("hash-object", str(path))
    if completed is None or completed.returncode != 0:
        return None
    return completed.stdout.strip()


def _commit_exists(commit_sha: str) -> bool | None:
    """True when the commit exists here, False when it does not, None without git."""
    completed = _git("cat-file", "-e", f"{commit_sha}^{{commit}}")
    if completed is None:
        return None
    return completed.returncode == 0


def main() -> int:
    errors: list[str] = []

    for path in (DOCUMENT_PATH, APPROVAL_PATH, MANIFEST_PATH):
        _require(
            path.is_file(),
            f"missing required lock file: {path.relative_to(ROOT)}",
            errors,
        )
    if errors:
        print("Identity-model lock verification failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    document_bytes = DOCUMENT_PATH.read_bytes()
    actual_digest = hashlib.sha256(document_bytes).hexdigest()

    # The load-bearing assertion: the document on disk is byte-for-byte the document
    # this script was written to accept. Compared against the constant above, never
    # against a value read from the repository.
    _require(
        actual_digest == EXPECTED_DOCUMENT_SHA256,
        f"canonical identity document does not match the anchored digest: "
        f"expected {EXPECTED_DOCUMENT_SHA256}, got {actual_digest}",
        errors,
    )

    # Out-of-tree anchor. Required under GitHub Actions; optional locally so a developer
    # can run the check without repository settings.
    env_anchor = os.environ.get(ENV_ANCHOR, "").strip()
    in_github_actions = os.environ.get("GITHUB_ACTIONS") == "true"
    if in_github_actions and not env_anchor:
        errors.append(
            f"{ENV_ANCHOR} is not set. Under CI the out-of-tree anchor is mandatory: "
            f"set it from the repository variable vars.IDENTITY_MODEL_V2_SHA256. A "
            f"workflow that stops passing it must fail, not fall back to the in-tree "
            f"constant."
        )
    elif env_anchor:
        _require(
            env_anchor == EXPECTED_DOCUMENT_SHA256,
            f"{ENV_ANCHOR} ({env_anchor}) disagrees with EXPECTED_DOCUMENT_SHA256 in "
            f"this script. The repository variable is authoritative; a tree-only change "
            f"cannot move it.",
            errors,
        )
        _require(
            env_anchor == actual_digest,
            f"{ENV_ANCHOR} ({env_anchor}) does not match the document on disk ({actual_digest})",
            errors,
        )
    _require(
        not document_bytes.startswith(b"\xef\xbb\xbf"),
        "approved document contains a BOM",
        errors,
    )
    _require(
        b"\r\n" not in document_bytes,
        "approved document contains CRLF line endings",
        errors,
    )

    approval = _load_json(APPROVAL_PATH)
    expected_statement = f"APPROVE IDENTITY_MODEL_V2.0.0 SHA256 {EXPECTED_DOCUMENT_SHA256}"

    _require(
        approval.get("document") == EXPECTED_DOCUMENT_PATH,
        f"approval record does not name the anchored document {EXPECTED_DOCUMENT_PATH}",
        errors,
    )
    _require(
        approval.get("document_sha256") == EXPECTED_DOCUMENT_SHA256,
        "approval record digest does not agree with the anchored digest",
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
    _require(
        bool(approval.get("approved_at")),
        "approval record has no approval timestamp",
        errors,
    )
    _require(
        approval.get("approval_statement") == expected_statement,
        "approval statement does not bind the anchored digest",
        errors,
    )

    actual_blob = _git_blob_sha(DOCUMENT_PATH)
    if actual_blob is not None:
        _require(
            approval.get("repository_document_blob_sha") == actual_blob,
            f"recorded blob id {approval.get('repository_document_blob_sha')!r} does not "
            f"match the document on disk ({actual_blob})",
            errors,
        )

    recorded_commit = approval.get("repository_document_commit_sha")
    if not (isinstance(recorded_commit, str) and len(recorded_commit) == 40):
        errors.append("approval record has no valid repository_document_commit_sha")
    elif _commit_exists(recorded_commit) is False:
        errors.append(
            f"approval commit {recorded_commit} is not present in this repository; "
            f"the approval record cites history that does not exist here"
        )

    manifest = MANIFEST_PATH.read_text(encoding="utf-8")
    for line in (
        f"Status: {EXPECTED_STATUS}",
        f"Canonical approved document: {EXPECTED_DOCUMENT_PATH}",
        f"Document SHA-256: {EXPECTED_DOCUMENT_SHA256}",
        f"Approval statement: {expected_statement}",
    ):
        _require(line in manifest, f"lock manifest is missing: {line}", errors)

    if errors:
        print("Identity-model lock verification failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(
        json.dumps(
            {
                "status": "PASS",
                "anchor_in_tree": "EXPECTED_DOCUMENT_SHA256 in scripts/check_identity_lock.py",
                "anchor_out_of_tree": (
                    f"{ENV_ANCHOR} (repository variable)"
                    if os.environ.get(ENV_ANCHOR, "").strip()
                    else "ABSENT -- tamper-evident only; see docs/audit/GATE_KNOWN_LIMITS.md"
                ),
                "approved_at": approval["approved_at"],
                "approved_by": approval["approved_by"],
                "document": EXPECTED_DOCUMENT_PATH,
                "document_sha256": EXPECTED_DOCUMENT_SHA256,
                "effective_status": EXPECTED_STATUS,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
