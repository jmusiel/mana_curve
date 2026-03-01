"""Deck manipulation utilities (adjust land counts, etc.)."""

from __future__ import annotations

from typing import Any, Dict, List

from .loader import get_basic_island


def adjust_land_count(
    decklist: List[Dict[str, Any]],
    target_land_count: int,
    cuts: List[str] | None = None,
) -> List[Dict[str, Any]]:
    """Return a new decklist with the specified number of lands.

    Adds basic Islands or removes non-MDFC lands as needed.
    If *cuts* is provided, those spells are removed first when adding lands.
    """
    cuts = cuts or []
    original_count = len(decklist)
    spells = [c for c in decklist if "Land" not in c.get("types", []) and "land" not in c.get("types", [])]
    lands = [c for c in decklist if "Land" in c.get("types", []) or "land" in c.get("types", [])]

    diff = target_land_count - len(lands)

    while diff > 0:
        lands.append(get_basic_island())
        diff -= 1
        if cuts and len(spells) + len(lands) > original_count:
            for j, card in enumerate(spells):
                if card["name"] in cuts:
                    spells.pop(j)
                    break

    while diff < 0:
        # Remove a non-MDFC land
        for j, card in enumerate(lands):
            types = card.get("types", [])
            is_spell = any(
                t.lower() in ("creature", "artifact", "enchantment", "instant", "sorcery", "planeswalker", "battle")
                for t in types
            )
            if not is_spell:
                lands.pop(j)
                break
        diff += 1

    return spells + lands
