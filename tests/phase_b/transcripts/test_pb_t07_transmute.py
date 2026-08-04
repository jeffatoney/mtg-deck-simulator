from mtg_deck import build_exact_game
from mtg_kernel.models import Zone
from mtg_policy import ActionBroker
from mtg_verify.transcript_evidence import record_game_state_evidence
from tests.phase_b.transcripts.support import (
    PLAYERS,
    TutorOverrideProvider,
    move_named,
    pass_round,
    provider,
)


def test_pb_t07_transmute_resolution_evidence() -> None:
    state, executor, created = build_exact_game("golden-t07", PLAYERS)
    library = list(created["library"])
    dizzy = move_named(executor, library, "Dizzy Spell", Zone.HAND)
    executor.bind_strategic_choice_provider(TutorOverrideProvider(provider(), "Sol Ring"))
    state.turn.phase = "PRECOMBAT_MAIN"
    state.players["P0"].mana_pool.update({symbol: 0 for symbol in state.players["P0"].mana_pool})
    state.players["P0"].mana_pool["U"] = 2
    state.players["P0"].mana_pool["C"] = 1
    broker = ActionBroker(executor, "P0")
    observation, actions = broker.refresh()
    action = next(
        item for item in actions if item.kind == "ACTIVATE_HAND" and item.identity == "Dizzy Spell"
    )
    assert action.metadata["choice_timing"] == "RESOLUTION"
    broker.execute(int(observation["generation"]), action.handle)
    assert not any(choice.kind == "TRANSMUTE" for choice in state.choices)
    pass_round(executor)
    rings = [
        obj
        for obj in state.objects.values()
        if not obj.retired
        and obj.zone is Zone.HAND
        and obj.current_characteristics.get("name") == "Sol Ring"
    ]
    assert len(rings) == 1
    choice = next(item for item in state.choices if item.kind == "TRANSMUTE")
    assert choice.selected["identity"] == "Sol Ring"
    assert choice.selected["chosen_at"] == "RESOLUTION"
    assert dizzy.retired
    record_game_state_evidence(
        "PB-T07-tutor-one",
        state,
        facts={
            "activation_event_semantics": "ANNOUNCED_AND_STACKED_BEFORE_COST_EVENTS",
            "selected_identity": "Sol Ring",
        },
    )
