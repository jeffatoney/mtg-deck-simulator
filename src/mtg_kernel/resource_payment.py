"""Authoritative card-agnostic ordered mana/resource feasibility solver."""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Iterable, Sequence

from mtg_kernel.errors import IllegalAction, UnsupportedCapability
from mtg_kernel.mana import COLORS, HYBRID_PREFIX, parse_mana_cost

_ORDER = {c: i for i, c in enumerate(COLORS)}
INSUFFICIENT_TOTAL_CAPACITY = "INSUFFICIENT_TOTAL_CAPACITY"
RED_PIP_DEFICIT = "RED_PIP_DEFICIT"
BLUE_PIP_DEFICIT = "BLUE_PIP_DEFICIT"
COLORLESS_REQUIREMENT_DEFICIT = "COLORLESS_REQUIREMENT_DEFICIT"
RESOURCE_EXPIRES_BEFORE_STEP = "RESOURCE_EXPIRES_BEFORE_STEP"
RESOURCE_NOT_AVAILABLE_IN_WINDOW = "RESOURCE_NOT_AVAILABLE_IN_WINDOW"
SOURCE_REUSED_ACROSS_COSTS = "SOURCE_REUSED_ACROSS_COSTS"
RESTRICTED_MANA_NOT_APPLICABLE = "RESTRICTED_MANA_NOT_APPLICABLE"
PERSISTENT_RESOURCE_REQUIRED = "PERSISTENT_RESOURCE_REQUIRED"


@dataclass(frozen=True, order=True)
class ManaProduction:
    mana: tuple[tuple[str, int], ...]
    spend_tags: tuple[str, ...] = ()
    activation_cost: str = ""

    def __post_init__(self) -> None:
        mana = tuple(sorted(((str(c), int(n)) for c, n in self.mana), key=lambda x: _ORDER[x[0]]))
        if not mana or any(c not in COLORS or n <= 0 for c, n in mana):
            raise IllegalAction("resource production must contain positive supported mana")
        object.__setattr__(self, "mana", mana)
        object.__setattr__(self, "spend_tags", tuple(sorted({str(x) for x in self.spend_tags})))
        parse_mana_cost(self.activation_cost)


@dataclass(frozen=True)
class ResourceSource:
    semantic_id: str
    productions: tuple[ManaProduction, ...]
    count: int = 1
    activation_cost: str = ""
    tap_to_activate: bool = False
    sacrifice_to_activate: bool = False
    persistent: bool = True
    tapped: bool = False
    enters_tapped: bool = False
    available_from_window: int = 0
    available_through_window: int | None = None
    execution_refs: tuple[str, ...] = field(default=(), compare=False, repr=False)

    def __post_init__(self) -> None:
        if not self.semantic_id or self.count <= 0 or not self.productions:
            raise IllegalAction("invalid resource source")
        if self.available_from_window < 0 or (
            self.available_through_window is not None
            and self.available_through_window < self.available_from_window
        ):
            raise IllegalAction("invalid resource availability window")
        object.__setattr__(self, "productions", tuple(sorted(set(self.productions))))
        parse_mana_cost(self.activation_cost)


@dataclass(frozen=True, order=True)
class FloatingMana:
    color: str
    amount: int = 1
    semantic_id: str = "floating"
    spend_tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.color not in COLORS or self.amount <= 0:
            raise IllegalAction("invalid floating mana")
        object.__setattr__(self, "spend_tags", tuple(sorted({str(x) for x in self.spend_tags})))


@dataclass(frozen=True, order=True)
class PaymentWindow:
    ordinal: int
    label: str
    clear_pool_before: bool = False
    untap_before: bool = False

    def __post_init__(self) -> None:
        if self.ordinal < 0 or not self.label:
            raise IllegalAction("invalid payment window")


@dataclass(frozen=True)
class PaymentStep:
    label: str
    mana_cost: str
    window: PaymentWindow
    context_tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.label:
            raise IllegalAction("payment step requires a label")
        object.__setattr__(self, "context_tags", tuple(sorted({str(x) for x in self.context_tags})))
        parse_mana_cost(self.mana_cost)


