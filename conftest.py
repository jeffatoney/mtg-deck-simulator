"""Ordinary-CI collection boundary for future protected reference tests.

The protected runner stages no parent conftest and explicitly collects the
reference directory, so this setup-only ignore cannot affect acceptance.
"""

collect_ignore_glob = ["tests/phase_a_reference/*"]
