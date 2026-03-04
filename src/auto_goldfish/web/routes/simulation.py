"""Simulation routes -- config page and data APIs for client-side simulation."""

from __future__ import annotations

import glob
import json
import logging
import os
import uuid

from flask import Blueprint, abort, jsonify, render_template, request, send_file

logger = logging.getLogger(__name__)

from auto_goldfish.decklist.loader import get_deckpath, load_decklist, load_overrides, save_overrides
from auto_goldfish.effects.builtin import (
    DiscardCards,
    DrawCards,
    ImmediateMana,
    LandToBattlefield,
    PerCastDraw,
    PerTurnDraw,
    ProduceMana,
    ReduceCost,
)
from auto_goldfish.effects.card_database import DEFAULT_REGISTRY
from auto_goldfish.effects.json_loader import get_effect_schema

# Client-side compute limits (enforced in JS)
MAX_SIMS = 10000
MAX_TURNS = 14
MAX_LAND_SWEEP = 10

bp = Blueprint("simulation", __name__, url_prefix="/sim")



def _effects_to_override(card_effects):
    """Convert a CardEffects instance to the category-based JSON override format."""
    categories = []
    for effect in card_effects.on_play:
        if isinstance(effect, ProduceMana):
            categories.append({"category": "ramp", "immediate": False,
                               "producer": {"mana_amount": effect.amount}})
        elif isinstance(effect, ImmediateMana):
            categories.append({"category": "ramp", "immediate": True,
                               "producer": {"mana_amount": effect.amount}})
        elif isinstance(effect, LandToBattlefield):
            tempo = "tapped" if effect.tapped else "untapped"
            categories.append({"category": "ramp", "immediate": True,
                               "land_to_battlefield": {"count": effect.count, "tempo": tempo}})
        elif isinstance(effect, ReduceCost):
            categories.append({"category": "ramp", "immediate": False,
                               "reducer": {"spell_type": effect.spell_type, "amount": effect.amount}})
        elif isinstance(effect, DrawCards):
            categories.append({"category": "draw", "immediate": True, "amount": effect.amount})
        elif isinstance(effect, DiscardCards):
            categories.append({"category": "discard", "amount": effect.amount})
    for effect in card_effects.per_turn:
        if isinstance(effect, PerTurnDraw):
            categories.append({"category": "draw", "immediate": False,
                               "per_turn": {"amount": effect.amount}})
    for effect in card_effects.cast_trigger:
        if isinstance(effect, PerCastDraw):
            categories.append({"category": "draw", "immediate": False,
                               "per_cast": {"amount": effect.amount, "trigger": effect.trigger}})

    result = {"categories": categories}
    if card_effects.priority:
        result["priority"] = card_effects.priority
    return result


def _describe_effects(card_effects):
    """Build a human-readable description of a CardEffects instance."""
    parts = []
    for effect in card_effects.on_play:
        parts.append(f"{type(effect).__name__}({', '.join(f'{k}={v}' for k, v in vars(effect).items())})" if vars(effect) else type(effect).__name__)
    for effect in card_effects.per_turn:
        parts.append(f"{type(effect).__name__}({', '.join(f'{k}={v}' for k, v in vars(effect).items())})" if vars(effect) else type(effect).__name__)
    for effect in card_effects.cast_trigger:
        parts.append(f"{type(effect).__name__}({', '.join(f'{k}={v}' for k, v in vars(effect).items())})" if vars(effect) else type(effect).__name__)
    for effect in card_effects.mana_function:
        parts.append(type(effect).__name__)
    return ", ".join(parts) if parts else ""


