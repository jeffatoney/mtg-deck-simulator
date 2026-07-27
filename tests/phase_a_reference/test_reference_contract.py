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


def test_A1_assert_a1() -> None:
    _run("A1")


def test_A2_assert_a2() -> None:
    _run("A2")


def test_A3_assert_a3() -> None:
    _run("A3")


def test_A4_assert_a4() -> None:
    _run("A4")


def test_A5_assert_a5() -> None:
    _run("A5")


def test_A6_assert_a6() -> None:
    _run("A6")


def test_A7_assert_a7() -> None:
    _run("A7")


def test_B1_assert_b1() -> None:
    _run("B1")


def test_B2_assert_b2() -> None:
    _run("B2")


def test_B3_assert_b3() -> None:
    _run("B3")


def test_B4_assert_b4() -> None:
    _run("B4")


def test_B5_assert_b5() -> None:
    _run("B5")


def test_B6_assert_b6() -> None:
    _run("B6")


def test_C1_assert_c1() -> None:
    _run("C1")


def test_C2_assert_c2() -> None:
    _run("C2")


def test_C3_assert_c3() -> None:
    _run("C3")


def test_C4_assert_c4() -> None:
    _run("C4")


def test_C5_assert_c5() -> None:
    _run("C5")


def test_C6_assert_c6() -> None:
    _run("C6")


def test_C7_assert_c7() -> None:
    _run("C7")


def test_C8_assert_c8() -> None:
    _run("C8")


def test_D1_assert_d1() -> None:
    _run("D1")


def test_D2_assert_d2() -> None:
    _run("D2")


def test_D3_assert_d3() -> None:
    _run("D3")


def test_D4_assert_d4() -> None:
    _run("D4")


def test_D5_assert_d5() -> None:
    _run("D5")


def test_D6_assert_d6() -> None:
    _run("D6")


def test_D7_assert_d7() -> None:
    _run("D7")


def test_D8_assert_d8() -> None:
    _run("D8")


def test_D9_assert_d9() -> None:
    _run("D9")


def test_E1_assert_e1() -> None:
    _run("E1")


def test_E2_assert_e2() -> None:
    _run("E2")


def test_E3_assert_e3() -> None:
    _run("E3")


def test_E4_assert_e4() -> None:
    _run("E4")


def test_E5_assert_e5() -> None:
    _run("E5")


def test_F1_assert_f1() -> None:
    _run("F1")


def test_F2_assert_f2() -> None:
    _run("F2")


def test_F3_assert_f3() -> None:
    _run("F3")


def test_G1_assert_g1() -> None:
    _run("G1")


def test_G2_assert_g2() -> None:
    _run("G2")


def test_G3_assert_g3() -> None:
    _run("G3")


def test_G4_assert_g4() -> None:
    _run("G4")
