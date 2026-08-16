from __future__ import annotations

from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected one replacement in {path}, found {count}")
    path.write_text(text.replace(old, new), encoding="utf-8")


def main() -> None:
    diagnostic = Path(
        ".github/diagnostics/pr100_public_tiebreak_diagnostic.py.txt"
    )
    replace_once(
        diagnostic,
        '''    if selector == "legacy":
        return max(
            actions,
            key=lambda action: (*legacy_score(action), action.handle),
        ).handle
''',
        '''    if selector == "legacy":
        historical_representative = max(
            actions,
            key=lambda action: (*legacy_score(action), action.handle),
        )
        selected_key = public_action_key(
            PolicyActionView.from_observed(historical_representative)
        )
        return resolve_selected_action_handle(actions, selected_key)
''',
    )


if __name__ == "__main__":
    main()
