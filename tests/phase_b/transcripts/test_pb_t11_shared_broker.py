import pytest

from mtg_kernel.errors import IllegalAction
from mtg_kernel.factory import add_card
from mtg_kernel.models import Zone
from mtg_measure import DivergenceMeasurement
from mtg_policy import ActionBroker, StandardPolicy, load_policy_matrix
from mtg_search import BoundedExplorer, SearchEvaluation, SearchPosition
from mtg_verify.transcript_evidence import audit_event, record_audit_evidence
from tests.phase_b.transcripts.support import funded_game


def test_pb_t11_shared_broker_divergence_evidence() -> None:
    _state, executor, specs = funded_game("golden-t11")
    add_card(executor, specs["Island"], Zone.HAND)
    add_card(executor, specs["Sol Ring"], Zone.HAND)
    broker = ActionBroker(executor, "P0")
    observation, actions = broker.refresh()
    generation = int(observation["generation"])
    handles = {action.handle for action in actions}
    standard = StandardPolicy(load_policy_matrix()[0]).select_action(observation, actions)
    root = SearchPosition(observation, actions, SearchEvaluation(), 0)

    def expand(parent: SearchPosition, action, seed: int) -> SearchPosition:
        prefers_ring = action.kind == "CAST" and action.identity == "Sol Ring"
        return SearchPosition(
            {"generation": 2, "turn": {"number": 1}, "sample": seed},
            (),
            SearchEvaluation(net_usable_mana=2 if prefers_ring else 0),
            parent.player_turns_elapsed + 1,
        )

    exploratory = BoundedExplorer().choose(root, belief_sample_seeds=(101, 102), expand=expand)
    assert standard in handles and exploratory.selected_action in handles
    assert standard != exploratory.selected_action
    standard_action = next(action for action in actions if action.handle == standard)
    exploratory_action = next(
        action for action in actions if action.handle == exploratory.selected_action
    )
    assert standard_action.kind == "PLAY_LAND"
    assert exploratory_action.kind == "CAST" and exploratory_action.identity == "Sol Ring"
    divergence = DivergenceMeasurement(
        paired_seed=101,
        standard_result=f"{standard_action.kind}:{standard_action.identity}",
        exploratory_result=f"{exploratory_action.kind}:{exploratory_action.identity}",
        first_decision_divergence=(
            f"{standard_action.kind}:{standard_action.identity} -> "
            f"{exploratory_action.kind}:{exploratory_action.identity}"
        ),
        visible_information=observation,
        win_turn_change=None,
        narrow_condition=False,
        branches_searched=exploratory.log.branches_searched,
        nodes_evaluated=exploratory.log.nodes_evaluated,
        depth_reached=exploratory.log.depth_reached,
        selected_before_future_draws=True,
    )
    refreshed, _ = broker.refresh()
    assert int(refreshed["generation"]) > generation
    with pytest.raises(IllegalAction, match="revoked") as stale_error:
        broker.execute(generation, standard)
    record_audit_evidence(
        "PB-T11-shared-broker",
        (
            audit_event(
                "BROKER_ACTION_SET_VALIDATED", generation=generation, action_count=len(actions)
            ),
            audit_event("STANDARD_SELECTION_VALIDATED", handle=standard),
            audit_event(
                "EXPLORATORY_SELECTION_VALIDATED",
                handle=exploratory.selected_action,
                evaluation_fixture="SOL_RING_NET_USABLE_MANA_TWO",
            ),
            audit_event(
                "FIRST_DIVERGENCE_RECORDED",
                description=divergence.first_decision_divergence,
            ),
            audit_event("STALE_BROKER_HANDLE_REJECTED", reason=str(stale_error.value)),
        ),
        facts={"divergence_is_fixture_driven": True, "shared_handle_count": len(handles)},
    )
