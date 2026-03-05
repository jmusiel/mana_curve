"""Load and query the otag registry for Scryfall tag-based card filtering."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_REGISTRY_PATH = Path(__file__).parent / "otag_registry.json"


def load_otag_registry(path: Path | str | None = None) -> dict[str, Any]:
    """Load the otag registry JSON file.

    Returns dict with keys 'updated' (str) and 'cards' (dict of name -> [otags]).
    """
    if path is None:
        path = _REGISTRY_PATH
    path = Path(path)

    if not path.exists():
        return {"updated": "", "cards": {}}

    with open(path, encoding="utf-8") as f:
        return json.load(f)


def get_matching_cards(
    card_names: list[str],
    registry: dict[str, Any],
) -> dict[str, list[str]]:
    """Return subset of card_names that appear in the otag registry.

    Returns dict of card_name -> list of otag strings.
    """
    registry_cards = registry.get("cards", {})
    return {
        name: registry_cards[name]
        for name in card_names
        if name in registry_cards
    }


def has_cheaper_than_mv(card_name: str, registry: dict[str, Any]) -> bool:
    """Check if a card has the 'cheaper-than-mv' otag."""
    otags = registry.get("cards", {}).get(card_name, [])
    return "cheaper-than-mv" in otags
