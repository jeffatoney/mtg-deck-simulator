from __future__ import annotations

import pytest

from mtg_kernel.errors import UnsupportedCapability
from mtg_kernel.strategic_choices import OptionalTriggerRequest
from mtg_policy.choices import PolicyStrategicChoiceProvider
from mtg_policy.config import load_policy_matrix
from mtg_policy.evaluation import ContextualEvaluator, load_evaluator_config


def _provider() -> PolicyStrategicChoiceProvider:
    bundle = next(
        bundle for bundle in load_policy_matrix() if bundle.policy_config_id == "anchor_balanced"
    )
    return PolicyStrategicChoiceProvider(bundle, ContextualEvaluator(load_evaluator_config()))


def _request(ability_id: str, effect_kind: str) -> OptionalTriggerRequest:
    return OptionalTriggerRequest(
        request_id="optional-trigger-test",
        actor_id="P0",
        ability_id=ability_id,
        effect_kind=effect_kind,
        turn_number=1,
        observation={"generation": 1, "turn": {"number": 1}},
    )


def test_policy_takes_reviewed_curiosity_optional_draw() -> None:
    selection = _provider().choose_optional_trigger(_request("curiosity:damage", "DRAW"))

    assert selection.take is True
    assert selection.diagnostics["strategy"] == "TAKE_REVIEWED_OPTIONAL_TRIGGER"


def test_policy_fails_closed_on_unreviewed_optional_draw() -> None:
    with pytest.raises(UnsupportedCapability, match="future:optional-draw/DRAW"):
        _provider().choose_optional_trigger(_request("future:optional-draw", "DRAW"))
