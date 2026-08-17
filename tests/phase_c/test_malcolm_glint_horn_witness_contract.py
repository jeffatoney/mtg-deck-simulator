from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
ARCHIVE = ROOT / "docs/audit/phase-c-postpilot/evidence/pr100-glint-horn-repaired-behavior-4d15c185.zip"
EXPECTED_ARCHIVE_SHA256 = "5f1706e2a9f1ef906938f6eef972c0f7258226f5b2e5dcb0ed008febb62eb996"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _shape(value: Any, depth: int = 0) -> Any:
    if depth >= 3:
        return type(value).__name__
    if isinstance(value, dict):
        return {str(key): _shape(item, depth + 1) for key, item in sorted(value.items())}
    if isinstance(value, list):
        if not value:
            return []
        return [_shape(value[0], depth + 1)]
    return type(value).__name__


def test_stage3_repaired_archive_probe() -> None:
    raw_archive = ARCHIVE.read_bytes()
    assert _sha256(raw_archive) == EXPECTED_ARCHIVE_SHA256
    probe: dict[str, Any] = {
        "archive_sha256": _sha256(raw_archive),
        "archive_size": len(raw_archive),
        "members": {},
    }
    with zipfile.ZipFile(ARCHIVE) as bundle:
        probe["member_names"] = sorted(bundle.namelist())
        for name in sorted(bundle.namelist()):
            raw = bundle.read(name)
            payload = json.loads(raw)
            decisions = payload.get("decisions", [])
            record: dict[str, Any] = {
                "sha256": _sha256(raw),
                "size": len(raw),
                "top_keys": sorted(payload),
                "shape": _shape(payload),
                "decision_count": len(decisions),
            }
            if decisions:
                record["decision0_keys"] = sorted(decisions[0])
                record["decision0_shape"] = _shape(decisions[0])
                interesting = []
                for index, decision in enumerate(decisions):
                    encoded = json.dumps(decision, sort_keys=True)
                    if "malcolm_glint_horn" in encoded or "Glint-Horn Buccaneer" in encoded:
                        interesting.append(
                            {
                                "index": index,
                                "keys": sorted(decision),
                                "turn": decision.get("turn"),
                                "phase": decision.get("phase"),
                                "step": decision.get("step"),
                                "selected": decision.get("selected"),
                                "selected_public_key": decision.get("selected_public_key"),
                            }
                        )
                    if len(interesting) >= 5:
                        break
                record["first_interesting"] = interesting
            probe["members"][name] = record
    raise AssertionError("STAGE3_ARCHIVE_PROBE=" + json.dumps(probe, sort_keys=True))
