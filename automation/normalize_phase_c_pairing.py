from __future__ import annotations

import json
from pathlib import Path

# Preserve the already-frozen 500-game standard environment stream. Exploratory
# reuses 200 exact environments; only search randomness receives a new domain.
config_path = Path("docs/spec/phase-c/PHASE_C_PILOT_CONFIG.json")
config = json.loads(config_path.read_text(encoding="utf-8"))
config["pilot"]["environment_seed_namespace"] = "phase-c-pilot-standard-v1"
config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

simple = {
    "src/mtg_runs/phase_c_pairing.py": [
        ("from dataclasses import asdict, dataclass", "from dataclasses import dataclass"),
        (
            "    return p_value\n\n\ndef _paired_bootstrap_percentile_ci",
            "    return float(p_value)\n\n\ndef _paired_bootstrap_percentile_ci",
        ),
    ],
    "tests/phase_c/test_phase_c_artifacts.py": [
        ("from dataclasses import asdict, replace", "from dataclasses import asdict"),
    ],
}
for filename, replacements in simple.items():
    path = Path(filename)
    text = path.read_text(encoding="utf-8")
    for old, new in replacements:
        if text.count(old) != 1:
            raise SystemExit(f"unexpected generated source shape: {filename}: {old[:60]!r}")
        text = text.replace(old, new, 1)
    path.write_text(text, encoding="utf-8")

path = Path("src/mtg_runs/phase_c_runner.py")
text = path.read_text(encoding="utf-8")
seed_old = '    seed_text = f"phase-c:environment:{seed}"\n'
seed_new = '    seed_text = f"phase-c:standard:{seed}"\n'
if text.count(seed_old) != 1:
    raise SystemExit("unexpected generated environment seed construction")
text = text.replace(seed_old, seed_new, 1)
old = '''    explorer = (
        _OneLayerExplorer(policy_config_id, int(effective_search_seed))
        if mode == "EXPLORATORY" and policy_actions
        else None
    )
'''
new = '''    explorer = None
    if mode == "EXPLORATORY" and policy_actions:
        if effective_search_seed is None:
            raise ValueError("EXPLORATORY execution requires a search seed")
        explorer = _OneLayerExplorer(policy_config_id, effective_search_seed)
'''
if text.count(old) != 1:
    raise SystemExit("unexpected generated explorer construction")
path.write_text(text.replace(old, new, 1), encoding="utf-8")

# Issue #78: revealed LOOK_SELECT remainder cards are public candidates. Order
# all of them deterministically: lower evaluator value is bottommost first.
path = Path("src/mtg_policy/choices.py")
text = path.read_text(encoding="utf-8")
marker = '''        elif request.purpose.startswith("TUTOR_"):
'''
block = '''        elif request.purpose == "ORDER_LIBRARY_BOTTOM":
            if request.minimum != request.maximum or request.minimum != len(request.candidates):
                raise UnsupportedCapability(
                    "ORDER_LIBRARY_BOTTOM requires an exact ordering of every public candidate"
                )
            ordered = sorted(
                request.candidates,
                key=lambda card: (
                    evaluations[card.handle],
                    card.identity,
                    card.handle,
                ),
            )
            selected = tuple(card.handle for card in ordered)
        elif request.purpose.startswith("TUTOR_"):
'''
if text.count(marker) != 1:
    raise SystemExit("unexpected strategic choice provider shape")
path.write_text(text.replace(marker, block, 1), encoding="utf-8")

test_path = Path("tests/phase_c/test_phase_c_control.py")
test_text = test_path.read_text(encoding="utf-8")
import_old = "from mtg_kernel.errors import IllegalAction\n"
import_new = "from mtg_kernel.errors import IllegalAction, UnsupportedCapability\n"
if test_text.count(import_old) != 1:
    raise SystemExit("unexpected Phase C error import shape")
test_text = test_text.replace(import_old, import_new, 1)
test_text += '''

def test_order_library_bottom_is_exact_deterministic_and_evaluator_bound() -> None:
    bundle = next(
        item for item in load_policy_matrix() if item.policy_config_id == "anchor_balanced"
    )
    evaluator = ContextualEvaluator(load_evaluator_config())
    provider = PolicyStrategicChoiceProvider(bundle, evaluator)
    cards = (
        PublicCard("bottom-a", "Island", 0, ("Land",), ()),
        PublicCard("bottom-b", "Twinflame", 2, ("Sorcery",), ()),
        PublicCard("bottom-c", "Opt", 1, ("Instant",), ()),
    )
    request = CardSelectionRequest(
        request_id="order-library-bottom",
        actor_id="P0",
        ability_id="impulse",
        purpose="ORDER_LIBRARY_BOTTOM",
        turn_number=3,
        observation={"generation": 1, "player": "P0", "objects": [], "turn": {"number": 3}},
        candidates=cards,
        minimum=3,
        maximum=3,
    )
    evaluations = {
        card.handle: evaluator.evaluate_pile((card,), request.observation).score for card in cards
    }
    expected = tuple(
        card.handle
        for card in sorted(
            cards,
            key=lambda card: (evaluations[card.handle], card.identity, card.handle),
        )
    )
    first = provider.choose_cards(request)
    second = provider.choose_cards(request)
    assert first == second
    assert first.selected_handles == expected
    assert set(first.selected_handles) == {card.handle for card in cards}
    assert first.evaluator_id == evaluator.config.evaluator_id
    assert first.evaluator_sha256 == evaluator.config.config_sha256
    assert first.diagnostics["purpose"] == "ORDER_LIBRARY_BOTTOM"
    with pytest.raises(UnsupportedCapability, match="exact ordering"):
        provider.choose_cards(
            CardSelectionRequest(
                request_id="bad-bottom-order",
                actor_id="P0",
                ability_id="impulse",
                purpose="ORDER_LIBRARY_BOTTOM",
                turn_number=3,
                observation=request.observation,
                candidates=cards,
                minimum=2,
                maximum=3,
            )
        )
'''
test_path.write_text(test_text, encoding="utf-8")

# Keep the human authorization contract canonical for git diff --check.
auth_path = Path("docs/spec/phase-c/PHASE_C_PILOT_AUTHORIZATION.md")
auth_path.write_text(auth_path.read_text(encoding="utf-8").rstrip() + "\n", encoding="utf-8")
