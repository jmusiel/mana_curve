"""Deck import and viewer routes."""

from __future__ import annotations

import json
import os

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for

from auto_goldfish.decklist.archidekt import fetch_and_save, fetch_decklist
from auto_goldfish.decklist.loader import get_deckpath, load_decklist

bp = Blueprint("decks", __name__, url_prefix="/decks")


@bp.route("/import")
def import_form():
    return render_template("import.html")


@bp.route("/import", methods=["POST"])
def import_deck():
    default_url = "https://archidekt.com/decks/81320/the_rr_connection"

    deck_url = request.form.get("deck_url", "").strip() or default_url
    deck_name = request.form.get("deck_name", "").strip()

    # If no name provided, extract it from the URL's last path segment
    if not deck_name:
        deck_name = deck_url.rstrip("/").rsplit("/", 1)[-1]

    try:
        fetch_and_save(deck_url, deck_name)
    except Exception as e:
        flash(f"Import failed: {e}", "error")
        return render_template("import.html"), 400

    flash(f"Deck '{deck_name}' imported successfully.", "success")
    return redirect(url_for("decks.view_deck", name=deck_name))


@bp.route("/import/api", methods=["POST"])
def import_deck_api():
    """Fetch deck from Archidekt and return JSON (no server-side save)."""
    try:
        body = request.get_json(force=True)
    except Exception:
        return jsonify({"ok": False, "error": "Invalid JSON"}), 400

    default_url = "https://archidekt.com/decks/81320/the_rr_connection"
    deck_url = (body.get("deck_url") or "").strip() or default_url
    deck_name = (body.get("deck_name") or "").strip()

    if not deck_name:
        deck_name = deck_url.rstrip("/").rsplit("/", 1)[-1]

    try:
        cards = fetch_decklist(deck_url)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400

    return jsonify({"ok": True, "deck_name": deck_name, "cards": cards})


@bp.route("/<name>", methods=["GET", "POST"])
def view_deck(name: str):
    if request.method == "POST":
        try:
            body = request.get_json(force=True)
        except Exception:
            abort(400)
        cards = body.get("cards", [])
        is_local = True
    else:
        path = get_deckpath(name)
        if not os.path.isfile(path):
            abort(404)
        cards = load_decklist(name)
        is_local = False

    # Group cards by user_category (or "Other")
    groups: dict[str, list] = {}
    commanders = []
    for card in cards:
        if card.get("commander"):
            commanders.append(card)
            continue
        category = card.get("user_category") or card.get("default_category") or "Other"
        groups.setdefault(category, []).append(card)

    # Sort groups: Land last, Commander first handled separately
    sorted_groups = sorted(groups.items(), key=lambda x: (x[0] == "Land", x[0]))

    total_cards = len(cards)
    land_count = sum(1 for c in cards if "Land" in c.get("types", []))

    return render_template(
        "deck_view.html",
        name=name,
        commanders=commanders,
        groups=sorted_groups,
        total_cards=total_cards,
        land_count=land_count,
        is_local=is_local,
    )
