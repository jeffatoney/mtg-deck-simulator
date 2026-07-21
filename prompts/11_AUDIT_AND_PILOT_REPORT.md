Audit the completed pilot using the independent replay validator and `docs/audit/AUDIT_CHECKLIST.md`. Do not run the full study.

Fully decode and inspect all required categories. For every audited game, save checklist results with event references. Identify any repeated error pattern, future-information access, illegal target/payment/timing, incorrect deterministic-loop classification, or obvious policy violation.

If a repeated error exists:

- Mark the pilot run invalid and quarantine it.
- Add a regression test.
- Correct the engine in a separate commit.
- Rerun the complete competency suite and the entire pilot under a new run ID.
- Do not merge old and new results.

If the audit passes, produce exactly the required pilot report: errors, corrections, audit pass rate, discovery and validation results, preliminary policies, indistinguishable policies, material assumptions, ten representative decoded games, and a clear go/no-go recommendation for the full study. Include paths and hashes for every empirical claim.
