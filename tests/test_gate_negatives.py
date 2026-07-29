"""Negative tests: every gate must be shown to FAIL on the thing it claims to catch.

Both merged gates passed review while doing nothing, because every test asserted only
that they pass on a clean tree. A gate with no failing case is indistinguishable from
`return 0`. Each test here reproduces a real bypass that was demonstrated against the
previous implementation.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
IDENTITY_DOC = "docs/spec/identity/IDENTITY_MODEL_V2.0.0.md"
APPROVAL = "docs/spec/identity/IDENTITY_MODEL_V2.0.0_APPROVAL_RECORD.json"
MANIFEST = "docs/spec/identity/IDENTITY_MODEL_V2.0.0_LOCK_MANIFEST.txt"

BYPASSES = pytest.mark.parametrize(
    ("label", "source"),
    [
        ("direct import", "import mtg_sim\n"),
        ("direct from-import", "from mtg_sim import engine\n"),
        (
            "bare import_module binding",
            "from importlib import import_module\nimport_module('mtg_sim.executor')\n",
        ),
        (
            "aliased importlib module",
            "import importlib as il\nil.import_module('mtg_sim')\n",
        ),
        (
            "renamed import_module binding",
            "from importlib import import_module as f\nf('mtg_sim')\n",
        ),
        (
            "reassigned alias",
            "import importlib\ng = importlib.import_module\ng('mtg_sim')\n",
        ),
        (
            "literal concatenation",
            "import importlib\nimportlib.import_module('mtg_' + 'sim')\n",
        ),
        (
            "module name held in a variable",
            "_m = 'mtg_sim'\n__import__(_m)\n",
        ),
        (
            "loader API",
            "import importlib.util\n"
            "importlib.util.spec_from_file_location('x', 'legacy/mtg_sim/engine.py')\n",
        ),
        (
            "exec of read source",
            "exec(open('legacy/mtg_sim/engine.py').read())\n",
        ),
        (
            "subprocess shelling out to the legacy CLI",
            "import subprocess\nsubprocess.run(['python', '-c', 'import mtg_sim'])\n",
        ),
    ],
)


def _run(script: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(cwd / "scripts" / script)],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
def sandbox(tmp_path: Path) -> Path:
    """A minimal copy of the repository the gates can run against."""
    for relative in ("scripts", "src", "docs/spec/identity"):
        shutil.copytree(ROOT / relative, tmp_path / relative, dirs_exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "base"],
        cwd=tmp_path,
        check=True,
    )
    # The approval record cites a commit from the real repository, which does not exist
    # in this synthetic one. Repoint it at the sandbox's own HEAD so the baseline is
    # genuinely valid and each negative test isolates the single defect it introduces.
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True, check=True
    ).stdout.strip()
    approval = tmp_path / APPROVAL
    payload = json.loads(approval.read_text(encoding="utf-8"))
    payload["repository_document_commit_sha"] = head
    approval.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return tmp_path


# --------------------------------------------------------------------------
# boundary scanner
# --------------------------------------------------------------------------


def test_boundary_scanner_passes_on_clean_tree(sandbox: Path) -> None:
    result = _run("check_clean_engine_boundary.py", sandbox)
    assert result.returncode == 0, result.stdout
    assert json.loads(result.stdout)["status"] == "PASS"


@BYPASSES
def test_boundary_scanner_rejects_every_known_bypass(
    sandbox: Path, label: str, source: str
) -> None:
    (sandbox / "src" / "mtg_kernel" / "_probe.py").write_text(source, encoding="utf-8")
    result = _run("check_clean_engine_boundary.py", sandbox)
    assert result.returncode == 1, f"{label} was NOT caught:\n{result.stdout}"
    payload = json.loads(result.stdout)
    assert payload["status"] == "FAIL"
    assert payload["forbidden_findings"], label


def test_boundary_scanner_rejects_legacy_back_on_import_path(sandbox: Path) -> None:
    (sandbox / "src" / "mtg_sim").mkdir()
    (sandbox / "src" / "mtg_sim" / "__init__.py").write_text("", encoding="utf-8")
    result = _run("check_clean_engine_boundary.py", sandbox)
    assert result.returncode == 1
    assert "back on the installable import path" in result.stdout


def test_boundary_scanner_allows_ordinary_kernel_code(sandbox: Path) -> None:
    (sandbox / "src" / "mtg_kernel" / "_ok.py").write_text(
        "from dataclasses import dataclass\n"
        "import json\n"
        "@dataclass\n"
        "class Zone:\n"
        "    name: str\n"
        "def dump(z: Zone) -> str:\n"
        "    return json.dumps({'name': z.name})\n",
        encoding="utf-8",
    )
    result = _run("check_clean_engine_boundary.py", sandbox)
    assert result.returncode == 0, result.stdout


# --------------------------------------------------------------------------
# identity lock
# --------------------------------------------------------------------------


def test_identity_lock_passes_on_untouched_document(sandbox: Path) -> None:
    result = _run("check_identity_lock.py", sandbox)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["status"] == "PASS"


def test_identity_lock_rejects_tampered_then_relocked_document(sandbox: Path) -> None:
    """The exact attack that defeated the previous implementation.

    Edit the frozen model, recompute its digest, and rewrite both companion files so
    the three are mutually consistent again. The old checker printed PASS. The anchored
    checker must not.
    """
    import hashlib

    doc = sandbox / IDENTITY_DOC
    old_digest = hashlib.sha256(doc.read_bytes()).hexdigest()
    doc.write_text(
        doc.read_text(encoding="utf-8")
        + "\nREQ MODEL-HIDDEN-IDENTITY-001 is hereby downgraded to blocking: false.\n",
        encoding="utf-8",
    )
    new_digest = hashlib.sha256(doc.read_bytes()).hexdigest()

    for relative in (APPROVAL, MANIFEST):
        target = sandbox / relative
        target.write_text(
            target.read_text(encoding="utf-8").replace(old_digest, new_digest),
            encoding="utf-8",
        )

    result = _run("check_identity_lock.py", sandbox)
    assert result.returncode == 1, (
        "tampered-then-relocked document was accepted; the anchor is not load-bearing:\n"
        + result.stdout
    )
    assert "anchored digest" in result.stdout


def test_identity_lock_rejects_repointed_document(sandbox: Path) -> None:
    approval = sandbox / APPROVAL
    payload = json.loads(approval.read_text(encoding="utf-8"))
    payload["document"] = "docs/spec/identity/README.md"
    approval.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    result = _run("check_identity_lock.py", sandbox)
    assert result.returncode == 1
    assert "anchored document" in result.stdout


def test_identity_lock_rejects_unfrozen_status(sandbox: Path) -> None:
    approval = sandbox / APPROVAL
    payload = json.loads(approval.read_text(encoding="utf-8"))
    payload["effective_status"] = "DRAFT"
    approval.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    result = _run("check_identity_lock.py", sandbox)
    assert result.returncode == 1
    assert "effective_status" in result.stdout


def test_identity_lock_rejects_unknown_approval_commit(sandbox: Path) -> None:
    approval = sandbox / APPROVAL
    payload = json.loads(approval.read_text(encoding="utf-8"))
    payload["repository_document_commit_sha"] = "0" * 40
    approval.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    result = _run("check_identity_lock.py", sandbox)
    assert result.returncode == 1
    assert "not present in this repository" in result.stdout


# --------------------------------------------------------------------------
# out-of-tree anchor
# --------------------------------------------------------------------------


def _run_env(script: str, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    import os

    merged = {**os.environ, **env}
    return subprocess.run(
        [sys.executable, str(cwd / "scripts" / script)],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        env=merged,
    )


REAL_DIGEST = "c839c16aa08ed6053233745fd2a35c38cbe4aadb16423ecac3d5390999af3ce6"


def test_env_anchor_agreeing_passes(sandbox: Path) -> None:
    result = _run_env("check_identity_lock.py", sandbox, {"IDENTITY_MODEL_SHA256": REAL_DIGEST})
    assert result.returncode == 0, result.stdout


def test_env_anchor_disagreeing_fails(sandbox: Path) -> None:
    """The same-PR attack: the tree is internally consistent, the variable is not."""
    result = _run_env("check_identity_lock.py", sandbox, {"IDENTITY_MODEL_SHA256": "0" * 64})
    assert result.returncode == 1
    assert "disagrees with EXPECTED_DOCUMENT_SHA256" in result.stdout


def test_env_anchor_is_mandatory_under_github_actions(sandbox: Path) -> None:
    """Dropping the env: block from the workflow must break the gate, not downgrade it."""
    result = _run_env(
        "check_identity_lock.py",
        sandbox,
        {"GITHUB_ACTIONS": "true", "IDENTITY_MODEL_SHA256": ""},
    )
    assert result.returncode == 1
    assert "out-of-tree anchor is mandatory" in result.stdout


def test_tree_only_tamper_still_fails_even_with_matching_env(sandbox: Path) -> None:
    """Edit document + in-tree constant together; the repository variable still wins."""
    import hashlib

    doc = sandbox / IDENTITY_DOC
    old = hashlib.sha256(doc.read_bytes()).hexdigest()
    doc.write_text(doc.read_text(encoding="utf-8") + "\ntampered\n", encoding="utf-8")
    new = hashlib.sha256(doc.read_bytes()).hexdigest()
    for relative in (APPROVAL, MANIFEST, "scripts/check_identity_lock.py"):
        target = sandbox / relative
        target.write_text(target.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")
    result = _run_env("check_identity_lock.py", sandbox, {"IDENTITY_MODEL_SHA256": old})
    assert result.returncode == 1, (
        "a fully self-consistent tree edit was accepted; the out-of-tree anchor is not "
        "load-bearing:\n" + result.stdout
    )
    assert "IDENTITY_MODEL_SHA256" in result.stdout
