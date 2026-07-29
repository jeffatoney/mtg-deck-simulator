"""Legacy behavior-primitive tests. ARCHIVAL_REFERENCE_ONLY.

Split out of tests/test_offline_sources.py. These assert the behavior of
`mtg_sim.behaviors`, which is quarantined legacy rules logic -- exactly the category
the Phase A authority map classifies PROHIBITED_AS_PHASE_A_EVIDENCE. They are retained
as history and are outside `testpaths`; running them requires PYTHONPATH=legacy and
they must never gate a merge.
"""

from __future__ import annotations

from mtg_sim.behaviors import (
    EXECUTABLE_IMPLEMENTATIONS,
    LibraryState,
    MalcolmDamageEvent,
    curiosity_draws,
    glint_horn_damage,
    malcolm_treasures,
)
from mtg_sources.offline_sources import load_behavior_registry


def test_behavior_declarations_are_not_all_executable_yet() -> None:
    declared = {entry.implementation for entry in load_behavior_registry()}
    missing = declared - EXECUTABLE_IMPLEMENTATIONS
    assert missing


def test_malcolm_treasures_are_opponent_dependent() -> None:
    assert malcolm_treasures(MalcolmDamageEvent((True, False, True))) == 2
    assert malcolm_treasures(MalcolmDamageEvent((False, False, False))) == 0


def test_empty_library_draw_fails_closed() -> None:
    try:
        curiosity_draws(1, LibraryState(0))
    except ValueError as exc:
        assert "empty" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("drawing from an empty library must fail closed")


def test_glint_horn_damage_scales_per_discard_and_opponent() -> None:
    assert glint_horn_damage(discarded_cards=2, opponents=3) == 6
