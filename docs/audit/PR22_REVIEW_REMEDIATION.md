# PR #22 Review Remediation Record — Phase 9E

Branch: `codex/phase9e-pr22-remediation`
Base commit reviewed: `ee04adbffef948c5bc495492ba98b7ba2db44de9`

## Finding 1 — Activated-ability dispatch

- Original finding: accepted `ACTIVATE_ABILITY` actions for non-Glint-Horn cards could be executed through the Glint-Horn Buccaneer handler.
- Corrected module and function: `src/mtg_sim/engine.py` — `validate_action`, `generate_legal_actions`, `execute_action`, `execute_activated_ability`.
- Regression test IDs: `test_pr22_ability_dispatch_uses_registered_card_handlers_only`.
- Exact command evidence: `uv run pytest -q tests/test_phase9e_pr22_remediation.py tests/test_phase9c_real_executor.py tests/test_engine_competency.py -q` passed with `58 passed`.
- Resolution status: Resolved.

## Finding 2 — Commander action generation

- Original finding: legal cast actions were not generated for Malcolm and Breeches from the command zone.
- Corrected module and function: `src/mtg_sim/engine.py` — `generate_legal_actions`, `validate_action`, `execute_action`.
- Regression test IDs: `test_pr22_command_zone_actions_and_tax_validation`.
- Exact command evidence: `uv run pytest -q tests/test_phase9e_pr22_remediation.py tests/test_phase9c_real_executor.py tests/test_engine_competency.py -q` passed with `58 passed`.
- Resolution status: Resolved.

## Finding 3 — Commander tax

- Original finding: commander tax was not derived and enforced consistently by the shared validator and executor.
- Corrected module and function: `src/mtg_sim/engine.py` — `commander_action_cost`, `validate_action`, `execute_action`.
- Regression test IDs: `test_pr22_command_zone_actions_and_tax_validation`.
- Exact command evidence: `uv run pytest -q tests/test_phase9e_pr22_remediation.py tests/test_phase9c_real_executor.py tests/test_engine_competency.py -q` passed with `58 passed`.
- Resolution status: Resolved.

## Finding 4 — Fetch lands

- Original finding: Evolving Wilds and Terramorphic Expanse were modeled as normal colorless mana lands rather than fetch lands.
- Corrected module and function: `src/mtg_sim/engine.py` — `LAND_MANA`, `validate_action`, `generate_legal_actions`, `_activate_fetch_land`, `execute_activated_ability`.
- Regression test IDs: `test_pr22_fetch_lands_have_no_mana_ability_and_fetch_existing_basic_tapped`.
- Exact command evidence: `uv run pytest -q tests/test_phase9e_pr22_remediation.py tests/test_phase9c_real_executor.py tests/test_engine_competency.py -q` passed with `58 passed`.
- Resolution status: Resolved.

## Finding 5 — Combat timing

- Original finding: attacker declaration immediately dealt combat damage and created Malcolm/Breeches combat-damage consequences too early.
- Corrected module and function: `src/mtg_sim/engine.py` — `ActionType.COMBAT_DAMAGE`, `validate_action`, `generate_legal_actions`, `execute_action`, `declare_attackers`.
- Regression test IDs: `test_pr22_declare_attackers_does_not_deal_damage_or_make_treasure`.
- Exact command evidence: `uv run pytest -q tests/test_phase9e_pr22_remediation.py tests/test_phase9c_real_executor.py tests/test_engine_competency.py -q` passed with `58 passed`.
- Resolution status: Resolved.

## Finding 6 — Pure replay verification

- Original finding: replay verification appended verification events to the replayable gameplay event stream.
- Corrected module and function: `src/mtg_sim/game_executor.py` — `ReplayResult`, `verify_replay_events`, `replay_events`.
- Regression test IDs: `test_pr22_replay_verification_is_pure_and_detects_tampering`.
- Exact command evidence: `uv run pytest -q tests/test_phase9e_pr22_remediation.py tests/test_phase9c_real_executor.py tests/test_engine_competency.py -q` passed with `58 passed`.
- Resolution status: Resolved.
