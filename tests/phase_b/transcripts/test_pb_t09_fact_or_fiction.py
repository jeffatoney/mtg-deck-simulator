from mtg_deck import build_exact_game
from mtg_kernel.models import Zone
from mtg_kernel.replay import transcript, validate_replay
from mtg_policy import (
    ContextualEvaluator,
    PolicyStrategicChoiceProvider,
    load_evaluator_config,
    load_policy_matrix,
)
from mtg_verify.transcript_evidence import record_game_state_evidence
from tests.phase_b.transcripts.support import PLAYERS, move_named, pass_round


def _provider() -> PolicyStrategicChoiceProvider:
    return PolicyStrategicChoiceProvider(
        load_policy_matrix()[0], ContextualEvaluator(load_evaluator_config())
    )


def test_pb_t09_fact_or_fiction_evidence() -> None:
    state, executor, created = build_exact_game("golden-t09", PLAYERS)
    library = list(created["library"])
    state.turn.number = 3
    state.turn.phase = "PRECOMBAT_MAIN"
    executor.bind_strategic_choice_provider(_provider())
    for _ in range(3):
        move_named(executor, library, "Island", Zone.BATTLEFIELD)
        library = [obj for obj in library if not obj.retired]
    fact = move_named(executor, library, "Fact or Fiction", Zone.HAND)
    library = [obj for obj in library if not obj.retired]
    move_named(executor, library, "Dualcaster Mage", Zone.HAND)
    library = [obj for obj in library if not obj.retired]
    reveal = []
    for name in ["Island", "Island", "Island", "Mountain", "Twinflame"]:
        obj = next(
            candidate
            for candidate in library
            if not candidate.retired and candidate.current_characteristics.get("name") == name
        )
        reveal.append(obj)
        library.remove(obj)
    revealed_instance_ids = {obj.component_card_instance_ids[0] for obj in reveal}
    assert len(revealed_instance_ids) == 5
    zone = state.zones[executor.zones.zone_key(Zone.LIBRARY, "P0")]
    for obj in reveal:
        zone.remove(obj.object_id)
    zone.extend(obj.object_id for obj in reversed(reveal))
    state.players["P0"].mana_pool.update({symbol: 0 for symbol in state.players["P0"].mana_pool})
    state.players["P0"].mana_pool["U"] = 1
    state.players["P0"].mana_pool["C"] = 3
    executor.cast("P0", fact.object_id)
    pass_round(executor)
    chosen = next(choice for choice in state.choices if choice.kind == "FACT_OR_FICTION_PILE")
    assert "Twinflame" in chosen.selected["cards"]
    resolved_revealed = [
        obj
        for obj in state.objects.values()
        if not obj.retired
        and obj.component_card_instance_ids
        and obj.component_card_instance_ids[0] in revealed_instance_ids
    ]
    assert len(resolved_revealed) == 5
    hand_cards = [obj for obj in resolved_revealed if obj.zone is Zone.HAND]
    graveyard_cards = [obj for obj in resolved_revealed if obj.zone is Zone.GRAVEYARD]
    assert len(hand_cards) + len(graveyard_cards) == 5
    assert hand_cards and graveyard_cards
    assert any(obj.current_characteristics.get("name") == "Twinflame" for obj in hand_cards)
    replayed = validate_replay(transcript(state, seed="golden-t09"))
    assert (
        next(
            choice for choice in replayed.choices if choice.kind == "FACT_OR_FICTION_PILE"
        ).selected
        == chosen.selected
    )
    record_game_state_evidence(
        "PB-T09-fact-min",
        state,
        facts={
            "twinflame_reached_hand": True,
            "revealed_cards_to_hand": len(hand_cards),
            "revealed_cards_to_graveyard": len(graveyard_cards),
            "fresh_replay_reproduced_selection": True,
            "test_fixture_uses_sol_ring": False,
        },
    )
