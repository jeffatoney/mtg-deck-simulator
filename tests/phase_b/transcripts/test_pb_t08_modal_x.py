import pytest

from mtg_kernel.errors import IllegalAction
from mtg_kernel.factory import add_card
from mtg_kernel.hashing import state_hash
from mtg_kernel.models import TargetRef, Zone
from mtg_kernel.phase_b_actions import foretell
from mtg_verify.transcript_evidence import record_game_state_evidence
from tests.phase_b.transcripts.support import funded_game


def test_pb_t08_modal_x_foretell_evidence() -> None:
    state, executor, specs = funded_game("golden-t08")
    creature = add_card(
        executor, specs["Malcolm, Keen-Eyed Navigator"], Zone.BATTLEFIELD, owner="P1"
    )
    artifact_a = add_card(executor, specs["Sol Ring"], Zone.BATTLEFIELD, owner="P1")
    artifact_b = add_card(executor, specs["Arcane Signet"], Zone.BATTLEFIELD, owner="P2")
    abrade = add_card(executor, specs["Abrade"], Zone.HAND)
    abrade_spell = executor.cast(
        "P0", abrade.object_id, (TargetRef(creature.object_id),), mode="damage"
    )
    assert executor._created_action(abrade_spell).modes == ("damage",)
    executor.counter(abrade_spell.object_id)
    by_force = add_card(executor, specs["By Force"], Zone.HAND)
    before = state_hash(state)
    with pytest.raises(IllegalAction, match="targets must equal"):
        executor.cast("P0", by_force.object_id, (TargetRef(artifact_a.object_id),), x_value=2)
    assert state_hash(state) == before
    x_spell = executor.cast(
        "P0",
        by_force.object_id,
        (TargetRef(artifact_a.object_id), TargetRef(artifact_b.object_id)),
        x_value=2,
    )
    x_action = executor._created_action(x_spell)
    assert x_action.x_value == 2 and x_action.payments["cost"]["GENERIC"] == 2
    executor.counter(x_spell.object_id)
    ravenform = add_card(executor, specs["Ravenform"], Zone.HAND)
    foretold = foretell(executor, "P0", ravenform.object_id, "ravenform:foretell")
    state.turn.number += 1
    state.players["P0"].mana_pool.update({symbol: 0 for symbol in ("W", "U", "B", "R", "G", "C")})
    state.players["P0"].mana_pool["U"] = 1
    alt_spell = executor.cast(
        "P0", foretold.object_id, (TargetRef(artifact_a.object_id),), mode="foretell"
    )
    alt_action = executor._created_action(alt_spell)
    assert alt_action.payments["cost"]["U"] == 1
    assert sum(alt_action.payments["cost"].values()) == 1
    record_game_state_evidence(
        "PB-T08-modal-x-alt",
        state,
        facts={"illegal_x_cast_rolled_back": True, "x_value": 2, "foretell_cast_payment": 1},
    )
