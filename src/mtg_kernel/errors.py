"""Fail-closed clean-engine errors."""


class RulesError(RuntimeError):
    """Base rules-kernel failure."""


class IllegalAction(RulesError):
    """An action is illegal and no state may be changed."""


class UnsupportedCapability(RulesError):
    """A rules capability is explicitly outside the approved scope."""


class ReplayError(RulesError):
    """A replay transcript is incomplete, altered, or incompatible."""
