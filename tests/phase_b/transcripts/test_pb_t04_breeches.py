from mtg_kernel.factory import add_card
from mtg_kernel.models import Zone
from mtg_verify.transcript_evidence import record_game_state_evidence
from tests.phase_b.transcripts.support import funded_game, pass_round


def test_pb_t04_breeches_boundary_evidence() -> None:
    state, executor, specs = funded_game("golden-t04")
    breeches = add_card(executor, specs["Breeches, Brazen Plunderer"], Zone.BATTLEFIELD)
    pirate = add_card(executor, specs["Malcolm, Keen-Eyed Navigator"], Zone.BATTLEFIELD)
    executor.deal_damage_to_player(pirate.object_id, "P1", 1, combat=True)
    while state.stack and state.terminal.status == "ACTIVE":
        pass_round(executor)
    record = next(choice for choice in state.choices if choice.kind == "BREECHES_UNKNOWN_EXCLUSION")
    assert record.selected == {
        "opponents": ["P1"],
        "deterministic_resources_added": 0,
        "hidden_identities_exposed": False,
    }
    assert not any(obj.zone is Zone.EXILE for obj in state.objects.values() if not obj.retired)
    assert breeches.zone is Zone.BATTLEFIELD
    record_game_state_evidence(
        "PB-T04-breeches-unknown",
        state,
        facts={
            "modeled_opponent_library_objects": 0,
            "local_exile_objects_added": 0,
            "deterministic_resources_added": 0,
        },
    )