@dataclass(frozen=True, order=True)
class PaymentAllocation:
    step_label: str
    source_semantic_id: str
    color: str
    requirement: str
    amount: int = 1


@dataclass(frozen=True, order=True)
class PaymentStepResult:
    label: str
    window_label: str
    mana_cost: str
    allocation: tuple[PaymentAllocation, ...]


@dataclass(frozen=True, order=True)
class SourceCapacity:
    source_semantic_id: str
    remaining: int
    unavailable: int


@dataclass(frozen=True)
class ResourcePaymentResult:
    feasible: bool
    ordered_payment_steps: tuple[PaymentStepResult, ...]
    canonical_allocation: tuple[PaymentAllocation, ...]
    first_failed_step: str | None
    remaining_source_capacity: tuple[SourceCapacity, ...]
    colored_pip_deficits: tuple[tuple[str, int], ...]
    colorless_deficit: int
    generic_deficit: int
    reason_codes: tuple[str, ...]
    assumptions: tuple[str, ...]
    windows: tuple[PaymentWindow, ...]
    remaining_mana: tuple[tuple[str, int], ...]


@dataclass(frozen=True, order=True)
class _Atom:
    color: str
    source: str
    tags: tuple[str, ...] = ()


@dataclass(frozen=True, order=True)
class _Req:
    name: str
    options: tuple[str, ...]


@dataclass(frozen=True)
class _Cap:
    remaining: int
    unavailable: int


@dataclass(frozen=True)
class _State:
    pool: tuple[_Atom, ...]
    caps: tuple[_Cap, ...]
    window: int | None


@dataclass(frozen=True)
class _Solution:
    state: _State
    steps: tuple[PaymentStepResult, ...]
    allocations: tuple[PaymentAllocation, ...]


def _source_key(s: ResourceSource) -> tuple[object, ...]:
    return (
        s.semantic_id,
        s.productions,
        s.activation_cost,
        s.tap_to_activate,
        s.sacrifice_to_activate,
        s.persistent,
        s.tapped,
        s.enters_tapped,
        s.available_from_window,
        s.available_through_window if s.available_through_window is not None else 10**9,
    )


def _normalize(sources: Sequence[ResourceSource]) -> tuple[ResourceSource, ...]:
    grouped: dict[tuple[object, ...], tuple[ResourceSource, int]] = {}
    for s in sources:
        key = _source_key(s)
        old = grouped.get(key)
        grouped[key] = (s, s.count + (old[1] if old else 0))
    return tuple(
        ResourceSource(
            semantic_id=s.semantic_id,
            productions=s.productions,
            count=count,
            activation_cost=s.activation_cost,
            tap_to_activate=s.tap_to_activate,
            sacrifice_to_activate=s.sacrifice_to_activate,
            persistent=s.persistent,
            tapped=s.tapped,
            enters_tapped=s.enters_tapped,
            available_from_window=s.available_from_window,
            available_through_window=s.available_through_window,
        )
        for s, count in (grouped[key] for key in sorted(grouped))
    )


def _reqs(cost: str) -> tuple[_Req, ...]:
    parsed = parse_mana_cost(cost)
    out: list[_Req] = []
    for color in COLORS:
        out.extend(
            _Req(f"{color}:{i}", (color,))
            for i in range(int(parsed.get(color, 0)))
        )
    for key in sorted(k for k in parsed if k.startswith(HYBRID_PREFIX)):
        opts = tuple(
            sorted(key.removeprefix(HYBRID_PREFIX).split("/"), key=_ORDER.__getitem__)
        )
        out.extend(_Req(f"{key}:{i}", opts) for i in range(int(parsed[key])))
    out.extend(
        _Req(f"GENERIC:{i}", tuple(COLORS)) for i in range(int(parsed["GENERIC"]))
    )
    return tuple(out)


def _initial(
    sources: tuple[ResourceSource, ...], floating: Sequence[FloatingMana]
) -> _State:
    atoms = tuple(
        sorted(
            _Atom(f.color, f.semantic_id, f.spend_tags)
            for f in sorted(floating)
            for _ in range(f.amount)
        )
    )
    caps = tuple(
        _Cap(s.count, s.count if s.tapped or s.enters_tapped else 0)
        for s in sources
    )
    return _State(atoms, caps, None)


