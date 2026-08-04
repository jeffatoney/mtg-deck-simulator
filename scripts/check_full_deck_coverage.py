#!/usr/bin/env python3
"""Validate exact-deck inventory, reviewed compositions, and bounded execution claims."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mtg_deck import load_exact_deck_package  # noqa: E402
from mtg_deck.package import (  # noqa: E402
    COMPOSITION_REVIEWED,
    EXECUTION_IMPLEMENTED,
    EXECUTION_UNVERIFIED,
    IMPLEMENTED_CARDS,
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
    invalid_execution_status = [
        record.name
        for record in package.coverage
        if record.execution_status not in {EXECUTION_IMPLEMENTED, EXECUTION_UNVERIFIED}
    ]
    implemented = {
        record.name
        for record in package.coverage
        if record.execution_status == EXECUTION_IMPLEMENTED
    }
    unverified = {
        record.name
        for record in package.coverage
        if record.execution_status == EXECUTION_UNVERIFIED
    }
    execution_claim_mismatch = sorted(implemented.symmetric_difference(IMPLEMENTED_CARDS))
    if (
        invalid_composition
        or invalid_execution_status
        or execution_claim_mismatch
        or implemented.intersection(unverified)
        or len(implemented) + len(unverified) != len(package.coverage)
        or len(package.coverage) != 80
        or package.physical_card_count != 100
    ):
        print(
            json.dumps(
                {
                    "status": "FAIL",
                    "invalid_composition": invalid_composition,
                    "invalid_execution_status": invalid_execution_status,
                    "execution_claim_mismatch": execution_claim_mismatch,
                    "implemented": sorted(implemented),
                    "unverified_count": len(unverified),
                    "coverage_count": len(package.coverage),
                    "physical_card_count": package.physical_card_count,
                },
                indent=2,
                sort_keys=True,
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
                "implemented_cards": sorted(implemented),
                "implemented_count": len(implemented),
                "unverified_count": len(unverified),
                "phase_b_complete": len(implemented) == len(package.coverage),
                "legacy_evidence_used": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