@bp.route("/<deck_name>")
def config(deck_name: str):
    path = get_deckpath(deck_name)
    if not os.path.isfile(path):
        abort(404)

    deck_list = load_decklist(deck_name)
    land_count = sum(
        c.get("quantity", 1) for c in deck_list if "Land" in c.get("types", [])
    )

    saved_overrides = load_overrides(deck_name)

    card_effects_list = []
    for card_dict in deck_list:
        name = card_dict.get("name", "")
        types = card_dict.get("types", [])
        if "Land" in types:
            continue
        effects = DEFAULT_REGISTRY.get(name)
        entry = {
            "name": name,
            "cmc": card_dict.get("cmc", 0),
            "types": types,
            "has_effects": effects is not None,
            "effects_display": _describe_effects(effects) if effects else "",
            "registry_override": _effects_to_override(effects) if effects else None,
        }
        # If this card has a saved override, attach override data for the template
        if name in saved_overrides:
            entry["original_effects"] = entry["effects_display"]
            entry["has_effects"] = True
            entry["effects_display"] = "User override"
            entry["override"] = saved_overrides[name]
        card_effects_list.append(entry)
    card_effects_list.sort(key=lambda c: (not c["has_effects"], c["cmc"], c["name"]))

    # Cards with no built-in effects AND no saved overrides (for auto-show labeler)
    unlabeled_cards = [
        {"name": c["name"], "cmc": c["cmc"], "types": c["types"]}
        for c in card_effects_list
        if not DEFAULT_REGISTRY.get(c["name"]) and c["name"] not in saved_overrides
    ]
    # All non-land cards (for manual "Label Cards" button)
    all_nonland_cards = [
        {"name": c["name"], "cmc": c["cmc"], "types": c["types"]}
        for c in card_effects_list
    ]

    try:
        from auto_goldfish.db.persistence import persist_deck_cards

        persist_deck_cards(deck_name, card_effects_list, saved_overrides)
    except Exception:
        logger.exception("Failed to persist deck cards to DB")

    effect_schema = get_effect_schema()

    return render_template(
        "simulate.html",
        deck_name=deck_name,
        land_count=land_count,
        max_sims=MAX_SIMS,
        max_turns=MAX_TURNS,
        max_land_sweep=MAX_LAND_SWEEP,
        card_effects=card_effects_list,
        effect_schema=effect_schema,
        saved_overrides=saved_overrides,
        unlabeled_cards=unlabeled_cards,
        all_nonland_cards=all_nonland_cards,
    )


@bp.route("/<deck_name>/overrides", methods=["POST"])
def save_overrides_api(deck_name: str):
    path = get_deckpath(deck_name)
    if not os.path.isfile(path):
        abort(404)

    try:
        effect_overrides = request.get_json(force=True) or {}
    except (TypeError, ValueError):
        effect_overrides = {}

    save_overrides(deck_name, effect_overrides)
    return jsonify({"ok": True})


@bp.route("/api/<deck_name>/deck")
def api_deck(deck_name: str):
    """Return the deck card list as JSON."""
    path = get_deckpath(deck_name)
    if not os.path.isfile(path):
        abort(404)
    deck_list = load_decklist(deck_name)
    return jsonify(deck_list)


@bp.route("/api/<deck_name>/effects")
def api_effects(deck_name: str):
    """Return merged effect overrides + default registry as JSON."""
    path = get_deckpath(deck_name)
    if not os.path.isfile(path):
        abort(404)

    saved_overrides = load_overrides(deck_name)
    deck_list = load_decklist(deck_name)

    # Build effects dict: card name -> override JSON format
    effects = {}
    for card_dict in deck_list:
        name = card_dict.get("name", "")
        types = card_dict.get("types", [])
        if "Land" in types:
            continue
        # User override takes precedence
        if name in saved_overrides:
            effects[name] = saved_overrides[name]
        else:
            card_effects = DEFAULT_REGISTRY.get(name)
            if card_effects is not None:
                effects[name] = _effects_to_override(card_effects)

    return jsonify(effects)


@bp.route("/api/wheel")
def api_wheel():
    """Return the wheel filename so the client can build the download URL."""
    project_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    )
    dist_dir = os.path.join(project_root, "dist")
    wheels = sorted(glob.glob(os.path.join(dist_dir, "auto_goldfish-*.whl")))
    if not wheels:
        abort(404)
    filename = os.path.basename(wheels[-1])
    return jsonify({"filename": filename})


@bp.route("/api/wheel/<filename>")
def api_wheel_download(filename: str):
    """Serve a specific wheel file. The .whl extension in the URL is required
    for micropip to recognise this as a wheel rather than a package name."""
    if not filename.endswith(".whl") or "/" in filename or ".." in filename:
        abort(400)
    project_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    )
    wheel_path = os.path.join(project_root, "dist", filename)
    if not os.path.isfile(wheel_path):
        abort(404)
    return send_file(wheel_path, mimetype="application/zip")


@bp.route("/api/<deck_name>/results", methods=["POST"])
def api_save_results(deck_name: str):
    """Persist client-side simulation results to the database."""
    path = get_deckpath(deck_name)
    if not os.path.isfile(path):
        abort(404)

    try:
        body = request.get_json(force=True)
    except Exception:
        return jsonify({"ok": False, "error": "Invalid JSON"}), 400

    if not isinstance(body, dict):
        return jsonify({"ok": False, "error": "Invalid JSON"}), 400

    config = body.get("config", {})
    results = body.get("results", [])

    job_id = uuid.uuid4().hex[:12]

    try:
        from auto_goldfish.db.persistence import get_or_create_deck, save_simulation_run
        from auto_goldfish.db.session import get_session

        with get_session() as session:
            deck = get_or_create_deck(session, deck_name)
            save_simulation_run(session, job_id, deck, config, results)
        logger.info("Persisted client simulation %s for deck %s", job_id, deck_name)
    except Exception:
        logger.exception("Failed to persist client simulation results")

    return jsonify({"ok": True})
