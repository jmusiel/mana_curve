"""Dashboard route -- list saved decks."""

from __future__ import annotations

import json
import os

from flask import Blueprint, render_template

from auto_goldfish.decklist.loader import get_deckpath

bp = Blueprint("dashboard", __name__)


def _list_saved_decks() -> list[dict]:
    """Return metadata for each saved deck."""
    project_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    )
    decks_dir = os.path.join(project_root, "decks")
    if not os.path.isdir(decks_dir):
        return []

    decks = []
    for name in sorted(os.listdir(decks_dir)):
        deck_json = os.path.join(decks_dir, name, f"{name}.json")
        if os.path.isfile(deck_json):
            try:
                with open(deck_json) as f:
                    cards = json.load(f)
                card_count = len(cards)
                commanders = [c["name"] for c in cards if c.get("commander")]
                land_count = sum(
                    1 for c in cards if "Land" in c.get("types", [])
                )
            except (json.JSONDecodeError, KeyError):
                card_count = 0
                commanders = []
                land_count = 0
            decks.append({
                "name": name,
                "card_count": card_count,
                "commanders": commanders,
                "land_count": land_count,
            })
    return decks


@bp.route("/")
def index():
    decks = _list_saved_decks()
    return render_template("dashboard.html", decks=decks)
