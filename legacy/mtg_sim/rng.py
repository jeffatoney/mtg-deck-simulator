"""Named deterministic random infrastructure."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import random
from typing import Sequence, TypeVar

T = TypeVar("T")
STREAMS = frozenset(
    {"library_shuffle", "mulligan_shuffle", "unknown_draw", "audit", "policy_tiebreak"}
)


@dataclass(frozen=True, slots=True)
class ScenarioSeed:
    base_seed: int

    def derive_int(self, stream: str, *parts: object) -> int:
        if stream not in STREAMS:
            raise ValueError(f"unknown deterministic RNG stream: {stream}")
        text = "|".join([str(self.base_seed), stream, *(str(p) for p in parts)])
        return int.from_bytes(hashlib.sha256(text.encode()).digest()[:8], "big")

    def rng(self, stream: str, *parts: object) -> random.Random:
        return random.Random(self.derive_int(stream, *parts))

    def shuffled(self, items: Sequence[T], stream: str, *parts: object) -> list[T]:
        result = list(items)
        self.rng(stream, *parts).shuffle(result)
        return result


def paired_shuffle_schedule(
    seed: ScenarioSeed, game_index: int, round_index: int, cards: Sequence[T]
) -> list[T]:
    """Shared per-round schedule for standard and exploratory policies."""
    return seed.shuffled(cards, "mulligan_shuffle", "paired", game_index, round_index)


def deterministic_fixture(
    seed: int, worker_count: int, fixture_index: int, cards: Sequence[T]
) -> list[T]:
    """Worker-count-independent fixture assignment keyed only by fixture index."""
    _ = worker_count
    return ScenarioSeed(seed).shuffled(cards, "library_shuffle", "fixture", fixture_index)
