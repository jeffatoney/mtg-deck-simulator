"""Explicit protected Phase A acceptance nodes owned by the referee."""

from __future__ import annotations

import json

from .reference_adapter import ROOT, assert_acceptance, load_scenario, run_scenario

MANIFEST = {
    item["acceptance_id"]: item
    for item in json.loads((ROOT / "automation/phase-a-reference-manifest.json").read_text())[
        "mappings"
    ]
}


def _run(acceptance_id: str) -> None:
    mapping = MANIFEST[acceptance_id]
    scenario = load_scenario(str(mapping["scenario_id"]))
    result = run_scenario(scenario)
    assert_acceptance(result, mapping, scenario)


def test_A1_protected_acceptance() -> None:
    _run("A1")


def test_A2_protected_acceptance() -> None:
    _run("A2")


def test_A3_protected_acceptance() -> None:
    _run("A3")


def test_A4_protected_acceptance() -> None:
    _run("A4")


def test_A5_protected_acceptance() -> None:
    _run("A5")


def test_A6_protected_acceptance() -> None:
    _run("A6")


def test_A7_protected_acceptance() -> None:
    _run("A7")


def test_B1_protected_acceptance() -> None:
    _run("B1")


def test_B2_protected_acceptance() -> None:
    _run("B2")


def test_B3_protected_acceptance() -> None:
    _run("B3")


def test_B4_protected_acceptance() -> None:
    _run("B4")


def test_B5_protected_acceptance() -> None:
    _run("B5")


def test_B6_protected_acceptance() -> None:
    _run("B6")


def test_C1_protected_acceptance() -> None:
    _run("C1")


def test_C2_protected_acceptance() -> None:
    _run("C2")


def test_C3_protected_acceptance() -> None:
    _run("C3")


def test_C4_protected_acceptance() -> None:
    _run("C4")


def test_C5_protected_acceptance() -> None:
    _run("C5")


def test_C6_protected_acceptance() -> None:
    _run("C6")


def test_C7_protected_acceptance() -> None:
    _run("C7")


def test_C8_protected_acceptance() -> None:
    _run("C8")


def test_D1_protected_acceptance() -> None:
    _run("D1")


def test_D2_protected_acceptance() -> None:
    _run("D2")


def test_D3_protected_acceptance() -> None:
    _run("D3")


def test_D4_protected_acceptance() -> None:
    _run("D4")


def test_D5_protected_acceptance() -> None:
    _run("D5")


def test_D6_protected_acceptance() -> None:
    _run("D6")


def test_D7_protected_acceptance() -> None:
    _run("D7")


def test_D8_protected_acceptance() -> None:
    _run("D8")


def test_D9_protected_acceptance() -> None:
    _run("D9")


def test_E1_protected_acceptance() -> None:
    _run("E1")


def test_E2_protected_acceptance() -> None:
    _run("E2")


def test_E3_protected_acceptance() -> None:
    _run("E3")


def test_E4_protected_acceptance() -> None:
    _run("E4")


def test_E5_protected_acceptance() -> None:
    _run("E5")


def test_F1_protected_acceptance() -> None:
    _run("F1")


def test_F2_protected_acceptance() -> None:
    _run("F2")


def test_F3_protected_acceptance() -> None:
    _run("F3")


def test_G1_protected_acceptance() -> None:
    _run("G1")


def test_G2_protected_acceptance() -> None:
    _run("G2")


def test_G3_protected_acceptance() -> None:
    _run("G3")


def test_G4_protected_acceptance() -> None:
    _run("G4")
