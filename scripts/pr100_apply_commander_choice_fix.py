#!/usr/bin/env python3
"""Apply the general Commander graveyard/exile choice repair, fail closed."""

from __future__ import annotations

import argparse
from pathlib import Path


def replace_once(root: Path, relative: str, old: str, new: str) -> None:
    target = root / relative
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{relative}: expected exactly one source fragment, found {count}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def apply(root: Path) -> None:
    replace_once(
        root,
        "src/mtg_kernel/engine_core.py",
        """            for obj in list(self.state.objects.values()):
                if (
                    obj.retired
                    or obj.zone not in {Zone.GRAVEYARD, Zone.EXILE}
                    or not obj.component_card_instance_ids
                ):
                    continue
                instance = self.state.card_instances[obj.component_card_instance_ids[0]]
                if (
                    instance.commander_designation
                    and obj.object_id not in self.state.pending_commander_choices
                ):
                    self.state.pending_commander_choices.append(obj.object_id)
""",
        "",
    )

    replace_once(
        root,
        "src/mtg_kernel/zones.py",
        """        old = self.state.objects[object_id]
        if old.retired or old.ceased_to_exist:
            raise IllegalAction("cannot move a retired object")
        self._remove_from_zone(old)
""",
        """        old = self.state.objects[object_id]
        if old.retired or old.ceased_to_exist:
            raise IllegalAction("cannot move a retired object")
        if object_id in self.state.pending_commander_choices:
            self.state.pending_commander_choices.remove(object_id)
        self._remove_from_zone(old)
""",
    )

    replace_once(
        root,
        "src/mtg_kernel/zones.py",
        """            self.state.objects[successor.object_id] = successor
            self.register(successor)

        change = ZoneChange(
""",
        """            self.state.objects[successor.object_id] = successor
            self.register(successor)
            if destination in {Zone.GRAVEYARD, Zone.EXILE} and any(
                self.state.card_instances[card_id].commander_designation
                for card_id in successor.component_card_instance_ids
            ):
                self.state.pending_commander_choices.append(successor.object_id)

        change = ZoneChange(
""",
    )

    replace_once(
        root,
        "tests/phase_a/test_kernel_acceptance.py",
        """    declined = executor.commander_return_choice("P0", grave.object_id, False)
    assert declined.zone is Zone.GRAVEYARD and state.choices[-1].selected == "DECLINE"

    state2, executor2 = funded_game()
""",
        """    declined = executor.commander_return_choice("P0", grave.object_id, False)
    assert declined.zone is Zone.GRAVEYARD and state.choices[-1].selected == "DECLINE"
    executor.check_state_based_actions()
    assert grave.object_id not in state.pending_commander_choices

    moved_again = executor.zones.move(
        grave.object_id, Zone.EXILE, "TEST", executor._event("TEST")
    )
    assert moved_again is not None
    executor.check_state_based_actions()
    assert state.pending_commander_choices == [moved_again.object_id]

    state2, executor2 = funded_game()
""",
    )

    replace_once(
        root,
        "tests/phase_b/test_broker_fail_closed.py",
        """    commander = add_card(
        executor, specs["Malcolm, Keen-Eyed Navigator"], Zone.EXILE, commander=True
    )
    executor.check_state_based_actions()
""",
        """    commander = add_card(
        executor, specs["Malcolm, Keen-Eyed Navigator"], Zone.BATTLEFIELD, commander=True
    )
    exiled = executor.zones.move(
        commander.object_id, Zone.EXILE, "TEST", executor._event("TEST")
    )
    assert exiled is not None
    executor.check_state_based_actions()
""",
    )

    replace_once(
        root,
        "tests/phase_b/test_broker_fail_closed.py",
        """        and obj.component_card_instance_ids == commander.component_card_instance_ids
""",
        """        and obj.component_card_instance_ids == exiled.component_card_instance_ids
""",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("."))
    args = parser.parse_args()
    apply(args.repo.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
