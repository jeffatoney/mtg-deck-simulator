import pytest

from mtg_policy.broker import ObservedAction
from mtg_search import BoundedExplorer, SearchEvaluation, SearchPosition
from mtg_verify.transcript_evidence import audit_event, record_audit_evidence


def test_pb_t10_hidden_future_evidence() -> None:
    action = ObservedAction("a", "TEST", None, 0, (), 0, {})
    with pytest.raises(ValueError, match="forbidden hidden field") as hidden_error:
        SearchPosition(
            {"generation": 1, "turn": {}, "library_order": ["A"]},
            (action,),
            SearchEvaluation(),
        )
    root = SearchPosition(
        {"generation": 1, "turn": {"number": 1}, "public_value": 0},
        (action,),
        SearchEvaluation(),
        0,
    )
    with pytest.raises(ValueError, match="maximum of eight") as sample_error:
        BoundedExplorer().choose(
            root,
            belief_sample_seeds=tuple(range(9)),
            expand=lambda parent, selected, seed: SearchPosition(
                parent.observation, parent.actions, parent.evaluation, 1
            ),
        )
    record_audit_evidence(
        "PB-T10-hidden-future",
        (
            audit_event("HIDDEN_FIELD_REJECTED", reason=str(hidden_error.value)),
            audit_event("BELIEF_SAMPLE_CAP_REJECTED", reason=str(sample_error.value), attempted=9),
        ),
        facts={"successful_samples_claimed": 0, "post_result_replay_attempted": False},
    )
