from __future__ import annotations

from mtg_sim.rules_competency import COMPETENCY_CASES

REQUIRED_IDS = {
    *(f"CR-{i:03d}" for i in range(1, 23)),
    *(f"EL-{i:03d}" for i in range(1, 8)),
    *(f"OT-{i:03d}" for i in range(1, 13)),
    *(f"PROP-{i:03d}" for i in range(1, 11)),
    *(f"BOUND-{i:03d}" for i in range(1, 14)),
}


def test_every_required_phase6_case_exists_once_with_metadata():
    ids = [case.test_id for case in COMPETENCY_CASES]
    assert len(ids) == len(set(ids))
    assert set(ids) == REQUIRED_IDS
    for case in COMPETENCY_CASES:
        assert case.rules_refs
        assert case.expected
        assert case.description


def test_complete_competency_case_results_match_expected():
    mismatches = []
    for case in COMPETENCY_CASES:
        actual = case.check()
        if actual != case.expected:
            mismatches.append((case.test_id, case.expected, actual))
    assert not mismatches
