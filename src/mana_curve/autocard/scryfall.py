"""Fetch top commander cards from Scryfall via scrython."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

import scrython

from .schemas import ScryfallCard

_DEFAULT_DATA_DIR = Path(__file__).parent / "data"


def fetch_top_cards(count: int = 1000) -> List[ScryfallCard]:
    """Fetch the top `count` commander cards ranked by EDHREC popularity.

    Uses scrython's Search with ``f:commander`` and ``order=edhrec``.
    Paginates automatically via ``iter_all()`` and stops after collecting
    the requested number of cards.
    """
    search = scrython.cards.Search(q="f:commander", order="edhrec", dir="asc")
    cards: List[ScryfallCard] = []

    for card_obj in search.iter_all():
        if len(cards) >= count:
            break
        try:
            cards.append(ScryfallCard.from_scryfall_object(card_obj))
        except Exception as exc:
            # Skip cards that fail to parse (e.g. unusual layouts)
            print(f"  Warning: skipping {card_obj.name!r}: {exc}")

    return cards


def save_cards(cards: List[ScryfallCard], path: Path | str | None = None) -> Path:
    """Save a list of ScryfallCards to a JSON file."""
    if path is None:
        path = _DEFAULT_DATA_DIR / "top_cards.json"
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "count": len(cards),
        "cards": [c.to_dict() for c in cards],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return path


def load_cards(path: Path | str | None = None) -> List[ScryfallCard]:
    """Load ScryfallCards from a previously saved JSON file."""
    if path is None:
        path = _DEFAULT_DATA_DIR / "top_cards.json"
    path = Path(path)

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    return [ScryfallCard.from_dict(c) for c in data["cards"]]
