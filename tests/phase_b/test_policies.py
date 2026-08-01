from __future__ import annotations

from mtg_policy.config import REQUIRED_AXES, load_policy_matrix, load_seed_split
from mtg_policy.standard import StandardPolicy


def test_policy_matrix_is_precommitted_composable_and_complete() -> None:
    matrix = load_policy_matrix()
    assert len(matrix) >= 12
    assert len({bundle.policy_config_id for bundle in matrix}) == len(matrix)
    assert all(REQUIRED_AXES <= bundle.values.keys() for bundle in matrix)
    assert all(bundle.values["documented_before_results"] is True for bundle in matrix)
    assert all(bundle.values["validation_seed_influence_allowed"] is False for bundle in matrix)


def test_discovery_validation_seeds_are_precommitted_and_disjoint() -> None:
    seeds = load_seed_split()
    assert len(seeds.discovery) == 300
    assert len(seeds.validation) == 200
    assert not set(seeds.discovery).intersection(seeds.validation)


def test_mulligan_policy_compares_hypotheses_at_7_6_5_4() -> None:
    matrix = load_policy_matrix()
    balanced = StandardPolicy(next(bundle for bundle in matrix if bundle.policy_config_id == "anchor_balanced"))
    aggressive = StandardPolicy(next(bundle for bundle in matrix if bundle.policy_config_id == "anchor_aggressive"))
    names = ("Island", "Mountain", "Sol Ring", "Opt", "Abrade", "Twinflame", "Dualcaster Mage")
    types = (("Land",), ("Land",), ("Artifact",), ("Instant",), ("Instant",), ("Sorcery",), ("Creature",))
    assert balanced.decide_keep(7, names, types).keep
    assert aggressive.decide_keep(7, names, types).keep
    for size in (6, 5, 4):
        decision = balanced.decide_keep(size, names[:size], types[:size])
        assert decision.hand_size == size
        assert isinstance(decision.keep, bool)
