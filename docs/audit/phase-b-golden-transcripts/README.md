# Phase B golden transcripts

This directory contains the twelve mandatory behavioral-transcript candidates required by `ENGINE_BUILD_PHASE_B.md`.

Each transcript is bound by ID, mandatory scenario family, production `test_node`, ordered operations, required event order, assertions, and SHA-256 digest. The candidate gate executes all twelve named tests rather than merely collecting them.

`APPROVALS.json` is intentionally `PENDING_OWNER_APPROVAL`. The strict Phase B verifier must fail until Jeff Toney explicitly approves the exact twelve IDs and digests and the approval document is anchored in `scripts/check_phase_b_golden_transcripts.py`.

No transcript approval authorizes the 500/200 pilot or the 20,000/5,000 study.
