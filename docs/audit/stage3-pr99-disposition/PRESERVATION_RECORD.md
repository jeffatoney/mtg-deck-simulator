# Stage 3 PR #99 Prototype Preservation Record

## Frozen prototype

PR #99, **Phase C: directed exploratory V2 redesign**, is preserved as prototype evidence.

- Preservation date: August 21, 2026 (America/Los_Angeles)
- Prototype base SHA: `150671a8e7a78e5fa14b6b3aca2308f6af647df3`
- Prototype head SHA: `4c9a404fc9308ecc281711b4b9b48eef6dfd441b`
- Commit count: 34
- Changed-file count: 37
- State verified by Stage 3 measurement: open, draft, unmerged
- Stage 3 base `main` SHA: `8b69b0aa3c3896c26f9c0823fd102dfa9a87f41f`

PR #99 will remain open, draft, unmerged, and unmodified. Stage 3 does not merge, rebase, update, force-push, or wholesale cherry-pick the prototype branch.

## Canonical patch digest

The preservation measurement ran on GitHub Actions Ubuntu 24.04 using Git `2.55.0`.

Canonical command:

```text
git -c core.quotepath=false diff --binary --full-index --no-ext-diff --no-color 150671a8e7a78e5fa14b6b3aca2308f6af647df3 4c9a404fc9308ecc281711b4b9b48eef6dfd441b
```

Measured patch:

- SHA-256: `31dbf0dad6c8bc497ea8dcb2bd40694d28e9b90cd6b25cf1b24a4cb5aae88b16`
- Bytes: 297,677
- Workflow run: `32554710434`
- Job: `96986959097`
- Measurement artifact: `9471079396`

The same workflow independently verified the prototype base/head SHAs, 34-commit count, 37-file count, and open/draft/unmerged PR state before emitting the digest.

## Complete changed-file manifest

1. `.github/workflows/phase-c-exploratory-v2-diagnostic.yml`
2. `configs/evaluators/exploratory_aggressive_v2.yaml`
3. `configs/evaluators/exploratory_alt_package_v2.yaml`
4. `configs/evaluators/exploratory_interaction_discovery_v2.yaml`
5. `configs/evaluators/exploratory_v2_scoring.yaml`
6. `docs/architecture/decisions/0017-controlled-counter-payment-outcomes.md`
7. `docs/audit/phase-a-certification/CERTIFICATION.json`
8. `docs/audit/phase-b-certification/CERTIFICATION.json`
9. `docs/audit/phase-c-exploratory-v2-diagnostic/DIAGNOSTIC_SUMMARY.md`
10. `docs/audit/phase-c-exploratory-v2-diagnostic/README.md`
11. `docs/spec/phase-c/EXPLORATORY_V2_DECISION_SCHEMA.json`
12. `docs/spec/phase-c/EXPLORATORY_V2_DESIGN.md`
13. `docs/spec/phase-c/EXPLORATORY_V2_KNOWN_LIMITATIONS.md`
14. `docs/spec/phase-c/EXPLORATORY_V2_SMALL_PILOT_DECISION_PACKAGE.md`
15. `scripts/check_clean_engine_boundary.py`
16. `src/mtg_kernel/phase_b_resolution_mana.py`
17. `src/mtg_kernel/phase_b_runtime_effects_interaction.py`
18. `src/mtg_kernel/strategic_choices.py`
19. `src/mtg_policy/choices.py`
20. `src/mtg_policy/exploratory_v2.py`
21. `src/mtg_policy/exploratory_v2_strategic.py`
22. `src/mtg_runs/exact_json_bytes.py`
23. `src/mtg_runs/phase_c_exploratory_v2.py`
24. `src/mtg_runs/phase_c_exploratory_v2_diagnostic.py`
25. `src/mtg_runs/phase_c_mulligan_v2.py`
26. `src/mtg_search/directed_v2.py`
27. `tests/phase_c/test_counter_payment_resolution_choices_v2.py`
28. `tests/phase_c/test_exploratory_v2_arm_constraints.py`
29. `tests/phase_c/test_exploratory_v2_artifact_hashing.py`
30. `tests/phase_c/test_exploratory_v2_counter_payment.py`
31. `tests/phase_c/test_exploratory_v2_hidden_info.py`
32. `tests/phase_c/test_exploratory_v2_integration.py`
33. `tests/phase_c/test_exploratory_v2_land_guardrail.py`
34. `tests/phase_c/test_exploratory_v2_mulligan.py`
35. `tests/phase_c/test_exploratory_v2_runner_smoke.py`
36. `tests/phase_c/test_exploratory_v2_selection.py`
37. `tests/phase_c/test_exploratory_v2_strategic_choices.py`

The machine-readable preservation record is `PRESERVATION_RECORD.json`. The complete file and component disposition is `INVENTORY.json`.

## Guardrails retained

PR #99 certification files are not copied into Stage 3. Historical pilot artifacts are not modified. This preservation record does not authorize a pilot, replacement pilot, or full study.