def _window(
    state: _State, win: PaymentWindow, sources: tuple[ResourceSource, ...]
) -> _State:
    if state.window == win.ordinal:
        return state
    if state.window is not None and win.ordinal < state.window:
        raise IllegalAction("payment windows must be ordered")
    caps = list(state.caps)
    if win.untap_before:
        for i, source in enumerate(sources):
            if source.persistent and not source.sacrifice_to_activate:
                caps[i] = _Cap(caps[i].remaining, 0)
    return _State(() if win.clear_pool_before else state.pool, tuple(caps), win.ordinal)


def _available(source: ResourceSource, cap: _Cap, win: PaymentWindow) -> bool:
    return (
        win.ordinal >= source.available_from_window
        and (
            source.available_through_window is None
            or win.ordinal <= source.available_through_window
        )
        and cap.remaining > cap.unavailable
    )


def _helpful(
    prod: ManaProduction, reqs: tuple[_Req, ...], tags: tuple[str, ...]
) -> bool:
    return set(prod.spend_tags).issubset(tags) and any(
        color in req.options for color, _ in prod.mana for req in reqs
    )


def _consume(state: _State, i: int, source: ResourceSource) -> _State:
    caps = list(state.caps)
    cap = caps[i]
    caps[i] = (
        _Cap(cap.remaining - 1, cap.unavailable)
        if source.sacrifice_to_activate
        else _Cap(cap.remaining, cap.unavailable + 1)
    )
    return _State(state.pool, tuple(caps), state.window)


def _produce(state: _State, source: ResourceSource, prod: ManaProduction) -> _State:
    pool = list(state.pool)
    for color, amount in prod.mana:
        pool.extend(
            _Atom(color, source.semantic_id, prod.spend_tags) for _ in range(amount)
        )
    return _State(tuple(sorted(pool)), state.caps, state.window)


def _pay(
    state: _State,
    reqs: tuple[_Req, ...],
    *,
    label: str,
    tags: tuple[str, ...],
    win: PaymentWindow,
    sources: tuple[ResourceSource, ...],
    seen: set[tuple[object, ...]],
) -> Iterable[tuple[_State, tuple[PaymentAllocation, ...]]]:
    if not reqs:
        yield state, ()
        return
    key = (state, reqs, label, tags, win.ordinal)
    if key in seen:
        return
    seen.add(key)
    req, rest = reqs[0], reqs[1:]
    used_atoms: set[_Atom] = set()
    for i, atom in enumerate(state.pool):
        if (
            atom in used_atoms
            or atom.color not in req.options
            or not set(atom.tags).issubset(tags)
        ):
            continue
        used_atoms.add(atom)
        pool = list(state.pool)
        pool.pop(i)
        nxt = _State(tuple(pool), state.caps, state.window)
        alloc = PaymentAllocation(label, atom.source, atom.color, req.name)
        for end, tail in _pay(
            nxt,
            rest,
            label=label,
            tags=tags,
            win=win,
            sources=sources,
            seen=seen,
        ):
            yield end, (alloc, *tail)
    for i, source in enumerate(sources):
        if not _available(source, state.caps[i], win):
            continue
        for prod in source.productions:
            if not _helpful(prod, reqs, tags):
                continue
            consumed = _consume(state, i, source)
            act_cost = prod.activation_cost or source.activation_cost
            act_reqs = _reqs(act_cost)
            act_label = f"{label}:source:{source.semantic_id}"
            paths: Iterable[tuple[_State, tuple[PaymentAllocation, ...]]]
            paths = _pay(
                consumed,
                act_reqs,
                label=act_label,
                tags=("ACTIVATED_ABILITY", "MANA_ABILITY"),
                win=win,
                sources=sources,
                seen=seen,
            ) if act_reqs else ((consumed, ()),)
            for paid, act_alloc in paths:
                produced = _produce(paid, source, prod)
                for end, tail in _pay(
                    produced,
                    reqs,
                    label=label,
                    tags=tags,
                    win=win,
                    sources=sources,
                    seen=seen,
                ):
                    yield end, (*act_alloc, *tail)


