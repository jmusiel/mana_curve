"""Integration tests for the goldfisher engine."""

import random

from mana_curve.engine.goldfisher import Goldfisher, SimulationResult


def _simple_deck(num_lands: int = 37, num_spells: int = 62) -> list[dict]:
    """Build a simple deck with lands and vanilla creatures."""
    deck = []
    # Commander
    deck.append({
        "name": "Test Commander",
        "cmc": 4,
        "cost": "{2}{U}{B}",
        "text": "",
        "types": ["Creature"],
        "commander": True,
    })
    # Lands
    for i in range(num_lands):
        deck.append({
            "name": f"Island {i}",
            "cmc": 0,
            "cost": "",
            "text": "",
            "types": ["Land"],
            "commander": False,
        })
    # Creatures at various costs
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


def test_simulate_completes():
    """Simulation runs without errors and returns a SimulationResult."""
    random.seed(42)
    deck = _simple_deck()
    gf = Goldfisher(deck, turns=5, sims=50, record_results="quartile")
    result = gf.simulate()
    assert isinstance(result, SimulationResult)
    assert result.mean_mana > 0
    assert result.mean_lands > 0


def test_simulate_with_effects_cards():
    """Simulation works with cards that have registered effects."""
    random.seed(42)
    deck = _simple_deck(num_lands=35, num_spells=60)
    # Add Sol Ring and Phyrexian Arena
    deck.append({
        "name": "Sol Ring",
        "cmc": 1,
        "cost": "{1}",
        "text": "",
        "types": ["Artifact"],
        "commander": False,
    })
    deck.append({
        "name": "Phyrexian Arena",
        "cmc": 3,
        "cost": "{1}{B}{B}",
        "text": "",
        "types": ["Enchantment"],
        "commander": False,
    })
    gf = Goldfisher(deck, turns=5, sims=50, record_results="quartile")
    result = gf.simulate()
    assert isinstance(result, SimulationResult)
    assert result.mean_mana > 0


def test_as_row():
    result = SimulationResult(land_count=37, mean_mana=15.5, consistency=0.9)
    row = result.as_row()
    assert row[0] == 37
    assert row[1] == 15.5
    assert len(row) == 13


def test_set_lands():
    """set_lands adjusts land count correctly."""
    deck = _simple_deck(num_lands=35, num_spells=64)
    gf = Goldfisher(deck, turns=5, sims=10, record_results="quartile")
    original = gf.land_count
    gf.set_lands(original + 2)
    assert gf.land_count == original + 2
