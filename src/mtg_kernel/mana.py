"""Deterministic mana-cost parsing and atomic payment for the Phase A card slice."""

from __future__ import annotations

import re
from collections.abc import Mapping

from mtg_kernel.errors import IllegalAction, UnsupportedCapability

COLORS = ("W", "U", "B", "R", "G", "C")
HYBRID_PREFIX = "HYBRID:"


def parse_mana_cost(cost: str, *, x_value: int = 0) -> dict[str, int]:
    parsed = {symbol: 0 for symbol in COLORS}
    parsed["GENERIC"] = 0
    for symbol in re.findall(r"\{([^}]+)\}", cost):
        if symbol.isdigit():
            parsed["GENERIC"] += int(symbol)
        elif symbol == "X":
            if x_value < 0:
                raise IllegalAction("X cannot be negative")
            parsed["GENERIC"] += x_value
        elif symbol in COLORS:
            parsed[symbol] += 1
        else:
            hybrid = tuple(symbol.split("/"))
            if len(hybrid) == 2 and hybrid[0] != hybrid[1] and all(
                option in COLORS for option in hybrid
            ):
                key = f"{HYBRID_PREFIX}{'/'.join(hybrid)}"
                parsed[key] = parsed.get(key, 0) + 1
            else:
                raise UnsupportedCapability(
                    f"unsupported mana symbol in Phase A cost: {{{symbol}}}"
                )
    return parsed


def combine_costs(*costs: Mapping[str, int]) -> dict[str, int]:
    total = {symbol: 0 for symbol in (*COLORS, "GENERIC")}
    for cost in costs:
        for symbol, amount in cost.items():
            total[symbol] = total.get(symbol, 0) + int(amount)
    return total


def multiply_cost(cost: Mapping[str, int], multiplier: int) -> dict[str, int]:
    if multiplier < 0:
        raise IllegalAction("cost multiplier cannot be negative")
    return {symbol: int(amount) * multiplier for symbol, amount in cost.items()}


def _pay_hybrid(
    working: dict[str, int],
    payment: dict[str, int],
    cost: Mapping[str, int],
) -> None:
    units: list[tuple[str, ...]] = []
    for key in sorted(cost):
        if not key.startswith(HYBRID_PREFIX):
            continue
        options = tuple(key.removeprefix(HYBRID_PREFIX).split("/"))
        amount = int(cost[key])
        if amount < 0 or len(options) != 2 or any(option not in COLORS for option in options):
            raise IllegalAction("invalid hybrid mana cost")
        units.extend(options for _ in range(amount))

    def assign(index: int) -> bool:
        if index == len(units):
            return True
        for symbol in units[index]:
            if working[symbol] <= 0:
                continue
            working[symbol] -= 1
            payment[symbol] += 1
            if assign(index + 1):
                return True
            payment[symbol] -= 1
            working[symbol] += 1
        return False

    if not assign(0):
        raise IllegalAction("insufficient mana for hybrid cost")


def pay_mana(pool: dict[str, int], cost: Mapping[str, int]) -> dict[str, int]:
    working = {symbol: int(pool.get(symbol, 0)) for symbol in COLORS}
    payment = {symbol: 0 for symbol in COLORS}
    for symbol in COLORS:
        required = int(cost.get(symbol, 0))
        if working[symbol] < required:
            raise IllegalAction(f"insufficient {symbol} mana")
        working[symbol] -= required
        payment[symbol] += required

    _pay_hybrid(working, payment, cost)

    generic = int(cost.get("GENERIC", 0))
    for symbol in ("C", "W", "U", "B", "R", "G"):
        amount = min(generic, working[symbol])
        working[symbol] -= amount
        payment[symbol] += amount
        generic -= amount
    if generic:
        raise IllegalAction("insufficient mana for generic cost")
    for symbol in COLORS:
        pool[symbol] = working[symbol]
    return {symbol: amount for symbol, amount in payment.items() if amount}


def add_mana(pool: dict[str, int], mana: Mapping[str, int]) -> None:
    for symbol, amount in mana.items():
        if symbol not in COLORS or int(amount) < 0:
            raise IllegalAction("invalid mana production")
        pool[symbol] = pool.get(symbol, 0) + int(amount)
