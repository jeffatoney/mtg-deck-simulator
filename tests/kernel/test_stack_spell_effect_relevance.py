"""Fast contracts for effect kinds preserved by resolving a stack spell."""

from mtg_kernel.models import GameObject, ObjectKind, Zone
from mtg_kernel.phase_b_runtime_effects_interaction import _stack_spell_effect_kinds


def _stack_spell(
    card_types: tuple[str, ...],
    abilities: tuple[dict[str, object], ...],
) -> GameObject:
    return GameObject(
        "synthetic-stack-spell",
        ObjectKind.SPELL,
        Zone.STACK,
        "P0",
        "P0",
        current_characteristics={
            "card_types": list(card_types),
            "abilities": list(abilities),
        },
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
