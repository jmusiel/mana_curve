"""Integration tests for the fast (CRN-paired racing) optimizer."""

import json

from auto_goldfish.engine.goldfisher import Goldfisher
from auto_goldfish.optimization.candidate_cards import ALL_CANDIDATES
from auto_goldfish.optimization.deck_config import DeckConfig
from auto_goldfish.optimization.fast_optimizer import FastDeckOptimizer


def _simple_deck(num_lands: int = 37, num_spells: int = 62) -> list[dict]:
    """Build a simple deck with lands and vanilla creatures."""
    deck = []
    deck.append({
        "name": "Test Commander",
        "cmc": 4,
        "cost": "{2}{U}{B}",
        "text": "",
        "types": ["Creature"],
        "commander": True,
    })
    for i in range(num_lands):
        deck.append({
            "name": f"Island {i}",
            "cmc": 0,
            "cost": "",
            "text": "",
            "types": ["Land"],
            "commander": False,
        })
    for i in range(num_spells):
        cmc = (i % 6) + 1
        deck.append({
            "name": f"Creature {i}",
            "cmc": cmc,
            "cost": f"{{{cmc}}}",
            "text": "",
            "types": ["Creature"],
            "commander": False,
        })
    return deck


class TestSimulateSingleGame:
    """Verify simulate_single_game matches simulate() game logic."""

    def test_matches_simulate_mana_values(self):
        """simulate_single_game returns same values as simulate() inner loop."""
        deck = _simple_deck()
        gf = Goldfisher(deck, turns=10, sims=20, seed=100, record_results="quartile")

        # Run full simulation and collect per-game primary values
        result = gf.simulate()

        # Now run individual games with the same seeds
        single_values = []
        for j in range(20):
            val = gf.simulate_single_game(100 + j)
            single_values.append(val)

        # The simulate() method builds primary_list the same way
        # Re-run to get the raw primary values
        gf2 = Goldfisher(deck, turns=10, sims=20, seed=100, record_results="quartile")
        # We need to compare against what simulate() would produce
        # Since both use the same seed+j pattern, they should match
        import random
        expected = []
        for j in range(20):
            random.seed(100 + j)
            state = gf2._reset()
            gf2._mulligan(state)
            game_mana_value = 0
            game_mana_draw = 0
            game_mana_ramp = 0
            for _turn in range(10):
                played = gf2._take_turn(state)
                for card in played:
                    if card.spell:
                        cost = card.mana_spent_when_played
                        if card.draw:
                            game_mana_draw += cost
                        elif card.ramp:
                            game_mana_ramp += cost
                        else:
                            game_mana_value += cost
            # Default mana_mode is "value_draw"
            expected.append(float(game_mana_value + game_mana_draw))

        assert single_values == expected

    def test_deterministic_with_seed(self):
        """Same seed produces same result."""
        deck = _simple_deck()
        gf = Goldfisher(deck, turns=10, sims=10, seed=42, record_results="quartile")
        v1 = gf.simulate_single_game(42)
        v2 = gf.simulate_single_game(42)
        assert v1 == v2

    def test_different_seeds_different_results(self):
        """Different seeds generally produce different results."""
        deck = _simple_deck()
        gf = Goldfisher(deck, turns=10, sims=10, seed=42, record_results="quartile")
        values = [gf.simulate_single_game(seed) for seed in range(100)]
        # Not all the same (overwhelmingly unlikely with 100 random games)
        assert len(set(values)) > 1


class TestFastDeckOptimizerIntegration:
    """Integration tests for FastDeckOptimizer."""

    def test_runs_and_returns_results(self):
        """FastDeckOptimizer completes and returns ranked results."""
        deck = _simple_deck()
        gf = Goldfisher(deck, turns=5, sims=50, seed=42, record_results="quartile")
        enabled = {
            cid: c for cid, c in ALL_CANDIDATES.items()
            if cid in ("draw_2cmc_2", "ramp_2cmc_1")
        }

        optimizer = FastDeckOptimizer(
            goldfisher=gf,
            candidates=enabled,
            swap_mode=False,
            max_draw=1,
            max_ramp=1,
            land_range=1,
            optimize_for="mean_mana",
            batch_size=10,
            min_games=20,
            max_sims_per_config=60,
        )

        results = optimizer.run(final_sims=50, final_top_k=3)
        assert len(results) > 0
        assert len(results) <= 3

        for config, result_dict in results:
            assert isinstance(config, DeckConfig)
            assert "mean_mana" in result_dict
            assert "consistency" in result_dict

    def test_consistency_optimization(self):
        """FastDeckOptimizer can optimize for consistency."""
        deck = _simple_deck()
        gf = Goldfisher(deck, turns=5, sims=50, seed=42, record_results="quartile")
        enabled = {
            cid: c for cid, c in ALL_CANDIDATES.items()
            if cid in ("draw_2cmc_2", "ramp_2cmc_1")
        }

        optimizer = FastDeckOptimizer(
            goldfisher=gf,
            candidates=enabled,
            swap_mode=False,
            max_draw=1,
            max_ramp=1,
            land_range=1,
            optimize_for="consistency",
            batch_size=10,
            min_games=20,
            max_sims_per_config=60,
        )

        results = optimizer.run(final_sims=50, final_top_k=3)
        assert len(results) > 0

        # Results should be sorted by consistency descending
        scores = [r[1]["consistency"] for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_progress_callback(self):
        """Progress callbacks are called during optimization."""
        deck = _simple_deck()
        gf = Goldfisher(deck, turns=5, sims=50, seed=42, record_results="quartile")
        enabled = {
            cid: c for cid, c in ALL_CANDIDATES.items()
            if cid in ("draw_2cmc_2", "ramp_2cmc_1")
        }

        optimizer = FastDeckOptimizer(
            goldfisher=gf,
            candidates=enabled,
            swap_mode=False,
            max_draw=1,
            max_ramp=1,
            land_range=1,
            optimize_for="mean_mana",
            batch_size=10,
            min_games=20,
            max_sims_per_config=60,
        )

        enum_calls = []
        eval_calls = []

        results = optimizer.run(
            final_sims=50,
            final_top_k=3,
            enum_progress=lambda c, t: enum_calls.append((c, t)),
            eval_progress=lambda c, t: eval_calls.append((c, t)),
        )

        assert len(enum_calls) > 0
        assert len(eval_calls) > 0

    def test_few_configs_returns_results(self):
        """With no candidates (land-only), optimizer still returns results."""
        deck = _simple_deck()
        gf = Goldfisher(deck, turns=5, sims=50, seed=42, record_results="quartile")

        optimizer = FastDeckOptimizer(
            goldfisher=gf,
            candidates={},  # no candidates = only land deltas
            swap_mode=False,
            max_draw=0,
            max_ramp=0,
            land_range=1,  # 3 land deltas: -1, 0, +1
            optimize_for="mean_mana",
        )

        results = optimizer.run(final_sims=50, final_top_k=5)
        assert len(results) >= 1
        assert len(results) <= 5
        for config, result_dict in results:
            assert isinstance(config, DeckConfig)
            assert "mean_mana" in result_dict