def _canon(
    items: Sequence[PaymentAllocation], steps: Sequence[PaymentStep]
) -> tuple[PaymentAllocation, ...]:
    order = {s.label: i for i, s in enumerate(steps)}
    counts: dict[tuple[str, str, str, str], int] = {}
    for a in items:
        key = (a.step_label, a.source_semantic_id, a.color, a.requirement)
        counts[key] = counts.get(key, 0) + a.amount
    out = [PaymentAllocation(*key, n) for key, n in counts.items()]
    out.sort(
        key=lambda a: (
            order.get(a.step_label.split(":source:", 1)[0], 10**9),
            a.step_label,
            a.requirement,
            a.source_semantic_id,
            _ORDER[a.color],
        )
    )
    return tuple(out)


def _solve(
    sources: tuple[ResourceSource, ...],
    steps: tuple[PaymentStep, ...],
    floating: tuple[FloatingMana, ...],
) -> _Solution | None:
    @lru_cache(maxsize=None)
    def search(i: int, state: _State) -> _Solution | None:
        if i == len(steps):
            return _Solution(state, (), ())
        step = steps[i]
        state = _window(state, step.window, sources)
        candidates = list(
            _pay(
                state,
                _reqs(step.mana_cost),
                label=step.label,
                tags=step.context_tags,
                win=step.window,
                sources=sources,
                seen=set(),
            )
        )
        candidates.sort(key=lambda x: (_canon(x[1], (step,)), x[0].pool, x[0].caps))
        for paid, alloc in candidates:
            tail = search(i + 1, paid)
            if tail is not None:
                canonical = _canon(alloc, (step,))
                public = tuple(a for a in canonical if ":source:" not in a.step_label)
                result = PaymentStepResult(step.label, step.window.label, step.mana_cost, public)
                return _Solution(
                    tail.state, (result, *tail.steps), (*canonical, *tail.allocations)
                )
        return None
    return search(0, _initial(sources, floating))


def _capacity(sources: tuple[ResourceSource, ...], state: _State) -> tuple[SourceCapacity, ...]:
    return tuple(
        SourceCapacity(s.semantic_id, c.remaining, c.unavailable)
        for s, c in zip(sources, state.caps, strict=True)
    )


def _remaining(state: _State) -> tuple[tuple[str, int], ...]:
    counts = {c: 0 for c in COLORS}
    for atom in state.pool:
        counts[atom.color] += 1
    return tuple((c, counts[c]) for c in COLORS if counts[c])


