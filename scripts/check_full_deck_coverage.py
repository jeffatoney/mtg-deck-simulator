#!/usr/bin/env python3
"""Validate exact-deck inventory and reviewed compositions without claiming execution."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mtg_deck import load_exact_deck_package  # noqa: E402
from mtg_deck.package import (  # noqa: E402
    COMPOSITION_REVIEWED,
    EXECUTION_UNVERIFIED,
)


def main() -> int:
    try:
        package = load_exact_deck_package()
    except Exception as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}, indent=2))
        return 1
    invalid_composition = [
        record.name
        for record in package.coverage
        if record.composition_status != COMPOSITION_REVIEWED
    ]
    premature_execution_claims = [
        record.name
        for record in package.coverage
        if record.execution_status != EXECUTION_UNVERIFIED
    ]
    if (
        invalid_composition
        or premature_execution_claims
        or len(package.coverage) != 80
        or package.physical_card_count != 100
    ):
        print(
            json.dumps(
                {
                    "status": "FAIL",
                    "invalid_composition": invalid_composition,
                    "premature_execution_claims": premature_execution_claims,
                    "coverage_count": len(package.coverage),
                    "physical_card_count": package.physical_card_count,
                },
                indent=2,
            )
        )
        return 1
    print(
        json.dumps(
            {
                "status": "PASS",
                "oracle_name_count": 80,
                "library_card_count": package.library_count,
                "commander_count": package.commander_count,
                "physical_card_count": package.physical_card_count,
                "composition_status": COMPOSITION_REVIEWED,
                "execution_status": EXECUTION_UNVERIFIED,
                "phase_b_complete": False,
                "legacy_evidence_used": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
