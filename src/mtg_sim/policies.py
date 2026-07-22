"""Phase 7 candidate-policy framework.

This module freezes policy choices as data and evaluates policy decisions from
:class:`mtg_sim.domain.Observation` only. It does not run policy discovery,
pilot games, or inspect hidden executor state.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from mtg_sim.domain import Observation

SCHEMA_VERSION = "phase7-policy-config-v1"
DEFAULT_SEED_LIST_PATH = Path("configs/policy_seeds.json")
DEFAULT_POLICY_MATRIX_PATH = Path("configs/policies.json")


class PolicyError(ValueError):
    """Raised when policy configuration or records violate Phase 7 constraints."""


class MulliganStyle(StrEnum):
    AGGRESSIVE = "aggressive"
    SELECTIVE = "selective"


class DevelopmentPlan(StrEnum):
    MALCOLM_FIRST = "malcolm_first"
    TUTOR_FIRST = "tutor_first"
    MANA_ROCK_FIRST = "mana_rock_first"


class BreechesTiming(StrEnum):
    EARLY = "early"
    IMMEDIATE_TRIGGER_ONLY = "immediate_trigger_only"


class TutorPriority(StrEnum):
    GLINT_HORN_FIRST = "glint_horn_first"
    DUALCASTER_FIRST = "dualcaster_first"


class ComboPriority(StrEnum):
    EARLIEST_LEGAL = "earliest_legal"
    LOWEST_MANA = "lowest_mana"


class ProtectionPlan(StrEnum):
    PROTECTED = "protected"
    EARLIEST_UNPROTECTED = "earliest_unprotected"


class AttemptTiming(StrEnum):
    IMMEDIATE = "immediate"
    WAIT_ONE_TURN_FOR_PROTECTION = "wait_one_turn_for_protection"


class VelocityPlan(StrEnum):
    CANTRIP_FIRST = "cantrip_first"
    RAMP_FIRST = "ramp_first"


class MuddleUse(StrEnum):
    PRESERVE_INTERACTION = "preserve_interaction"
    TRANSMUTE = "transmute"


class GlintHornUse(StrEnum):
    HOLD_FOR_COMBO = "hold_for_combo"
    CAST_FOR_VALUE = "cast_for_value"


@dataclass(frozen=True, slots=True)
class MulliganKeepLogic:
    """Keep thresholds by hand size after Commander league mulligan replacement draws."""

    keep_at_7: str
    keep_at_6: str
    keep_at_5: str
    keep_at_4: str

    def criterion_for_size(self, hand_size: int) -> str:
        if hand_size == 7:
            return self.keep_at_7
        if hand_size == 6:
            return self.keep_at_6
        if hand_size == 5:
            return self.keep_at_5
        if hand_size == 4:
            return self.keep_at_4
        raise PolicyError(f"unsupported mulligan hand size: {hand_size}")


@dataclass(frozen=True, slots=True)
class PolicyConfig:
    policy_config_id: str
    bundle_name: str
    mulligan_style: MulliganStyle
    mulligan_keep_logic: MulliganKeepLogic
    development_plan: DevelopmentPlan
    malcolm_vs_mana_rock: DevelopmentPlan
    breeches_timing: BreechesTiming
    tutor_priority: TutorPriority
    combo_priority: ComboPriority
    protection_plan: ProtectionPlan
    attempt_timing: AttemptTiming
    velocity_plan: VelocityPlan
    muddle_use: MuddleUse
    glint_horn_use: GlintHornUse
    additional_policy: str = "none"
    schema_version: str = SCHEMA_VERSION
    documented_before_results: bool = True
    search_enabled: bool = False
    validation_seed_influence_allowed: bool = False

    def to_canonical_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def config_hash(self) -> str:
        return sha256_json(self.to_canonical_dict())

    def validate(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise PolicyError("unsupported policy schema version")
        if not self.policy_config_id:
            raise PolicyError("policy_config_id is required")
        if not self.documented_before_results:
            raise PolicyError("additional policies must be documented before results are seen")
        if self.search_enabled:
            raise PolicyError("Phase 7 policy framework must not enable exploratory search")
        if self.validation_seed_influence_allowed:
            raise PolicyError(
                "validation seeds may not influence discovery, advancement, or tie-breaking"
            )


@dataclass(frozen=True, slots=True)
class HandFeatures:
    hand_size: int
    lands: int
    mana_rocks: int
    cantrips: int
    tutors: int
    protection: int
    combo_pieces: int
    has_malcolm: bool
    has_breeches: bool
    has_glint_horn: bool
    has_muddle: bool


LANDS = frozenset(
    {
        "Island",
        "Mountain",
        "Command Tower",
        "Exotic Orchard",
        "Shivan Reef",
        "Cascade Bluffs",
        "Temple of Epiphany",
        "Izzet Boilerworks",
        "Frostboil Snarl",
        "Thriving Isle",
        "Ash Barrens",
        "Evolving Wilds",
        "Terramorphic Expanse",
        "Scavenger Grounds",
        "Demolition Field",
        "Path of Ancestry",
    }
)
MANA_ROCKS = frozenset(
    {"Sol Ring", "Arcane Signet", "Izzet Signet", "Prismatic Lens", "Fellwar Stone", "Mind Stone"}
)
CANTRIPS = frozenset(
    {
        "Expedite",
        "Opt",
        "Sleight of Hand",
        "Faithless Looting",
        "Frantic Search",
        "Impulse",
        "Chart a Course",
        "Fact or Fiction",
    }
)
TUTORS = frozenset(
    {
        "Drift of Phantasms",
        "Muddle the Mixture",
        "Dizzy Spell",
        "Step Through",
        "Vedalken Aethermage",
        "Invert // Invent",
        "Long-Term Plans",
    }
)
PROTECTION = frozenset(
    {
        "Siren Stormtamer",
        "Arcane Denial",
        "Negate",
        "Dispel",
        "Spell Pierce",
        "Wash Away",
        "Change the Equation",
        "Syncopate",
        "Lazotep Plating",
        "Reality Ripple",
    }
)
COMBO_PIECES = frozenset(
    {
        "Glint-Horn Buccaneer",
        "Dualcaster Mage",
        "Twinflame",
        "Electroduplicate",
        "Niv-Mizzet, the Firemind",
        "Curiosity",
        "Lightning-Rig Crew",
        "Crab Umbra",
        "Psychosis Crawler",
    }
)


def extract_hand_features(observation: Observation) -> HandFeatures:
    names = tuple(name for _, name in observation.hand)
    return HandFeatures(
        hand_size=len(names),
        lands=count_matching(names, LANDS),
        mana_rocks=count_matching(names, MANA_ROCKS),
        cantrips=count_matching(names, CANTRIPS),
        tutors=count_matching(names, TUTORS),
        protection=count_matching(names, PROTECTION),
        combo_pieces=count_matching(names, COMBO_PIECES),
        has_malcolm="Malcolm, Keen-Eyed Navigator" in names
        or "Malcolm, Keen-Eyed Navigator" in observation.command_zone_names,
        has_breeches="Breeches, Brazen Plunderer" in names
        or "Breeches, Brazen Plunderer" in observation.command_zone_names,
        has_glint_horn="Glint-Horn Buccaneer" in names,
        has_muddle="Muddle the Mixture" in names,
    )


def count_matching(names: Sequence[str], candidates: frozenset[str]) -> int:
    return sum(1 for name in names if name in candidates)


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    decision_type: str
    choice: str
    rationale: str
    observation_hash: str
    hand_features: HandFeatures


class CandidatePolicy:
    def __init__(self, config: PolicyConfig) -> None:
        config.validate()
        self.config = config

    def choose_action(self, observation: Observation) -> PolicyDecision:
        features = extract_hand_features(observation)
        if observation.terminal_status.value != "ongoing":
            choice = "pass_terminal"
        elif (
            self.config.attempt_timing is AttemptTiming.WAIT_ONE_TURN_FOR_PROTECTION
            and features.protection == 0
        ):
            choice = "develop_and_wait_for_protection"
        elif self.config.velocity_plan is VelocityPlan.RAMP_FIRST and features.mana_rocks > 0:
            choice = "prioritize_mana_rock"
        elif self.config.velocity_plan is VelocityPlan.CANTRIP_FIRST and features.cantrips > 0:
            choice = "prioritize_cantrip"
        else:
            choice = self.config.development_plan.value
        return PolicyDecision(
            "main_phase_priority",
            choice,
            self.config.policy_config_id,
            observation_digest(observation),
            features,
        )


def observation_digest(observation: Observation) -> str:
    return sha256_json(
        {
            "hand": observation.hand,
            "battlefield": observation.battlefield,
            "graveyard_names": observation.graveyard_names,
            "exile_names": observation.exile_names,
            "command_zone_names": observation.command_zone_names,
            "stack": observation.stack,
            "players": observation.players,
            "turn": observation.turn,
            "phase": observation.phase.value,
            "step": observation.step.value,
            "land_plays_this_turn": observation.land_plays_this_turn,
            "commander_cast_counts": dict(observation.commander_cast_counts),
            "terminal_status": observation.terminal_status.value,
            "library_size": observation.library_size,
            "known_top_library": observation.known_top_library,
        }
    )


@dataclass(frozen=True, slots=True)
class PairedComparisonRecord:
    comparison_id: str
    seed: int
    split: str
    policy_a: str
    policy_b: str
    policy_a_result_ref: str | None = None
    policy_b_result_ref: str | None = None
    paired_difference: Mapping[str, int | float | str] = field(default_factory=dict)
    validation_seed_used_for_discovery: bool = False

    def validate(self) -> None:
        if self.split == "validation" and self.validation_seed_used_for_discovery:
            raise PolicyError(
                "validation seeds cannot influence discovery advancement or tie-breaking"
            )
        if self.policy_a == self.policy_b:
            raise PolicyError("paired comparison requires two distinct policies")


@dataclass(frozen=True, slots=True)
class FirstDecisionDivergence:
    seed: int
    policy_a: str
    policy_b: str
    decision_index: int
    policy_a_choice: str
    policy_b_choice: str
    observation_hash: str
    visible_hand_features: HandFeatures


def first_decision_divergence(
    seed: int,
    policy_a: CandidatePolicy,
    policy_b: CandidatePolicy,
    observations: Sequence[Observation],
) -> FirstDecisionDivergence | None:
    for idx, obs in enumerate(observations):
        a = policy_a.choose_action(obs)
        b = policy_b.choose_action(obs)
        if a.choice != b.choice:
            return FirstDecisionDivergence(
                seed,
                policy_a.config.policy_config_id,
                policy_b.config.policy_config_id,
                idx,
                a.choice,
                b.choice,
                a.observation_hash,
                a.hand_features,
            )
    return None


def anchor_keep_logic(style: MulliganStyle) -> MulliganKeepLogic:
    if style is MulliganStyle.AGGRESSIVE:
        return MulliganKeepLogic(
            "combo_or_fast_malcolm", "land_plus_action", "two_land_or_sol_ring", "any_castable_plan"
        )
    return MulliganKeepLogic(
        "two_to_four_lands_and_action",
        "two_lands_and_action",
        "two_lands_or_tutor",
        "minimum_mana_plus_spell",
    )


def frozen_policy_matrix() -> tuple[PolicyConfig, ...]:
    base = PolicyConfig(
        "anchor_balanced",
        "balanced anchor",
        MulliganStyle.SELECTIVE,
        anchor_keep_logic(MulliganStyle.SELECTIVE),
        DevelopmentPlan.MALCOLM_FIRST,
        DevelopmentPlan.MALCOLM_FIRST,
        BreechesTiming.IMMEDIATE_TRIGGER_ONLY,
        TutorPriority.GLINT_HORN_FIRST,
        ComboPriority.EARLIEST_LEGAL,
        ProtectionPlan.PROTECTED,
        AttemptTiming.IMMEDIATE,
        VelocityPlan.RAMP_FIRST,
        MuddleUse.PRESERVE_INTERACTION,
        GlintHornUse.HOLD_FOR_COMBO,
    )
    variants: list[PolicyConfig] = [
        base,
        PolicyConfig(
            "anchor_aggressive",
            "aggressive anchor",
            MulliganStyle.AGGRESSIVE,
            anchor_keep_logic(MulliganStyle.AGGRESSIVE),
            DevelopmentPlan.TUTOR_FIRST,
            DevelopmentPlan.MANA_ROCK_FIRST,
            BreechesTiming.EARLY,
            TutorPriority.DUALCASTER_FIRST,
            ComboPriority.LOWEST_MANA,
            ProtectionPlan.EARLIEST_UNPROTECTED,
            AttemptTiming.IMMEDIATE,
            VelocityPlan.CANTRIP_FIRST,
            MuddleUse.TRANSMUTE,
            GlintHornUse.CAST_FOR_VALUE,
        ),
    ]
    axes: list[tuple[str, dict[str, Any]]] = [
        (
            "mulligan_aggressive",
            {
                "mulligan_style": MulliganStyle.AGGRESSIVE,
                "mulligan_keep_logic": anchor_keep_logic(MulliganStyle.AGGRESSIVE),
            },
        ),
        ("tutor_first", {"development_plan": DevelopmentPlan.TUTOR_FIRST}),
        (
            "mana_rock_first",
            {
                "malcolm_vs_mana_rock": DevelopmentPlan.MANA_ROCK_FIRST,
                "velocity_plan": VelocityPlan.RAMP_FIRST,
            },
        ),
        ("breeches_early", {"breeches_timing": BreechesTiming.EARLY}),
        ("dualcaster_tutor", {"tutor_priority": TutorPriority.DUALCASTER_FIRST}),
        ("lowest_mana_combo", {"combo_priority": ComboPriority.LOWEST_MANA}),
        ("earliest_unprotected", {"protection_plan": ProtectionPlan.EARLIEST_UNPROTECTED}),
        ("wait_for_protection", {"attempt_timing": AttemptTiming.WAIT_ONE_TURN_FOR_PROTECTION}),
        ("cantrip_first", {"velocity_plan": VelocityPlan.CANTRIP_FIRST}),
        ("transmute_muddle", {"muddle_use": MuddleUse.TRANSMUTE}),
        ("glint_horn_value", {"glint_horn_use": GlintHornUse.CAST_FOR_VALUE}),
        (
            "additional_land_stability",
            {"additional_policy": "prefer_land_stability_over_action_density_until_turn_3"},
        ),
    ]
    base_dict = base.to_canonical_dict() | {"schema_version": SCHEMA_VERSION}
    for policy_id, changes in axes:
        data = (
            base_dict
            | {"policy_config_id": policy_id, "bundle_name": f"one-axis {policy_id}"}
            | changes
        )
        variants.append(PolicyConfig(**data))
    for cfg in variants:
        cfg.validate()
    return tuple(variants)


def freeze_policy_artifacts(
    seed_path: Path = DEFAULT_SEED_LIST_PATH, matrix_path: Path = DEFAULT_POLICY_MATRIX_PATH
) -> None:
    seeds = frozen_seed_split()
    seed_path.write_text(json.dumps(seeds, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    policies = [
        cfg.to_canonical_dict() | {"config_hash": cfg.config_hash} for cfg in frozen_policy_matrix()
    ]
    matrix_path.write_text(
        json.dumps(
            {
                "schema_version": SCHEMA_VERSION,
                "full_factorial_run": False,
                "full_factorial_reason": "Screening uses anchors plus one-axis variants per docs/spec/POLICY_CANDIDATES.md.",
                "policies": policies,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def frozen_seed_split() -> dict[str, Any]:
    seeds = [
        int.from_bytes(hashlib.sha256(f"phase7-policy-seed-{i}".encode()).digest()[:8], "big")
        for i in range(500)
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "base_seed_count": 500,
        "discovery_count": 300,
        "validation_count": 200,
        "discovery_seeds": seeds[:300],
        "validation_seeds": seeds[300:],
    }


def sha256_json(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
