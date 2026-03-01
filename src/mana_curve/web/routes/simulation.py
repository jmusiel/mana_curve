"""Simulation routes -- config, run, poll, results."""

from __future__ import annotations

import os

from flask import Blueprint, abort, flash, jsonify, make_response, render_template, request

from mana_curve.decklist.loader import get_deckpath, load_decklist
from mana_curve.web.services.simulation_runner import SimulationRunner

# Web UI compute limits (CLI remains unrestricted)
MAX_SIMS = 2000
MAX_TURNS = 14
MAX_LAND_SWEEP = 10

bp = Blueprint("simulation", __name__, url_prefix="/sim")

# Single runner shared across requests (app-level singleton)
_runner = SimulationRunner()


def get_runner() -> SimulationRunner:
    return _runner


@bp.route("/<deck_name>")
def config(deck_name: str):
    path = get_deckpath(deck_name)
    if not os.path.isfile(path):
        abort(404)
    cards = load_decklist(deck_name)
    land_count = sum(
        c.get("quantity", 1) for c in cards if "Land" in c.get("types", [])
    )
    return render_template(
        "simulate.html",
        deck_name=deck_name,
        land_count=land_count,
        max_sims=MAX_SIMS,
        max_turns=MAX_TURNS,
        max_land_sweep=MAX_LAND_SWEEP,
    )


@bp.route("/<deck_name>/run", methods=["POST"])
def run(deck_name: str):
    path = get_deckpath(deck_name)
    if not os.path.isfile(path):
        abort(404)

    seed_val = request.form.get("seed", "").strip()
    workers_val = int(request.form.get("workers", 0))

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
