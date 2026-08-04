import pytest

from mtg_kernel.errors import IllegalAction
from mtg_kernel.factory import add_card
from mtg_kernel.hashing import state_hash
from mtg_kernel.models import TargetRef, Zone
from mtg_verify.transcript_evidence import record_game_state_evidence
from tests.phase_b.transcripts.support import funded_game, pass_round


def test_pb_t06_glint_curiosity_terminal_evidence() -> None:
    state, executor, specs = funded_game("golden-t06")
    for opponent in ("P1", "P2", "P3"):
        state.players[opponent].life = 1
    add_card(executor, specs["Island"], Zone.LIBRARY)
    glint = add_card(executor, specs["Glint-Horn Buccaneer"], Zone.BATTLEFIELD)
    curiosity = add_card(executor, specs["Curiosity"], Zone.HAND)
    executor.cast("P0", curiosity.object_id, (TargetRef(glint.object_id),))
    pass_round(executor)
    glint.current_characteristics["attacking"] = True
    discarded = add_card(executor, specs["Opt"], Zone.HAND)
    executor.activate(
        "P0", glint.object_id, "glint-horn:loot", choices={"discard_ids": [discarded.object_id]}
    )
    activated_id, damage_trigger_id = state.stack
    pass_round(executor)
    assert state.terminal.status == "TERMINAL"
    assert state.stack == [activated_id]
    assert not state.waiting_triggers
    assert all(not state.players[player].in_game for player in ("P1", "P2", "P3"))
    resolved = next(
        index
        for index, event in enumerate(state.events)
        if event.kind == "STACK_OBJECT_RESOLVED"
        and event.payload.get("object_id") == damage_trigger_id
    )
    terminal = next(
        index for index, event in enumerate(state.events) if event.kind == "GAME_TERMINATED"
    )
    assert resolved < terminal == len(state.events) - 1
    curiosity_triggers = [
        event
        for event in state.events
        if event.kind == "ABILITY_TRIGGERED"
        and event.payload.get("ability_id") == "curiosity:damage"
    ]
    assert len(curiosity_triggers) == 3
    assert any(event.kind == "SBA_SYNTHETIC_CEASE" for event in state.events)
    assert any(event.kind == "SYNTHETIC_OBJECT_CEASED" for event in state.events)
    assert not any(event.kind == "CARD_DRAWN" for event in state.events)

    negative_state, negative_executor, negative_specs = funded_game(
        "golden-t06-not-attacking", ("P0", "P1")
    )
    negative_glint = add_card(
        negative_executor, negative_specs["Glint-Horn Buccaneer"], Zone.BATTLEFIELD
    )
    negative_discard = add_card(negative_executor, negative_specs["Opt"], Zone.HAND)
    before = state_hash(negative_state)
    with pytest.raises(IllegalAction, match="only while the source attacks"):
        negative_executor.activate(
            "P0",
            negative_glint.object_id,
            "glint-horn:loot",
            choices={"discard_ids": [negative_discard.object_id]},
        )
    assert state_hash(negative_state) == before
    record_game_state_evidence(
        "PB-T06-glint-curiosity-terminal",
        state,
        facts={
            "curiosity_trigger_count": 3,
            "nonattacking_activation_rejected": True,
            "post_terminal_draw_count": 0,
        },
    )
