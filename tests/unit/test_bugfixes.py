"""Tests for the three bug fixes in the simulation engine.

Bug 1: _get_playables was marking cards as cast even when not played
Bug 2: mana_spent_when_played used card.cmc instead of get_current_cost
Bug 3: Bootstrap CI used unseeded np.random
"""

import random

import numpy as np
import pytest

from auto_goldfish.effects.registry import CardEffects, EffectRegistry
from auto_goldfish.effects.builtin import ReduceCost
from auto_goldfish.engine.goldfisher import Goldfisher, SimulationResult


def _simple_deck(num_lands=37, num_spells=62):
    """Build a simple deck with lands and vanilla creatures."""
    deck = []
    deck.append({
        "name": "Test Commander",
        "cmc": 4, "cost": "{2}{U}{B}", "text": "",
        "types": ["Creature"], "commander": True,
    })
    for i in range(num_lands):
        deck.append({
            "name": f"Island {i}", "cmc": 0, "cost": "", "text": "",
            "types": ["Land"], "commander": False,
        })
    for i in range(num_spells):
        cmc = (i % 6) + 1
        deck.append({
            "name": f"Creature {i}", "cmc": cmc, "cost": f"{{{cmc}}}",
            "text": "", "types": ["Creature"], "commander": False,
        })
    return deck


class TestBug1CardCastTurnOnlyOnPlay:
    """Bug 1: card_cast_turn should only be set when a card is actually played,
    not when it is merely identified as playable."""

    def test_unplayed_affordable_card_not_marked_as_cast(self):
        """If a card is affordable but not selected by the mana efficiency
        algorithm, it should NOT have card_cast_turn set."""
        deck = _simple_deck(num_lands=37, num_spells=62)
        gf = Goldfisher(
            deck, turns=5, sims=100, seed=42,
            record_results=None,
            mana_efficiency="greedy",
        )
        result = gf.simulate()

        # Run a single game manually and check card_cast_turn
        random.seed(42)
        state = gf._reset()
        gf._mulligan(state)

        # Take a single turn
        played_cards = gf._take_turn(state)
        played_indices = {c.index for c in played_cards if c.spell}

        # Check that only actually played cards have card_cast_turn set
        for i, turn in enumerate(state.card_cast_turn):
            if turn is not None:
                card = gf.decklist[i]
                if card.spell and not card.land:
                    assert i in played_indices, (
                        f"Card {card.name} (index {i}) was marked as cast on turn {turn} "
                        f"but was not in the played set"
                    )

    def test_card_cast_turn_set_on_play(self):
        """Cards that ARE played should have their cast turn recorded."""
        deck = _simple_deck(num_lands=37, num_spells=62)
        gf = Goldfisher(
            deck, turns=3, sims=1, seed=42,
            record_results=None,
        )

        random.seed(42)
        state = gf._reset()
        gf._mulligan(state)

        for turn in range(3):
            played = gf._take_turn(state)
            for card in played:
                if card.spell and not card.commander:
                    assert state.card_cast_turn[card.index] is not None, (
                        f"Card {card.name} was played but card_cast_turn not set"
                    )


class TestBug2ManaSpentUsesCurrentCost:
    """Bug 2: mana_spent_when_played should use get_current_cost(state),
    not card.cmc, to account for cost reductions."""

    def test_mana_spent_reflects_cost_reduction(self):
        """When a cost reduction is active, mana_spent_when_played should
        be the reduced cost, not the base CMC."""
        # Build a deck with a known creature
        deck = []
        deck.append({
            "name": "Test Commander", "cmc": 4, "cost": "{2}{U}{B}",
            "text": "", "types": ["Creature"], "commander": True,
        })
        for i in range(37):
            deck.append({
                "name": f"Island {i}", "cmc": 0, "cost": "", "text": "",
                "types": ["Land"], "commander": False,
            })
        # Add a 5-mana creature that we'll play with cost reduction
        deck.append({
            "name": "Expensive Creature", "cmc": 5, "cost": "{5}",
            "text": "", "types": ["Creature"], "commander": False,
        })
        # Filler
        for i in range(61):
            deck.append({
                "name": f"Filler {i}", "cmc": 6, "cost": "{6}",
                "text": "", "types": ["Creature"], "commander": False,
            })

        gf = Goldfisher(
            deck, turns=10, sims=1, seed=None,
            record_results=None,
        )

        # Manually set up a game state with cost reduction
        random.seed(99)
        state = gf._reset()
        gf._mulligan(state)

        # Apply a creature cost reduction of 2
        state.creature_cost_reduction = 2

        # Find the expensive creature and put it in hand if not there
        expensive = gf.deckdict.get("Expensive Creature")
        if expensive is not None:
            # Force it into hand
            if expensive.index not in state.hand:
                state.deck.remove(expensive.index)
                expensive.zone = state.hand
                state.hand.append(expensive.index)

            # Ensure enough mana (play several turns to get lands)
            for _ in range(6):
                gf._take_turn(state)

            # Now check if it was played
            if expensive.mana_spent_when_played > 0:
                # With creature_cost_reduction=2, a 5-cmc creature should cost 3
                assert expensive.mana_spent_when_played == 3, (
                    f"Expected mana_spent_when_played=3 (5 cmc - 2 reduction), "
                    f"got {expensive.mana_spent_when_played}"
                )


class TestBug3BootstrapCISeeded:
    """Bug 3: Bootstrap CI should be reproducible with a fixed seed."""

    def test_bootstrap_ci_reproducible(self):
        """Two runs with the same seed should produce identical CI values."""
        deck = _simple_deck()

        gf1 = Goldfisher(deck, turns=5, sims=200, seed=42, record_results=None)
        result1 = gf1.simulate()

        gf2 = Goldfisher(deck, turns=5, sims=200, seed=42, record_results=None)
        result2 = gf2.simulate()

        assert result1.ci_consistency == result2.ci_consistency, (
            f"Bootstrap CI not reproducible: {result1.ci_consistency} != {result2.ci_consistency}"
        )
        assert result1.ci_mean_mana == result2.ci_mean_mana
        assert result1.ci_mean_bad_turns == result2.ci_mean_bad_turns

    def test_bootstrap_ci_different_seeds_differ(self):
        """Runs with different seeds should generally produce different CIs."""
        deck = _simple_deck()

        gf1 = Goldfisher(deck, turns=5, sims=500, seed=42, record_results=None)
        result1 = gf1.simulate()

        gf2 = Goldfisher(deck, turns=5, sims=500, seed=99, record_results=None)
        result2 = gf2.simulate()

        # The means will likely differ, so CIs will differ
        # (This is a probabilistic test but very likely to pass)
        assert result1.ci_mean_mana != result2.ci_mean_mana or \
               result1.mean_mana != result2.mean_mana
