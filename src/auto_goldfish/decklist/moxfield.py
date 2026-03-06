"""Moxfield API integration for loading decklists."""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List

import requests

from . import rate_limiter
from .card_resolver import resolve_cards

_API_BASE = "https://api2.moxfield.com/v3/decks/all"

# Matches Moxfield URLs like:
#   https://www.moxfield.com/decks/AbCdEf123
#   https://moxfield.com/decks/AbCdEf123
_URL_RE = re.compile(r"moxfield\.com/decks/([A-Za-z0-9_-]+)")


class MoxfieldConfigError(Exception):
    """Raised when the Moxfield User-Agent credential is not configured."""


class MoxfieldAPIError(Exception):
    """Raised when the Moxfield API returns an error."""


def _get_user_agent() -> str:
    """Read the Moxfield User-Agent from environment.

    The User-Agent is a sensitive credential and must never be logged,
    exposed to clients, or committed to source control.
    """
    ua = os.environ.get("MOXFIELD_USER_AGENT", "").strip()
    if not ua:
        raise MoxfieldConfigError(
            "MOXFIELD_USER_AGENT environment variable is not set. "
            "Moxfield import requires a valid User-Agent credential."
        )
    return ua


def _extract_deck_id(deck_url: str) -> str:
    """Extract the deck ID from a Moxfield URL."""
    match = _URL_RE.search(deck_url)
    if not match:
        raise ValueError(
            f"Invalid Moxfield URL: {deck_url!r}. "
            "Expected format: https://www.moxfield.com/decks/<deck_id>"
        )
    return match.group(1)


def fetch_decklist(deck_url: str) -> List[Dict[str, Any]]:
    """Fetch a decklist from the Moxfield API and resolve via Scryfall.

    Parameters
    ----------
    deck_url : str
        Moxfield deck URL (e.g. "https://www.moxfield.com/decks/AbCdEf123").

    Returns
    -------
    list[dict]
        Card dicts in the standard internal format.
    """
    user_agent = _get_user_agent()
    deck_id = _extract_deck_id(deck_url)

    rate_limiter.wait("moxfield")

    resp = requests.get(
        f"{_API_BASE}/{deck_id}",
        headers={"User-Agent": user_agent},
        timeout=30,
    )
    if resp.status_code == 404:
        raise MoxfieldAPIError(f"Deck not found: {deck_id}")
    resp.raise_for_status()

    data = resp.json()

    # Extract card entries from the Moxfield response.
    # Moxfield groups cards under "boards" -> "mainboard"/"commanders"/etc.
    entries: list[tuple[int, str, bool]] = []

    # Commanders
    commanders_board = data.get("boards", {}).get("commanders", {})
    for card_key, card_data in commanders_board.get("cards", {}).items():
        name = card_data.get("card", {}).get("name", card_key)
        qty = card_data.get("quantity", 1)
        entries.append((qty, name, True))

    # Mainboard
    mainboard = data.get("boards", {}).get("mainboard", {})
    for card_key, card_data in mainboard.get("cards", {}).items():
        name = card_data.get("card", {}).get("name", card_key)
        qty = card_data.get("quantity", 1)
        entries.append((qty, name, False))

    if not entries:
        raise MoxfieldAPIError("No cards found in deck")

    return resolve_cards(entries)


def is_configured() -> bool:
    """Check if the Moxfield User-Agent credential is available."""
    return bool(os.environ.get("MOXFIELD_USER_AGENT", "").strip())
