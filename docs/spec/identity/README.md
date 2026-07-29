# Identity Specification Status

The binding identity specification is:

```text
docs/spec/identity/IDENTITY_MODEL_V2.0.0.md
```

Its bytes intentionally still contain the pre-approval label `LOCK_READY`. Editing that label after approval would change the approved digest. The companion files perform the freeze transition without mutating the approved Markdown bytes:

- `IDENTITY_MODEL_V2.0.0_APPROVAL_RECORD.json`
- `IDENTITY_MODEL_V2.0.0_LOCK_MANIFEST.txt`

The effective status is:

```text
FROZEN_BINDING_FOR_PHASE_A
```

The approved SHA-256 digest is:

```text
c839c16aa08ed6053233745fd2a35c38cbe4aadb16423ecac3d5390999af3ce6
```

Run this before engine work or review:

```bash
uv run python scripts/check_identity_lock.py
```

Do not edit the V2.0.0 Markdown, approval record, or lock manifest in an implementation pull request. A binding correction requires a new semantic version, a new digest, and owner approval.