def _diagnose(
    sources: tuple[ResourceSource, ...],
    state: _State,
    step: PaymentStep,
    floating: tuple[FloatingMana, ...],
) -> tuple[tuple[tuple[str, int], ...], int, int, tuple[str, ...]]:
    parsed = parse_mana_cost(step.mana_cost)
    potential = {c: 0 for c in COLORS}
    for atom in state.pool:
        if set(atom.tags).issubset(step.context_tags):
            potential[atom.color] += 1
    for source, cap in zip(sources, state.caps, strict=True):
        if not _available(source, cap, step.window):
            continue
        count = cap.remaining - cap.unavailable
        for color in COLORS:
            if any(
                any(produced == color for produced, _ in production.mana)
                and set(production.spend_tags).issubset(step.context_tags)
                for production in source.productions
            ):
                potential[color] += count

    colored: list[tuple[str, int]] = []
    reasons: set[str] = set()
    for color in "WUBRG":
        deficit = max(0, int(parsed.get(color, 0)) - potential[color])
        if deficit:
            colored.append((color, deficit))
            reasons.add(
                {"R": RED_PIP_DEFICIT, "U": BLUE_PIP_DEFICIT}.get(
                    color, f"{color}_PIP_DEFICIT"
                )
            )
    colorless = max(0, int(parsed.get("C", 0)) - potential["C"])
    if colorless:
        reasons.add(COLORLESS_REQUIREMENT_DEFICIT)

    required = sum(
        int(value)
        for key, value in parsed.items()
        if not key.startswith(HYBRID_PREFIX)
    ) + sum(
        int(value)
        for key, value in parsed.items()
        if key.startswith(HYBRID_PREFIX)
    )
    available = len(state.pool) + sum(
        (cap.remaining - cap.unavailable)
        * max(sum(amount for _, amount in production.mana) for production in source.productions)
        for source, cap in zip(sources, state.caps, strict=True)
        if _available(source, cap, step.window)
    )
    fixed = required - int(parsed.get("GENERIC", 0))
    generic = max(0, int(parsed.get("GENERIC", 0)) - max(0, available - fixed))
    if available < required:
        reasons.add(INSUFFICIENT_TOTAL_CAPACITY)
    if step.window.clear_pool_before and floating:
        reasons.add(RESOURCE_EXPIRES_BEFORE_STEP)

    needs = _reqs(step.mana_cost)
    if any(
        source.available_from_window > step.window.ordinal
        and any(_helpful(production, needs, step.context_tags) for production in source.productions)
        for source in sources
    ):
        reasons.add(RESOURCE_NOT_AVAILABLE_IN_WINDOW)
    if any(
        (cap.unavailable or cap.remaining < source.count)
        and any(
            any(produced in req.options for produced, _ in production.mana)
            for production in source.productions
            for req in needs
        )
        for source, cap in zip(sources, state.caps, strict=True)
    ):
        reasons.add(SOURCE_REUSED_ACROSS_COSTS)
    if any(
        _available(source, cap, step.window)
        and any(
            production.spend_tags
            and not set(production.spend_tags).issubset(step.context_tags)
            for production in source.productions
        )
        for source, cap in zip(sources, state.caps, strict=True)
    ):
        reasons.add(RESTRICTED_MANA_NOT_APPLICABLE)
    if any(
        not source.persistent and (cap.unavailable or cap.remaining < source.count)
        for source, cap in zip(sources, state.caps, strict=True)
    ):
        reasons.add(PERSISTENT_RESOURCE_REQUIRED)
    if not reasons:
        reasons.add(INSUFFICIENT_TOTAL_CAPACITY)
    return tuple(colored), colorless, generic, tuple(sorted(reasons))


def solve_resource_payment(
    sources: Sequence[ResourceSource],
    steps: Sequence[PaymentStep],
    *,
    floating_mana: Sequence[FloatingMana] = (),
    assumptions: Sequence[str] = (),
) -> ResourcePaymentResult:
    sources = _normalize(tuple(sources))
    steps = tuple(steps)
    floating = tuple(sorted(floating_mana))
    if any(
        second.window.ordinal < first.window.ordinal
        for first, second in zip(steps, steps[1:])
    ):
        raise IllegalAction("payment step windows must be nondecreasing")
    windows = tuple(dict.fromkeys(step.window for step in steps))
    safe = tuple(
        sorted(
            str(value)
            for value in assumptions
            if not str(value).startswith("library-order:")
        )
    )
    solved = _solve(sources, steps, floating)
    if solved is not None:
        return ResourcePaymentResult(
            True,
            solved.steps,
            _canon(solved.allocations, steps),
            None,
            _capacity(sources, solved.state),
            (),
            0,
            0,
            (),
            safe,
            windows,
            _remaining(solved.state),
        )

    prefix = _Solution(_initial(sources, floating), (), ())
    failed: PaymentStep | None = None
    for index, step in enumerate(steps):
        candidate = _solve(sources, steps[: index + 1], floating)
        if candidate is None:
            failed = step
            break
        prefix = candidate
    if failed is None:
        raise UnsupportedCapability("resource payment failed without identifiable step")
    state = _window(prefix.state, failed.window, sources)
    colored, colorless, generic, reasons = _diagnose(sources, state, failed, floating)
    return ResourcePaymentResult(
        False,
        prefix.steps,
        _canon(prefix.allocations, steps[: len(prefix.steps)]),
        failed.label,
        _capacity(sources, state),
        colored,
        colorless,
        generic,
        reasons,
        safe,
        windows,
        _remaining(state),
    )
