from mtg_kernel.factory import add_card
from mtg_kernel.models import Zone
from mtg_verify.transcript_evidence import record_game_state_evidence
from tests.phase_b.transcripts.support import funded_game, pass_round


def test_pb_t03_malcolm_opponent_set_evidence() -> None:
    state, executor, specs = funded_game("golden-t03")
    add_card(executor, specs["Island"], Zone.LIBRARY)
    malcolm = add_card(executor, specs["Malcolm, Keen-Eyed Navigator"], Zone.BATTLEFIELD)
    glint = add_card(executor, specs["Glint-Horn Buccaneer"], Zone.BATTLEFIELD)
    glint.current_characteristics["attacking"] = True
    discarded = add_card(executor, specs["Opt"], Zone.HAND)
    executor.activate(
        "P0", glint.object_id, "glint-horn:loot", choices={"discard_ids": [discarded.object_id]}
    )
    pass_round(executor)
    trigger = next(
        obj
        for obj in state.objects.values()
        if not obj.retired
        and obj.current_characteristics.get("ability", {}).get("ability_id")
        == "malcolm:pirate-damage"
    )
    assert set(trigger.current_characteristics["trigger_context"]["opponents"]) == {
        "P1",
        "P2",
        "P3",
    }
    pass_round(executor)
    treasures = [
        obj
        for obj in state.objects.values()
        if not obj.retired
        and obj.zone is Zone.BATTLEFIELD
        and obj.current_characteristics.get("name") == "Treasure"
    ]
    assert len(treasures) == 3 and malcolm.zone is Zone.BATTLEFIELD
    pass_round(executor)
    kinds = [event.kind for event in state.events]
    assert kinds.index("TREASURE_CREATED") < kinds.index("CARD_DRAWN")
    record_game_state_evidence(
        "PB-T03-malcolm-opponents",
        state,
        facts={"damaged_opponents": ["P1", "P2", "P3"], "treasure_count": 3},
    )
