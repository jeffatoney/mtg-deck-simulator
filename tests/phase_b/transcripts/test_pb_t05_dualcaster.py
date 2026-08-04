from mtg_deck import build_exact_game
from mtg_kernel.models import CopyKind, TargetRef, Zone
from mtg_verify.transcript_evidence import record_game_state_evidence
from tests.phase_b.transcripts.support import LoopWitnessProvider, move_named, pass_round, provider


def test_pb_t05_dualcaster_twinflame_evidence() -> None:
    state, executor, created = build_exact_game("golden-t05", ("P0", "P1"))
    library = list(created["library"])
    executor.bind_strategic_choice_provider(LoopWitnessProvider(provider(), 2))
    state.turn.phase = "PRECOMBAT_MAIN"
    dualcaster = move_named(executor, library, "Dualcaster Mage", Zone.HAND)
    library = [obj for obj in library if not obj.retired]
    twinflame = move_named(executor, library, "Twinflame", Zone.HAND)
    malcolm = move_named(
        executor, list(created["command"]), "Malcolm, Keen-Eyed Navigator", Zone.BATTLEFIELD
    )
    state.players["P0"].mana_pool.update({symbol: 0 for symbol in state.players["P0"].mana_pool})
    state.players["P0"].mana_pool["R"] = 3
    state.players["P0"].mana_pool["C"] = 3
    original = executor.cast("P0", twinflame.object_id, (TargetRef(malcolm.object_id),))
    executor.cast(
        "P0",
        dualcaster.object_id,
        choices={"trigger_targets": {"dualcaster:etb": original.object_id}},
    )
    for _ in range(30):
        if not state.stack and not state.waiting_triggers:
            break
        pass_round(executor)
    else:
        raise AssertionError("bounded Dualcaster line did not terminate")
    tokens = [
        obj
        for obj in state.objects.values()
        if not obj.retired
        and obj.copy_kind is CopyKind.TOKEN_COPY
        and obj.current_characteristics.get("name") == "Dualcaster Mage"
    ]
    copies = [
        obj
        for obj in state.objects.values()
        if obj.copy_kind is CopyKind.SPELL_COPY
        and obj.current_characteristics.get("name") == "Twinflame"
    ]
    assert len(tokens) == 2
    assert copies and all(
        copy.was_cast is False and not copy.component_card_instance_ids for copy in copies
    )
    strategies = [
        choice.selected.get("diagnostics", {}).get("strategy")
        for choice in state.choices
        if choice.kind == "COPY_TARGETS" and isinstance(choice.selected, dict)
    ]
    assert "CONTINUE_BOUNDED_DUALCASTER_LOOP" in strategies
    assert "STOP_BOUNDED_DUALCASTER_LOOP" in strategies
    kinds = [event.kind for event in state.events]
    assert (
        kinds.index("COPY_TARGET_DECISION")
        < kinds.index("SPELL_COPIED")
        < kinds.index("TOKEN_COPY_CREATED")
    )
    record_game_state_evidence(
        "PB-T05-dualcaster-twinflame",
        state,
        facts={
            "token_dualcaster_count": 2,
            "copy_target_decision_precedes_copy": True,
            "canonical_policy_eligible": False,
        },
    )
