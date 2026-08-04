from collections import Counter

from mtg_deck import build_exact_game
from mtg_verify.transcript_evidence import audit_event, record_audit_evidence


def test_pb_t01_exact_deck_evidence() -> None:
    state, _, objects = build_exact_game("golden-t01")
    assert len(objects["library"]) == 98
    assert len(objects["command"]) == 2
    assert len(state.card_instances) == len(state.deck_slots) == 100
    assert len(set(state.card_instances)) == 100
    active = [obj for obj in state.objects.values() if not obj.retired and not obj.ceased_to_exist]
    assert len(active) == 100 == len({obj.object_id for obj in active})
    assert all(len(obj.component_card_instance_ids) == 1 for obj in active)
    assert {obj.component_card_instance_ids[0] for obj in active} == set(state.card_instances)
    names = Counter(obj.current_characteristics["name"] for obj in objects["library"])
    assert names["Island"] == 12 and names["Mountain"] == 10
    commanders = sorted(obj.current_characteristics["name"] for obj in objects["command"])
    assert commanders == ["Breeches, Brazen Plunderer", "Malcolm, Keen-Eyed Navigator"]
    record_audit_evidence(
        "PB-T01-exact-deck",
        (
            audit_event("DECK_PACKAGE_VALIDATED", library_count=98, command_count=2),
            audit_event("CARD_INSTANCE_IDENTIFIERS_VALIDATED", count=100),
            audit_event("ACTIVE_OBJECT_IDENTIFIERS_VALIDATED", count=100),
            audit_event("COMMAND_ZONE_ASSIGNMENTS_VALIDATED", commanders=commanders),
        ),
        facts={"island_count": 12, "mountain_count": 10},
    )
