"""Class invariants for live, explicit, and recorded-replay choice authority."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from mtg_kernel.errors import UnsupportedCapability
from mtg_kernel.strategic_choices import (
    RecordedStrategicChoiceProvider,
    StrategicChoiceBinding,
    explicit_action_choice_is_authorized,
    is_recorded_replay_provider,
    require_authorized_provider,
    require_executor_authorized_provider,
)


@dataclass
class _SpyProvider:
    calls: list[str]

    def choose_counter_payment(self, request: object) -> None:
        del request
        self.calls.append("counter")
        raise AssertionError("unbound live provider must not be invoked")


def test_explicit_action_choice_requires_matching_actor_and_owner() -> None:
    assert explicit_action_choice_is_authorized(
        decision_owner_id="P0",
        action_actor_id="P0",
    )
    assert not explicit_action_choice_is_authorized(
        decision_owner_id="P1",
        action_actor_id="P0",
    )
    assert not explicit_action_choice_is_authorized(
        decision_owner_id="P2",
        action_actor_id="P0",
    )


def test_live_unbound_provider_fails_closed_without_invocation() -> None:
    spy = _SpyProvider([])
    with pytest.raises(UnsupportedCapability, match="unmodeled opponent"):
        require_authorized_provider(
            spy,
            "counter-unless-pay payment",
            decision_owner_id="P1",
            binding=None,
            replaying=False,
        )
    assert spy.calls == []


def test_live_bound_provider_authorizes_only_the_bound_owner() -> None:
    spy = _SpyProvider([])
    binding = StrategicChoiceBinding(spy, "P0")
    assert (
        require_authorized_provider(
            spy,
            "counter-unless-pay payment",
            decision_owner_id="P0",
            binding=binding,
            replaying=False,
        )
        is spy
    )
    with pytest.raises(UnsupportedCapability, match="unmodeled opponent"):
        require_authorized_provider(
            spy,
            "counter-unless-pay payment",
            decision_owner_id="P1",
            binding=binding,
            replaying=False,
        )
    with pytest.raises(UnsupportedCapability, match="unmodeled opponent"):
        require_authorized_provider(
            spy,
            "counter-unless-pay payment",
            decision_owner_id="P2",
            binding=binding,
            replaying=False,
        )
    assert spy.calls == []


def test_recorded_replay_provider_is_authorized_without_live_binding() -> None:
    recorded = RecordedStrategicChoiceProvider([])
    assert is_recorded_replay_provider(recorded)
    assert not is_recorded_replay_provider(_SpyProvider([]))
    assert (
        require_authorized_provider(
            recorded,
            "counter-unless-pay payment",
            decision_owner_id="P1",
            binding=None,
            replaying=True,
        )
        is recorded
    )


def test_replay_mode_does_not_authorize_an_arbitrary_live_provider() -> None:
    spy = _SpyProvider([])
    with pytest.raises(UnsupportedCapability, match="unmodeled opponent"):
        require_authorized_provider(
            spy,
            "counter-unless-pay payment",
            decision_owner_id="P0",
            binding=None,
            replaying=True,
        )
    assert spy.calls == []


def test_executor_helper_threads_replay_flag_and_binding() -> None:
    spy = _SpyProvider([])
    binding = StrategicChoiceBinding(spy, "P1")

    class _Executor:
        strategic_choice_provider = spy
        strategic_choice_binding = binding
        replaying = False

    assert (
        require_executor_authorized_provider(
            _Executor(),
            "Prismari Command discard selection",
            decision_owner_id="P1",
        )
        is spy
    )

    class _UnboundLive:
        strategic_choice_provider = spy
        strategic_choice_binding = None
        replaying = False

    with pytest.raises(UnsupportedCapability, match="unmodeled opponent"):
        require_executor_authorized_provider(
            _UnboundLive(),
            "Demolition Field basic-land search resolution",
            decision_owner_id="P0",
        )
    assert spy.calls == []
