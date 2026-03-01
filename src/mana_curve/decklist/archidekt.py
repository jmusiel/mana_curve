"""Archidekt API integration for loading decklists."""

from __future__ import annotations

from typing import Any, Dict, List

from pyrchidekt.api import getDeckById
from tqdm import tqdm

from .loader import get_deckpath, save_decklist


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
    deck = getDeckById(deck_id)

    categories_in_deck = {cat.name: cat.included_in_deck for cat in deck.categories}
    cards = [c for c in deck.cards if categories_in_deck.get(c.categories[0], False)]

    if include_cuts_and_adds:
        categories_in_deck["Add"] = True
        categories_in_deck["add"] = True
        cards = [
            c for c in deck.cards
            if categories_in_deck.get(c.categories[0], False) and c.label != "Cuts"
        ]

    deck_list: List[Dict[str, Any]] = []

    for card in tqdm(cards, desc="Getting decklist"):
        for _ in range(card.quantity):
            if not categories_in_deck.get(card.categories[0], False):
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
                "user_category": card.categories[0],
                "tag": card.label,
                "commander": card.categories[0] == "Commander",
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
