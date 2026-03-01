"""Simulation routes -- config, run, poll, results."""

from __future__ import annotations

import json
import os

from flask import Blueprint, abort, flash, jsonify, make_response, render_template, request

from mana_curve.decklist.loader import get_deckpath, load_decklist, load_overrides, save_overrides
from mana_curve.effects.card_database import DEFAULT_REGISTRY
from mana_curve.effects.json_loader import get_effect_schema
from mana_curve.web.services.simulation_runner import SimulationRunner

# Web UI compute limits (CLI remains unrestricted)
MAX_SIMS = 10000
MAX_TURNS = 14
MAX_LAND_SWEEP = 10

bp = Blueprint("simulation", __name__, url_prefix="/sim")

# Single runner shared across requests (app-level singleton)
_runner = SimulationRunner()


def get_runner() -> SimulationRunner:
    return _runner


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
        }
        # If this card has a saved override, attach override data for the template
        if name in saved_overrides:
            entry["has_effects"] = True
            entry["effects_display"] = "User override"
            entry["override"] = saved_overrides[name]
        card_effects_list.append(entry)
    card_effects_list.sort(key=lambda c: (not c["has_effects"], c["cmc"], c["name"]))

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


@bp.route("/status/<job_id>")
def status(job_id: str):
    runner = get_runner()
    status = runner.get_status(job_id)
    if status is None:
        abort(404)

    if status["status"] == "completed":
        resp = make_response(render_template("partials/job_status.html", **status))
        resp.headers["HX-Redirect"] = f"/sim/results/{job_id}"
        return resp

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
