"""Simulation routes -- config, run, poll, results."""

from __future__ import annotations

import json
import os

from flask import Blueprint, abort, flash, jsonify, render_template, request

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
from auto_goldfish.web.services.simulation_runner import SimulationRunner

# Web UI compute limits (CLI remains unrestricted)
MAX_SIMS = 10000
MAX_TURNS = 14
MAX_LAND_SWEEP = 10

bp = Blueprint("simulation", __name__, url_prefix="/sim")

# Single runner shared across requests (app-level singleton)
_runner = SimulationRunner()


def get_runner() -> SimulationRunner:
    return _runner


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


@bp.route("/<deck_name>/run", methods=["POST"])
def run(deck_name: str):
    path = get_deckpath(deck_name)
    if not os.path.isfile(path):
        abort(404)

    seed_val = request.form.get("seed", "").strip()
    workers_val = int(request.form.get("workers", 0))

    # Parse effect overrides JSON (empty dict if missing or invalid)
    overrides_raw = request.form.get("effect_overrides", "{}").strip()
    try:
        effect_overrides = json.loads(overrides_raw) if overrides_raw else {}
    except (json.JSONDecodeError, TypeError):
        effect_overrides = {}

    # Persist overrides to disk (even if empty, to clear previous overrides)
    save_overrides(deck_name, effect_overrides)

    turns = int(request.form.get("turns", 10))
    sims = int(request.form.get("sims", 1000))
    min_lands = int(request.form.get("min_lands", 36))
    max_lands = int(request.form.get("max_lands", 39))

    # Server-side validation (web UI limits)
    errors = []
    if sims > MAX_SIMS:
        errors.append(f"Simulations cannot exceed {MAX_SIMS}.")
    if turns > MAX_TURNS:
        errors.append(f"Turns cannot exceed {MAX_TURNS}.")
    if min_lands > max_lands:
        errors.append("Min lands must be less than or equal to max lands.")
    if max_lands - min_lands > MAX_LAND_SWEEP:
        errors.append(f"Land range cannot exceed {MAX_LAND_SWEEP}.")
    if errors:
        for e in errors:
            flash(e, "error")
        return render_template("partials/validation_error.html", errors=errors), 400

    sim_config = {
        "turns": turns,
        "sims": sims,
        "min_lands": min_lands,
        "max_lands": max_lands,
        "record_results": request.form.get("record_results", "quartile"),
        "seed": int(seed_val) if seed_val else None,
        "workers": workers_val if workers_val > 0 else (os.cpu_count() or 1),
        "mulligan": request.form.get("mulligan", "default"),
        "effect_overrides": effect_overrides,
    }

    runner = get_runner()
    job_id = runner.submit(deck_name, sim_config)
    status = runner.get_status(job_id)
    return render_template("partials/job_status.html", **status)


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


@bp.route("/status/<job_id>")
def status(job_id: str):
    runner = get_runner()
    status = runner.get_status(job_id)
    if status is None:
        abort(404)

    if status["status"] == "completed":
        return render_template("partials/results_content.html", **status)

    return render_template("partials/job_status.html", **status)


@bp.route("/results/<job_id>")
def results(job_id: str):
    runner = get_runner()
    status = runner.get_status(job_id)
    if status is None or status["status"] != "completed":
        abort(404)
    return render_template("results.html", **status)


@bp.route("/api/results/<job_id>")
def api_results(job_id: str):
    runner = get_runner()
    status = runner.get_status(job_id)
    if status is None or status["status"] != "completed":
        abort(404)
    return jsonify(status["results"])
