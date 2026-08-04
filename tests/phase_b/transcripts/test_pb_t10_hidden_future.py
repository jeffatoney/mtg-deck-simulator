import pytest

from mtg_policy.broker import ObservedAction
from mtg_search import BoundedExplorer, SearchEvaluation, SearchPosition
from mtg_verify.transcript_evidence import audit_event, record_audit_evidence


def _reject_hidden_field(field: str) -> str:
    action = ObservedAction("a", "TEST", None, 0, (), 0, {})
    with pytest.raises(ValueError, match="forbidden hidden field") as error:
        SearchPosition(
            {"generation": 1, "turn": {}, field: ["secret"]},
            (action,),
            SearchEvaluation(),
        )
    return str(error.value)


def test_pb_t10_hidden_future_evidence() -> None:
    library_error = _reject_hidden_field("library_order")
    future_event_error = _reject_hidden_field("future_events")
    future_random_error = _reject_hidden_field("future_random_outcomes")

    action = ObservedAction("a", "TEST", None, 0, (), 0, {})
    root = SearchPosition(
        {"generation": 1, "turn": {"number": 1}, "public_value": 0},
        (action,),
        SearchEvaluation(),
        0,
    )
    expansion_calls = 0

    def expand(parent, selected, seed):
        nonlocal expansion_calls
        expansion_calls += 1
        return SearchPosition(parent.observation, parent.actions, parent.evaluation, 1)

    with pytest.raises(ValueError, match="maximum of eight") as sample_error:
        BoundedExplorer().choose(
            root,
            belief_sample_seeds=tuple(range(9)),
            expand=expand,
        )
    assert expansion_calls == 0

    record_audit_evidence(
        "PB-T10-hidden-future",
        (
            audit_event("HIDDEN_LIBRARY_FIELD_REJECTED", reason=library_error),
            audit_event("FUTURE_EVENT_FIELD_REJECTED", reason=future_event_error),
            audit_event("FUTURE_RANDOM_OUTCOME_FIELD_REJECTED", reason=future_random_error),
            audit_event(
                "BELIEF_SAMPLE_CAP_REJECTED_BEFORE_EXPANSION",
                reason=str(sample_error.value),
                attempted=9,
                expansion_calls=expansion_calls,
            ),
        ),
        facts={
            "successful_sample_expansions": expansion_calls,
            "forbidden_fields_tested": [
                "library_order",
                "future_events",
                "future_random_outcomes",
            ],
        },
    )
