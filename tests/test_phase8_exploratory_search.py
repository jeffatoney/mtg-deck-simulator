from __future__ import annotations

import pytest

from mtg_sim.domain import Phase, Step, TerminalStatus, Observation
from mtg_sim.exploratory_search import (
    BeliefState,
    ExploratoryResultRecord,
    ExploratorySearch,
    ExploratorySearchError,
    PublicActionCandidate,
    ResultCategory,
    SearchScore,
    reject_cross_policy_result_access,
    reject_opponent_dependent_line,
    validate_replay_seed_set,
)


def observation(*, library_size: int = 4, known_top_library: tuple[()] = ()) -> Observation:
    return Observation(
        hand=(("c1", "Island"),),
        battlefield=(),
        graveyard_names=(),
        exile_names=(),
        command_zone_names=("Malcolm, Keen-Eyed Navigator", "Breeches, Brazen Plunderer"),
        stack=(),
        players=((0, 40, False), (1, 40, False), (2, 40, False), (3, 40, False)),
        turn=1,
        phase=Phase.PRECOMBAT_MAIN,
        step=Step.MAIN,
        land_plays_this_turn=0,
        commander_cast_counts={},
        terminal_status=TerminalStatus.ONGOING,
        library_size=library_size,
        known_top_library=known_top_library,
    )


def belief() -> BeliefState:
    return BeliefState(("Opt", "Sol Ring", "Mountain", "Island"), 4, 12345, "d0")


def test_bounded_search_applies_fixed_limits_and_logs_samples() -> None:
    candidates = tuple(
        PublicActionCandidate(
            str(i), f"action_{i}", ("CR 117.5",), True, SearchScore(cards_accessed=i)
        )
        for i in range(20)
    )
    result = ExploratorySearch().choose(
        observation=observation(), belief=belief(), candidates=candidates
    )
    assert result.category is ResultCategory.BEST_BOUNDED_SEARCH
    assert result.log.branches_searched == 12
    assert result.log.maximum_depth == 3
    assert result.log.nodes_evaluated <= 5000
    assert "candidate_branch_limit_12" in result.log.beam_pruning
    assert "beam_width_8" in result.log.beam_pruning
    assert len(result.log.rollout_sample_seeds) > 0
    assert result.log.actual_hidden_future_order_inaccessible is True


def test_search_rejects_ordered_future_library_access() -> None:
    obs = observation(known_top_library=("Sol Ring",))  # type: ignore[arg-type]
    with pytest.raises(ExploratorySearchError, match="future library"):
        ExploratorySearch().choose(
            observation=obs,
            belief=belief(),
            candidates=(PublicActionCandidate("a", "pass_priority", (), True),),
        )


def test_search_rejects_unvalidated_candidate_actions() -> None:
    with pytest.raises(ExploratorySearchError, match="shared legality validator"):
        ExploratorySearch().choose(
            observation=observation(),
            belief=belief(),
            candidates=(PublicActionCandidate("illegal", "shortcut", (), False),),
        )


def test_common_random_draw_samples_do_not_depend_on_actual_future_order() -> None:
    b = belief()
    first = b.sample_unknown_draws(depth=1, action_id="a")
    second = BeliefState(
        tuple(reversed(b.unseen_card_multiset)), 4, 12345, "d0"
    ).sample_unknown_draws(depth=1, action_id="a")
    assert [seed for seed, _ in first] == [seed for seed, _ in second]


def test_search_rejects_another_policy_result_access() -> None:
    with pytest.raises(ExploratorySearchError, match="another policy result"):
        reject_cross_policy_result_access(
            current_policy_id="exploratory_a", requested_result_policy_id="standard_b"
        )


def test_search_rejects_unspecified_or_favorable_opponent_assumptions() -> None:
    with pytest.raises(ExploratorySearchError, match="unspecified opponent resources"):
        reject_opponent_dependent_line(
            opponent_resources_specified=False, opponent_choice_policy="documented"
        )
    with pytest.raises(ExploratorySearchError, match="favorable opponent choices"):
        reject_opponent_dependent_line(
            opponent_resources_specified=True, opponent_choice_policy="favorable_to_this_deck"
        )


def test_result_records_distinguish_manual_replay_and_reject_post_result_optimization() -> None:
    with pytest.raises(ExploratorySearchError, match="post-result optimization"):
        ExploratoryResultRecord(
            1,
            ResultCategory.FIRST_SELECTED_EXPLORATORY_POLICY,
            "r1",
            replayed_after_failure_only=True,
        ).validate()
    with pytest.raises(ExploratorySearchError, match="manual replay"):
        ExploratoryResultRecord(1, ResultCategory.LATER_MANUAL_REPLAY, "r2").validate()
    ExploratoryResultRecord(
        1, ResultCategory.LATER_MANUAL_REPLAY, "r2", selected_before_result_known=False
    ).validate()


def test_selective_replay_of_failed_seeds_is_rejected() -> None:
    with pytest.raises(ExploratorySearchError, match="only failed seeds"):
        validate_replay_seed_set(
            planned_seeds=[1, 2, 3, 4], replayed_seeds=[2, 4], failed_seeds=[2, 4]
        )
    validate_replay_seed_set(
        planned_seeds=[1, 2, 3, 4], replayed_seeds=[1, 2, 3, 4], failed_seeds=[2, 4]
    )
