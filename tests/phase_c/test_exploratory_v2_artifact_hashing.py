"""Exact serialized-byte digest contracts for Exploratory V2 artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from mtg_runs.exact_json_bytes import serialize_typed_json_bytes
from mtg_runs.phase_c_exploratory_v2_diagnostic import (
    DIGEST_SEMANTICS,
    MANIFEST_SCHEMA,
    SUMMARY_SCHEMA,
    artifact_schema_classification,
    verify_exact_serialized_artifact,
)
from mtg_search.directed_v2 import canonical_sha256


def _write(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)


def _fixture(root: Path) -> tuple[Path, Path, Path]:
    arm = root / "arm"
    game = arm / "games/game-0001.json"
    game_body = serialize_typed_json_bytes(
        {
            "schema_version": "phase-c-exploratory-v2-diagnostic-game-v2",
            "digest_semantics": DIGEST_SEMANTICS,
            "integer_key_probe": {1: "integer"},
        }
    )
    _write(game, game_body)
    inventory = [
        {
            "relative_path": "games/game-0001.json",
            "byte_size": len(game_body),
            "sha256": hashlib.sha256(game_body).hexdigest(),
        }
    ]
    inventory_sha = canonical_sha256(inventory)
    summary = {
        "schema_version": SUMMARY_SCHEMA,
        "digest_semantics": DIGEST_SEMANTICS,
        "game_count": 1,
        "game_file_inventory": inventory,
        "game_file_inventory_sha256": inventory_sha,
        "game_payload_sha256": inventory_sha,
    }
    summary_body = serialize_typed_json_bytes(summary)
    summary_path = arm / "NON_AUTHORIZED_DIAGNOSTIC-summary.json"
    _write(summary_path, summary_body)
    manifest = {
        "schema_version": MANIFEST_SCHEMA,
        "digest_semantics": DIGEST_SEMANTICS,
        "game_count": 1,
        "game_file_inventory": inventory,
        "game_file_inventory_sha256": inventory_sha,
        "summary_file_path": summary_path.name,
        "summary_byte_size": len(summary_body),
        "summary_file_sha256": hashlib.sha256(summary_body).hexdigest(),
    }
    manifest_path = arm / "NON_AUTHORIZED_DIAGNOSTIC-manifest.json"
    _write(manifest_path, serialize_typed_json_bytes(manifest))
    return arm, game, manifest_path


def test_exact_bytes_change_for_whitespace_and_key_type() -> None:
    compact = json.dumps({"x": 1}, sort_keys=True, separators=(",", ":")).encode()
    pretty = json.dumps({"x": 1}, sort_keys=True, indent=2).encode()
    assert hashlib.sha256(compact).hexdigest() != hashlib.sha256(pretty).hexdigest()
    integer_key = serialize_typed_json_bytes({"probe": {1: "value"}})
    string_key = serialize_typed_json_bytes({"probe": {"1": "value"}})
    assert integer_key != string_key
    assert hashlib.sha256(integer_key).hexdigest() != hashlib.sha256(string_key).hexdigest()


def test_exact_byte_verifier_needs_no_integer_key_restoration(tmp_path: Path) -> None:
    arm, _, _ = _fixture(tmp_path)
    result = verify_exact_serialized_artifact(arm)
    assert result["status"] == "PASS"
    assert result["digest_semantics"] == DIGEST_SEMANTICS


def test_missing_extra_or_changed_game_file_fails(tmp_path: Path) -> None:
    arm, game, _ = _fixture(tmp_path)
    original = game.read_bytes()
    game.unlink()
    with pytest.raises(ValueError, match="game-file set"):
        verify_exact_serialized_artifact(arm)
    _write(game, original)
    extra = arm / "games/game-0002.json"
    _write(extra, b"{}\n")
    with pytest.raises(ValueError, match="game-file set"):
        verify_exact_serialized_artifact(arm)
    extra.unlink()
    _write(game, original + b" ")
    with pytest.raises(ValueError, match="byte size|SHA-256"):
        verify_exact_serialized_artifact(arm)


def test_manifest_inventory_order_is_canonical_and_v1_is_only_historical(tmp_path: Path) -> None:
    arm, _, manifest_path = _fixture(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    duplicate = dict(manifest["game_file_inventory"][0])
    duplicate["relative_path"] = "games/game-0000.json"
    manifest["game_file_inventory"] = [manifest["game_file_inventory"][0], duplicate]
    manifest["game_file_inventory_sha256"] = canonical_sha256(manifest["game_file_inventory"])
    _write(manifest_path, serialize_typed_json_bytes(manifest))
    with pytest.raises(ValueError, match="canonical path order"):
        verify_exact_serialized_artifact(arm)

    assert (
        artifact_schema_classification(
            {"schema_version": "phase-c-exploratory-v2-diagnostic-manifest-v1"}
        )
        == "SUPERSEDED_FOR_FINAL_CLOSEOUT"
    )
