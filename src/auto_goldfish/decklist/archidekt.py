"""Archidekt API integration for loading decklists."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import requests
from pyrchidekt.deck import Deck
from tqdm import tqdm

from . import rate_limiter
from .loader import get_deckpath, save_decklist
from .user_agent import default_user_agent

ARCHIDEKT_DECKS_V3_URL = "https://www.archidekt.com/api/decks/v3/"
ARCHIDEKT_DECK_URL = "https://www.archidekt.com/api/decks/{}/"
ARCHIDEKT_FORMAT_COMMANDER = 3


class ArchidektAPIError(Exception):
    """Raised when the Archidekt API returns an error."""


def _get_deck(deck_id: int) -> Deck:
    """Fetch a deck from Archidekt.

    Replaces pyrchidekt's ``getDeckById``, which sends no User-Agent, sets no
    timeout, and collapses every non-404 status into one opaque message. The
    status code matters: datacenter IPs sending a default library User-Agent
    are the ones most likely to be throttled or blocked.
    """
    rate_limiter.wait("archidekt")
    resp = requests.get(
        ARCHIDEKT_DECK_URL.format(deck_id),
        headers={"User-Agent": default_user_agent()},
        timeout=30,
    )
    if resp.status_code == 404:
        raise ArchidektAPIError(
            f"Deck {deck_id} not found (it may be private)"
        )
    if resp.status_code != 200:
        raise ArchidektAPIError(
            f"Archidekt returned HTTP {resp.status_code} for deck {deck_id}: "
            f"{resp.text[:200]}"
        )
    return Deck.fromJson(resp.json())


def _primary_category(card: Any) -> Optional[str]:
    """Return a card's first Archidekt category, or None if it has none.

    Archidekt leaves ``categories`` unset on cards the owner never tagged.
    """
    return card.categories[0] if card.categories else None


def _is_in_deck(card: Any, categories_in_deck: Dict[str, bool]) -> bool:
    """Whether a card counts toward the deck. Untagged cards are mainboard."""
    category = _primary_category(card)
    if category is None:
        return True
    return categories_in_deck.get(category, False)


def fetch_decklist(
    deck_url: str,
    verbose: bool = False,
    include_cuts_and_adds: bool = False,
) -> List[Dict[str, Any]]:
    """Fetch a decklist from the Archidekt API.

    Parameters
    ----------
    deck_url : str
        Archidekt deck URL (e.g. "https://archidekt.com/decks/12345/my_deck").
    verbose : bool
        Print card details while fetching.
    include_cuts_and_adds : bool
        Include cards in "Add" category and exclude cards labeled "Cuts".
    """
    deck_id = int(deck_url.split("/")[-2])
    deck = _get_deck(deck_id)

    categories_in_deck = {cat.name: cat.included_in_deck for cat in deck.categories}
    cards = [c for c in deck.cards if _is_in_deck(c, categories_in_deck)]

    if include_cuts_and_adds:
        categories_in_deck["Add"] = True
        categories_in_deck["add"] = True
        cards = [
            c for c in deck.cards
            if _is_in_deck(c, categories_in_deck) and c.label != "Cuts"
        ]

    deck_list: List[Dict[str, Any]] = []

    for card in tqdm(cards, desc="Getting decklist"):
        for _ in range(card.quantity):
            if not _is_in_deck(card, categories_in_deck):
                continue

            card_dict: Dict[str, Any] = {
                "name": card.card.oracle_card.name,
                "quantity": 1,
                "oracle_cmc": card.card.oracle_card.cmc,
                "cmc": card.card.oracle_card.cmc,
                "cost": card.card.oracle_card.mana_cost,
                "text": card.card.oracle_card.text,
                "sub_types": card.card.oracle_card.sub_types,
                "super_types": card.card.oracle_card.super_types,
                "types": card.card.oracle_card.types,
                "identity": card.card.oracle_card.color_identity,
                "default_category": card.card.oracle_card.default_category,
                "user_category": _primary_category(card),
                "tag": card.label,
                "commander": _primary_category(card) == "Commander",
            }

            if card.custom_cmc is not None:
                card_dict["cmc"] = card.custom_cmc

            # Handle modal/double-faced cards
            if card.card.oracle_card.faces:
                card_dict["cost"] = None
                card_dict["text"] = None
                card_dict["sub_types"] = []
                card_dict["super_types"] = []
                card_dict["types"] = []
                for face in card.card.oracle_card.faces:
                    if card_dict["cost"] is None:
                        card_dict["cost"] = face["manaCost"] + "//"
                    else:
                        card_dict["cost"] += face["manaCost"]
                    if card_dict["text"] is None:
                        card_dict["text"] = face["text"] + "//"
                    else:
                        card_dict["text"] += face["text"]
                    card_dict["sub_types"].extend(face["subTypes"])
                    card_dict["super_types"].extend(face["superTypes"])
                    card_dict["types"].extend(face["types"])

            if verbose:
                print(
                    f"\t{card_dict['quantity']} {card_dict['name']} "
                    f"cmc:{card_dict['oracle_cmc']} custom_cmc:{card_dict['cmc']}"
                )

            deck_list.append(card_dict)

    return deck_list


def fetch_and_save(
    deck_url: str,
    deck_name: str,
    verbose: bool = False,
    include_cuts_and_adds: bool = False,
) -> List[Dict[str, Any]]:
    """Fetch from Archidekt and save to JSON. Returns the deck list."""
    deck_list = fetch_decklist(
        deck_url, verbose=verbose, include_cuts_and_adds=include_cuts_and_adds
    )
    save_decklist(deck_name, deck_list)
    return deck_list


def list_user_decks(
    username: str,
    deck_format: int = ARCHIDEKT_FORMAT_COMMANDER,
    require_size: Optional[int] = 100,
    page_size: int = 100,
    timeout: int = 30,
) -> List[Dict[str, Any]]:
    """Return public deck listings owned by ``username`` from Archidekt.

    Filters out private, unlisted, and theorycrafted decks. When
    ``require_size`` is set (default 100) only decks with that exact card
    count are returned -- matches Commander legality.

    Each entry is the raw v3 result row (keys: id, name, size, deckFormat,
    edhBracket, owner, createdAt, updatedAt, ...).
    """
    params: Optional[Dict[str, Any]] = {
        "ownerUsername": username,
        "deckFormat": deck_format,
        "pageSize": page_size,
    }
    url: Optional[str] = ARCHIDEKT_DECKS_V3_URL
    out: List[Dict[str, Any]] = []
    while url:
        resp = requests.get(url, params=params, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        out.extend(data.get("results", []))
        url = data.get("next")
        params = None  # Archidekt's "next" already encodes the query.

    filtered: List[Dict[str, Any]] = []
    for entry in out:
        if entry.get("private") or entry.get("unlisted"):
            continue
        if entry.get("theorycrafted"):
            continue
        if require_size is not None and entry.get("size") != require_size:
            continue
        filtered.append(entry)
    return filtered
