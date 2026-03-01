"""Simulation routes -- config, run, poll, results."""

from __future__ import annotations

import os

from flask import Blueprint, abort, jsonify, make_response, render_template, request

from mana_curve.decklist.loader import get_deckpath
from mana_curve.web.services.simulation_runner import SimulationRunner

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
    return render_template("simulate.html", deck_name=deck_name)


@bp.route("/<deck_name>/run", methods=["POST"])
def run(deck_name: str):
    path = get_deckpath(deck_name)
    if not os.path.isfile(path):
        abort(404)

    seed_val = request.form.get("seed", "").strip()
    workers_val = int(request.form.get("workers", 0))

    sim_config = {
        "turns": int(request.form.get("turns", 10)),
        "sims": int(request.form.get("sims", 1000)),
        "min_lands": int(request.form.get("min_lands", 36)),
        "max_lands": int(request.form.get("max_lands", 39)),
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
