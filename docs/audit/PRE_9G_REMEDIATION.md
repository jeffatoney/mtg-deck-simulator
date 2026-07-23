# Phase 9F-5 pre-9G remediation audit

Internet access is disabled in this agent run and the GitHub CLI is not installed in the container, so original unresolved review-thread URLs for PRs #23 through #26 could not be retrieved live. The rows below track the review findings enumerated in the Phase 9F-5 task against current main `68230ead0ab46c09ffcc360c49fd36f8c22a3997` and the local remediation commit.

| Finding | Original PR / review-thread URL | Severity | Defect remained in current main | Corrected function | Regression test ID | Final status |
|---|---|---:|---|---|---|---|
| Soul-Guide Lantern draw ability must pay `{1}` before sacrifice and draw. | PR #23 / unavailable offline | P1 | Yes | `soul_guide_lantern_draw` | `test_phase9f5_soul_guide_lantern_draw_pays_before_sacrifice` | Fixed |
| Combat-damage execution must stop immediately after a terminal result. | PR #23 / unavailable offline | P1 | Yes | `execute_action` combat-damage branch | `test_phase9f5_combat_uses_power_defenders_and_commander_presence` | Fixed |
| Evolving Wilds and Terramorphic Expanse must remain playable and must use their actual fetch abilities. | PR #23 / unavailable offline | P2 | No | `_activate_fetch_land`, `generate_legal_actions` | `test_every_land_play_is_generated`, `test_land_mana_and_fetch_behaviors` | Preserved |
| The executable-coverage gate must reject every `BLOCKED` adapter. | PR #24 / unavailable offline | P1 | Yes | `validate_executable_coverage` | `test_phase9f5_callable_gate_rejects_blocked_missing_wrong_and_placeholder` | Fixed |
| Cascade Bluffs must support colorless mana, legal blue/red input, and `UU`, `UR`, or `RR` output. | PR #24 / unavailable offline | P2 | Yes | `_legal_mana_outputs`, `tap_for_mana` | `test_phase9f5_cascade_bluffs_and_prismatic_lens_semantics` | Fixed |
| Prismatic Lens must support tap for colorless and `{1}, tap` filtering into any legal color. | PR #24 / unavailable offline | P2 | Yes | `_legal_mana_outputs`, `tap_for_mana` | `test_phase9f5_cascade_bluffs_and_prismatic_lens_semantics` | Fixed |
| Scavenger Grounds must sacrifice a Desert. | PR #24 / unavailable offline | P2 | Yes | `validate_action`, `execute_activated_ability` | `test_phase9f5_demolition_field_and_scavenger_grounds_require_legal_costs_and_targets` | Fixed |
| Demolition Field must target a nonbasic land, tap and sacrifice itself, destroy the target, and perform only legal basic searches. | PR #24 / unavailable offline | P2 | Yes | `validate_action`, `execute_activated_ability` | `test_phase9f5_demolition_field_and_scavenger_grounds_require_legal_costs_and_targets` | Fixed |
| Commit must not be accepted without choosing Commit and a legal target. | PR #25 / unavailable offline | P1 | Yes | `validate_action` | `test_phase9f5_targets_and_conditional_counters_are_enforced` | Fixed |
| Expedite must not be accepted without a legal creature target. | PR #25 / unavailable offline | P1 | Yes | `validate_action` | `test_phase9f5_targets_and_conditional_counters_are_enforced` | Fixed |
| Mandatory discard counts must be enforced after cards are drawn. | PR #25 / unavailable offline | P2 | No | `_spell_effect_for_action`, `_discard_named` | `test_phase9f2_draw_tutor_split_adapters.py` semantic tests | Preserved |
| Opt must branch between keeping the top card and putting it on the bottom. | PR #25 / unavailable offline | P2 | No | `_spell_effect_for_action`, `generate_legal_actions` | `test_phase9f2_draw_tutor_split_adapters.py` semantic tests | Preserved |
| Conditional counters must not assume an opponent declines payment. | PR #25 / unavailable offline | P2 | No | `counter_unless_pays`, `spell_pierce`, `syncopate` | `test_phase9f5_targets_and_conditional_counters_are_enforced` | Preserved |
| Stack objects must carry correct spell types, colors, mana value, chosen face, and cast zone. | PR #25 / unavailable offline | P1 | Yes | `execute_action`, `StackObject` construction | `test_phase9f5_creature_and_artifact_spells_use_stack_and_sba_removes_lethal_damage` | Fixed |
| Sentinel Totem and Soul-Guide Lantern must resolve as battlefield permanents and execute their ETB abilities. | PR #26 / unavailable offline | P2 | Partially | `resolve_top`, ETB handlers | Existing Phase 9F-3 semantic tests | Preserved / strengthened by stack resolution |
| State-based actions must remove creatures with lethal damage or zero toughness. | PR #26 / unavailable offline | P1 | Yes | `GameState.check_state_based_actions` | `test_phase9f5_creature_and_artifact_spells_use_stack_and_sba_removes_lethal_damage` | Fixed |
| Preserve corrected Prismari Command Treasure creation. | PR #26 / unavailable offline | P2 | No | `prismari_command` | `test_phase9f3_interaction_adapters.py` semantic tests | Preserved |
| Preserve fetch-land play-action generation. | PR #26 / unavailable offline | P2 | No | `generate_legal_actions` | `test_every_land_play_is_generated` | Preserved |

## Gate conclusion

The pre-policy readiness gate is intentionally fail-closed: executable coverage now inspects callable references and rejects missing callables, placeholder/no-op handlers, wrong-card rows, missing semantic-test IDs, `BLOCKED` status, and unexpected registry rows.
