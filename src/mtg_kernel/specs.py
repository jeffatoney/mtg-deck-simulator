"""Pure helpers for deriving an object's fresh characteristics from a card specification."""

from __future__ import annotations

from mtg_kernel.models import CardSpec, Zone

PUBLIC_ZONES = {Zone.BATTLEFIELD, Zone.STACK, Zone.GRAVEYARD, Zone.EXILE, Zone.COMMAND}


def base_characteristics(spec: CardSpec, face: int | None = None) -> dict[str, object]:
    selected = spec.faces[face] if face is not None and spec.faces else None
    power = selected.get("power") if selected else spec.power
    toughness = selected.get("toughness") if selected else spec.toughness
    characteristics: dict[str, object] = {
        "name": selected.get("name", spec.name) if selected else spec.name,
        "card_spec_id": spec.card_spec_id,
        "oracle_id": spec.oracle_id,
        "oracle_record_sha256": spec.oracle_record_sha256,
        "source_version": spec.source_version,
        "mana_cost": selected.get("mana_cost", spec.mana_cost) if selected else spec.mana_cost,
        "mana_value": selected.get("mana_value", spec.mana_value) if selected else spec.mana_value,
        "supertypes": list(selected.get("supertypes", spec.supertypes))
        if selected
        else list(spec.supertypes),
        "card_types": list(selected.get("card_types", spec.card_types))
        if selected
        else list(spec.card_types),
        "subtypes": list(selected.get("subtypes", spec.subtypes))
        if selected
        else list(spec.subtypes),
        "colors": list(spec.colors),
        "color_identity": list(spec.color_identity),
        "keywords": list(selected.get("keywords", spec.keywords))
        if selected
        else list(spec.keywords),
        "oracle_text": selected.get("oracle_text", spec.oracle_text)
        if selected
        else spec.oracle_text,
        "abilities": list(selected.get("abilities", spec.abilities))
        if selected
        else list(spec.abilities),
        "faces": [dict(value) for value in spec.faces],
    }
    if power is not None:
        characteristics["power"] = int(power) if str(power).lstrip("-").isdigit() else power
    if toughness is not None:
        characteristics["toughness"] = (
            int(toughness) if str(toughness).lstrip("-").isdigit() else toughness
        )
    return characteristics


def default_visibility(zone: Zone, owner: str, players: set[str], face_down: bool = False) -> set[str]:
    if face_down or zone in {Zone.HAND, Zone.LIBRARY}:
        return {owner}
    if zone in PUBLIC_ZONES:
        return set(players)
    return {owner}
