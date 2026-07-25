# Phase A rules-kernel audit record

The frozen Comprehensive Rules, Oracle snapshot, deck and commander sources, rules acceptance
specification, pilot configurations, legacy engine, `GameExecutor`, and replay implementation were
reviewed before implementation. PR #29 could not be fetched from this checkout because it has no
Git remote or GitHub CLI. Its explicitly supplied regression themes are captured by the Phase A
tests. None of its import-time `setattr` patch architecture is used.

The production pilot and full study remain locked. The recovery workflow is manual-only and accepts
exactly `VALIDATE_RULES_KERNEL`; it runs no pilot command. The new kernel is fail-closed at the
migration inventory boundary. The inventory reflects the frozen snapshot's 80 unique definitions:
10 migrated and 70 pending. The prompt's phrase “remaining 88 representative unique cards” does not
match the frozen source (78 unique library names plus two commanders); this discrepancy is recorded
rather than silently inventing definitions.
