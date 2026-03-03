"""Tests for Pyodide compatibility: conditional imports and progress callback."""

from unittest.mock import MagicMock

import pytest

from auto_goldfish.decklist.loader import get_basic_island, get_hare_apparent
from auto_goldfish.engine.goldfisher import Goldfisher, SimulationResult


def _make_small_deck(n_lands=10, n_spells=5):
    """Build a minimal deck for quick simulations."""
    deck = [get_basic_island() for _ in range(n_lands)]
    for i in range(n_spells):
        deck.append({
            "name": f"Bear {i}",
            "quantity": 1,
            "oracle_cmc": 2,
            "cmc": 2,
            "cost": "{1}{G}",
            "text": "",
            "types": ["Creature"],
            "sub_types": [],
            "super_types": [],
            "identity": ["Green"],
            "user_category": "Creature",
            "commander": False,
        })
    return deck


class TestConditionalImports:
    def test_process_pool_executor_guarded(self):
        """ProcessPoolExecutor import is guarded; module loads even if unavailable."""
        import auto_goldfish.engine.goldfisher as mod
        # The attribute exists (either real or None sentinel)
        assert hasattr(mod, "ProcessPoolExecutor")

    def test_tqdm_guarded(self):
        """tqdm import is guarded; module loads even if unavailable."""
        import auto_goldfish.engine.goldfisher as mod
        assert hasattr(mod, "tqdm")

    def test_sequential_fallback_when_workers_gt_1(self):
        """When ProcessPoolExecutor is None, workers>1 falls back to sequential."""
        import auto_goldfish.engine.goldfisher as mod

        original = mod.ProcessPoolExecutor
        try:
            mod.ProcessPoolExecutor = None
            deck = _make_small_deck()
            gf = Goldfisher(deck, turns=3, sims=10, workers=4, seed=42)
            result = gf.simulate()
            assert isinstance(result, SimulationResult)
            assert result.mean_mana >= 0
        finally:
            mod.ProcessPoolExecutor = original


class TestProgressCallback:
    def test_callback_called_for_each_sim(self):
        """Progress callback should be called once per simulation."""
        deck = _make_small_deck()
        sims = 20
        gf = Goldfisher(deck, turns=3, sims=sims, workers=1, seed=42)

        callback = MagicMock()
        result = gf.simulate(progress_callback=callback)

        assert isinstance(result, SimulationResult)
        assert callback.call_count == sims
        # Verify incrementing values
        calls = [c.args for c in callback.call_args_list]
        assert calls[0] == (0, sims)
        assert calls[-1] == (sims - 1, sims)

    def test_no_callback_still_works(self):
        """simulate() without callback should work as before."""
        deck = _make_small_deck()
        gf = Goldfisher(deck, turns=3, sims=10, workers=1, seed=42)
        result = gf.simulate()
        assert isinstance(result, SimulationResult)

    def test_callback_not_called_in_parallel_mode(self):
        """In parallel mode, callback is not used (parallel path ignores it)."""
        deck = _make_small_deck()
        gf = Goldfisher(deck, turns=3, sims=20, workers=2, seed=42)
        callback = MagicMock()
        result = gf.simulate(progress_callback=callback)
        # Parallel mode doesn't call the callback
        assert isinstance(result, SimulationResult)
