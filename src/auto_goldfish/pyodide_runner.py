"""Entry point for running simulations in Pyodide (client-side WebAssembly).

This module is loaded by the Web Worker and called from JavaScript.
It orchestrates a full simulation run using only sequential execution
(workers=1), which is the only option available in the Pyodide environment.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional

from auto_goldfish.effects.card_database import DEFAULT_REGISTRY
from auto_goldfish.effects.json_loader import build_overridden_registry
from auto_goldfish.engine.goldfisher import Goldfisher
from auto_goldfish.engine.mulligan import CurveAwareMulligan
from auto_goldfish.metrics.reporter import result_to_dict


def run_simulation(
    deck_json: str,
    config_json: str,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> str:
    """Entry point called from JavaScript via Pyodide.

    Args:
        deck_json: JSON string of deck card list (list of card dicts).
        config_json: JSON string with simulation configuration:
            - turns (int): Number of turns per game (default 10)
            - sims (int): Number of simulations per land count (default 1000)
            - min_lands (int): Minimum land count to sweep
            - max_lands (int): Maximum land count to sweep
            - seed (int|null): Random seed (default null)
            - record_results (str): Detail level - "quartile"/"decile"/"centile"
            - effect_overrides (dict): Card name -> override JSON format
            - mulligan (str): Mulligan strategy - "default"/"curve_aware"
        progress_callback: Optional callable(current, total) for progress
            updates. Called during each simulation run. The total reflects
            sims * number_of_land_counts.

    Returns:
        JSON string of list[result_to_dict(result)] for each land count.
    """
    deck_list: List[Dict[str, Any]] = json.loads(deck_json)
    config: Dict[str, Any] = json.loads(config_json)

    turns = config.get("turns", 10)
    sims = config.get("sims", 1000)
    min_lands = config.get("min_lands")
    max_lands = config.get("max_lands")
    seed = config.get("seed")
    record_results = config.get("record_results", "quartile")
    effect_overrides = config.get("effect_overrides", {})
    mulligan_type = config.get("mulligan", "default")

    # Build registry with overrides
    registry = None
    if effect_overrides:
        registry = build_overridden_registry(DEFAULT_REGISTRY, effect_overrides)

    # Build mulligan strategy
    mulligan_strategy = None
    if mulligan_type == "curve_aware":
        mulligan_strategy = CurveAwareMulligan()

    goldfisher = Goldfisher(
        deck_list,
        turns=turns,
        sims=sims,
        verbose=False,
        record_results=record_results,
        seed=seed,
        workers=1,  # Always sequential in Pyodide
        mulligan_strategy=mulligan_strategy,
        registry=registry,
    )

    # Determine land range
    if min_lands is None:
        min_lands = goldfisher.land_count
    if max_lands is None:
        max_lands = goldfisher.land_count

    num_land_counts = max_lands - min_lands + 1
    results: List[Dict[str, Any]] = []

    for land_idx, land_count in enumerate(range(min_lands, max_lands + 1)):
        goldfisher.set_lands(land_count, cuts=[])

        # Wrap progress callback to report global progress across all land counts
        land_callback = None
        if progress_callback is not None:
            offset = land_idx * sims

            def land_callback(current: int, total: int, _offset: int = offset) -> None:
                progress_callback(
                    _offset + current,
                    num_land_counts * sims,
                )

        result = goldfisher.simulate(progress_callback=land_callback)
        results.append(result_to_dict(result))

    return json.dumps(results)
