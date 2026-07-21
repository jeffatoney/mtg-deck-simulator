Implement and run the complete competency suite in `docs/spec/RULES_ACCEPTANCE.md`. Do not run policy discovery, pilot games, or the full study.

For every test:

- Use a stable test ID.
- Cite the frozen Comprehensive Rules section and/or Oracle text in the test metadata.
- Show exact PASS/FAIL output.
- Save machine-readable results under `artifacts/rules/<run_id>/` with commit and source hashes.

Also run property tests for state conservation, mana legality, stack order, state-based-action timing, terminal-state enforcement, hidden-information isolation, deterministic replay, tutor exclusivity, and 100% deck coverage.

If any test fails or remains uncertain, stop with NO-GO. Do not weaken the test to make it pass. Correct code only when the source supports the correction, add regression evidence, and rerun the whole suite.
