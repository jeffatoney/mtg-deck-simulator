"""Fast contracts for effect kinds preserved by resolving a stack spell."""

import pytest

from mtg_kernel.factory import add_card, new_game
from mtg_kernel.models import CardSpec, GameObject, ObjectKind, Zone
from mtg_kernel.phase_b_runtime_effects_interaction import (
    _stack_spell_effect_kinds,
    _stack_spell_effect_semantics,
)


def _stack_spell(
    card_types: tuple[str, ...],
    abilities: tuple[dict[str, object], ...],
    *,
    cast_choices: dict[str, object] | None = None,
) -> GameObject:
    characteristics: dict[str, object] = {
        "card_types": list(card_types),
        "abilities": list(abilities),
    }
    if cast_choices is not None:
        characteristics["cast_choices"] = dict(cast_choices)
    return GameObject(
        "synthetic-stack-spell",
        ObjectKind.SPELL,
        Zone.STACK,
        "P0",
        "P0",
        current_characteristics=characteristics,
        was_cast=True,
    )


def test_permanent_stack_spell_excludes_hand_activation_capability() -> None:
    target = _stack_spell(
        ("Creature",),
        (
            {"kind": "SPELL", "effect": {"kind": "RESOLUTION_EFFECT"}},
            {
                "kind": "ACTIVATED",
                "cost": {"mana": "{1}", "discard": 1},
                "restriction": "SORCERY_SPEED",
                "effect": {"kind": "HAND_ONLY_EFFECT"},
            },
        ),
    )

    assert _stack_spell_effect_kinds(target) == ("RESOLUTION_EFFECT",)


def test_permanent_stack_spell_retains_post_resolution_capabilities() -> None:
    target = _stack_spell(
        ("Enchantment",),
        (
            {"kind": "SPELL", "effect": {"kind": "RESOLUTION_EFFECT"}},
            {
                "kind": "ACTIVATED",
                "cost": {"mana": "{2}", "discard": 1},
                "restriction": "SOURCE_ATTACKING",
                "effect": {"kind": "BATTLEFIELD_ACTIVATED_EFFECT"},
            },
            {
                "kind": "TRIGGERED",
                "trigger": "BATTLEFIELD_EVENT",
                "effect": {"kind": "BATTLEFIELD_TRIGGERED_EFFECT"},
            },
        ),
    )

    assert _stack_spell_effect_kinds(target) == (
        "BATTLEFIELD_ACTIVATED_EFFECT",
        "BATTLEFIELD_TRIGGERED_EFFECT",
        "RESOLUTION_EFFECT",
    )


def _synthetic_kicker_spell() -> CardSpec:
    ability = {
        "ability_id": "synthetic:kicker-spell",
        "kind": "SPELL",
        "face": 0,
        "mode": "default",
        "target_schema": {"kind": "NONE", "min": 0, "max": 0, "unique": True},
        "effect": {"kind": "BOUNCE_AND_KICKER_DRAW", "kicker": "{1}"},
    }
    face = {
        "name": "Synthetic Kicker Spell",
        "mana_cost": "",
        "mana_value": 0,
        "supertypes": [],
        "card_types": ["Instant"],
        "subtypes": [],
        "keywords": [],
        "oracle_text": "Synthetic kernel contract.",
        "abilities": [ability],
        "spell_modes": [ability],
        "activated_abilities": [],
        "triggered_abilities": [],
    }
    return CardSpec(
        card_spec_id="synthetic:kicker-spell",
        name="Synthetic Kicker Spell",
        oracle_id="synthetic:kicker-spell",
        oracle_record_sha256="0" * 64,
        source_version="synthetic-kernel-contract",
        mana_cost="",
        mana_value=0,
        supertypes=(),
        card_types=("Instant",),
        subtypes=(),
        colors=(),
        color_identity=(),
        keywords=(),
        power=None,
        toughness=None,
        oracle_text="Synthetic kernel contract.",
        faces=(face,),
        abilities=(ability,),
    )


@pytest.mark.parametrize(
    ("raw_kicked", "expected_kicked"),
    [(False, False), (True, True), ("yes", True), ([], False)],
    ids=("false", "true", "truthy-string", "falsey-list"),
)
def test_kicker_resolution_semantics_use_normalized_production_cast_fact(
    raw_kicked: object,
    expected_kicked: bool,
) -> None:
    state, executor = new_game(("P0", "P1"), f"normalized-kicker-{raw_kicked!r}")
    for player in state.players.values():
        player.mana_pool.update({symbol: 0 for symbol in ("W", "U", "B", "R", "G", "C")})
    state.players["P0"].mana_pool["C"] = 1
    card = add_card(executor, _synthetic_kicker_spell(), Zone.HAND, owner="P0")

    stack_spell = executor.cast("P0", card.object_id, choices={"kicked": raw_kicked})
    action = executor._created_action(stack_spell)
    semantics = _stack_spell_effect_semantics(stack_spell)

    assert stack_spell.current_characteristics.get("kicked", False) is expected_kicked
    assert stack_spell.current_characteristics["cast_choices"]["kicked"] == raw_kicked
    assert sum(action.payments["mana"].values()) == int(expected_kicked)
    assert semantics.effect_kinds == ("BOUNCE_AND_KICKER_DRAW",)
    assert semantics.inactive_effect_kinds == (() if expected_kicked else ("DRAW",))
