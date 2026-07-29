"""Frozen-source validation and offline deck construction.

These modules are classified ``SOURCE_VALIDATION_ONLY`` by
``automation/phase-a-authority-map.json``. They read the frozen Comprehensive
Rules, deck lists, and Oracle snapshot and verify their hashes. They contain no
rules-execution logic and are independent of the quarantined legacy engine, which
is why they remain importable while ``legacy/mtg_sim`` does not.

Nothing in this package is acceptance evidence for the clean engine.
"""

__version__ = "2.0.0"
