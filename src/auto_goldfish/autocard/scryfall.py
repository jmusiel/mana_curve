"""Fetch top commander cards from Scryfall via scrython."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List

# scrython uses aiohttp which needs SSL certs; on macOS the default
# Python cert store is often empty.  Point it at certifi's bundle.
try:
    import certifi

    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
except ImportError:
    pass

import scrython

from .schemas import ScryfallCard

_DEFAULT_DATA_DIR = Path(__file__).parent / "data"


def _parse_card_dict(raw: dict) -> ScryfallCard:
    """Parse a raw Scryfall JSON dict into a ScryfallCard.

    Handles double-faced cards by concatenating oracle text from faces.
    """
    oracle_text = ""
    mana_cost = ""
    card_faces_data = None

    faces = raw.get("card_faces")
    if faces:
        card_faces_data = faces
        text_parts = [f.get("oracle_text", "") for f in faces]
        cost_parts = [f.get("mana_cost", "") for f in faces]
        oracle_text = " // ".join(text_parts)
        mana_cost = " // ".join(cost_parts)
    else:
        oracle_text = raw.get("oracle_text", "")
        mana_cost = raw.get("mana_cost", "")

    return ScryfallCard(
        name=raw["name"],
        mana_cost=mana_cost,
        cmc=raw.get("cmc", 0.0),
        type_line=raw.get("type_line", ""),
        oracle_text=oracle_text,
        colors=raw.get("colors", []),
        color_identity=raw.get("color_identity", []),
        keywords=raw.get("keywords", []),
        edhrec_rank=raw.get("edhrec_rank"),
        layout=raw.get("layout", "normal"),
        card_faces=card_faces_data,
        produced_mana=raw.get("produced_mana", []),
    )


def fetch_top_cards(
    count: int = 1000,
    query: str = "f:commander",
) -> List[ScryfallCard]:
    """Fetch the top `count` commander cards ranked by EDHREC popularity.

    Uses scrython's Search with the given query and ``order=edhrec``.
    Paginates manually through results until we have enough cards.
    """
    import time

    page = 1
    cards: List[ScryfallCard] = []

    while True:
        search = scrython.cards.Search(q=query, order="edhrec", dir="asc", page=page)

        for raw in search.data():
            if len(cards) >= count:
                return cards
            try:
                cards.append(_parse_card_dict(raw))
            except Exception as exc:
                name = raw.get("name", "???")
                print(f"  Warning: skipping {name!r}: {exc}")

        if not search.has_more():
            break

        page += 1
        # Scryfall asks for 50-100ms between requests
        time.sleep(0.1)

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
