"""Integration tests proving effect overrides change simulation outcomes."""

from mana_curve.effects.card_database import DEFAULT_REGISTRY
from mana_curve.effects.json_loader import build_overridden_registry
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


def test_mana_override_increases_mean_mana():
    """Override a creature to ProduceMana(10) -> significantly higher mean_mana."""
    deck = _simple_deck()
    seed = 42
    sims = 200
    turns = 8

    # Baseline (no overrides)
    gf_base = Goldfisher(deck, turns=turns, sims=sims, seed=seed,
                         record_results="quartile")
    r_base = gf_base.simulate()

    # Override: give Creature 0 (cmc=1) a massive mana boost
    overrides = {
        "Creature 0": {
            "effects": [{"type": "produce_mana", "slot": "on_play",
                         "params": {"amount": 10}}],
            "ramp": True,
        }
    }
    registry = build_overridden_registry(DEFAULT_REGISTRY, overrides)
    gf_override = Goldfisher(deck, turns=turns, sims=sims, seed=seed,
                             registry=registry, record_results="quartile")
    r_override = gf_override.simulate()

    assert isinstance(r_base, SimulationResult)
    assert isinstance(r_override, SimulationResult)
    assert r_override.mean_mana > r_base.mean_mana


def test_draw_override_increases_draws():
    """Override a creature to DrawCards(5) on_play -> higher mean_draws."""
    deck = _simple_deck()
    seed = 123
    sims = 200
    turns = 8

    # Baseline
    gf_base = Goldfisher(deck, turns=turns, sims=sims, seed=seed,
                         record_results="quartile")
    r_base = gf_base.simulate()

    # Override: give Creature 1 (cmc=2) a big draw effect
    overrides = {
        "Creature 1": {
            "effects": [{"type": "draw_cards", "slot": "on_play",
                         "params": {"amount": 5}}],
        }
    }
    registry = build_overridden_registry(DEFAULT_REGISTRY, overrides)
    gf_override = Goldfisher(deck, turns=turns, sims=sims, seed=seed,
                             registry=registry, record_results="quartile")
    r_override = gf_override.simulate()

    assert r_override.mean_draws > r_base.mean_draws


def test_override_adds_effect_to_unregistered_card():
    """A card with no registry entry gets an effect via override -> mean_mana increases."""
    deck = _simple_deck(num_lands=35, num_spells=60)
    # Add a custom card with no effects in the registry
    deck.append({
        "name": "Custom Creature",
        "cmc": 1,
        "cost": "{1}",
        "text": "",
        "types": ["Creature"],
        "commander": False,
    })
    seed = 77
    sims = 200
    turns = 8

    # Baseline (Custom Creature has no effects)
    gf_base = Goldfisher(deck, turns=turns, sims=sims, seed=seed,
                         record_results="quartile")
    r_base = gf_base.simulate()

    # Override: give it mana production
    overrides = {
        "Custom Creature": {
            "effects": [{"type": "produce_mana", "slot": "on_play",
                         "params": {"amount": 3}}],
            "ramp": True,
        }
    }
    registry = build_overridden_registry(DEFAULT_REGISTRY, overrides)
    gf_override = Goldfisher(deck, turns=turns, sims=sims, seed=seed,
                             registry=registry, record_results="quartile")
    r_override = gf_override.simulate()

    assert r_override.mean_mana > r_base.mean_mana


def test_no_overrides_matches_baseline():
    """Empty overrides dict {} produces identical results to no registry arg."""
    deck = _simple_deck()
    seed = 42
    sims = 200
    turns = 5

    # Run with default registry (no explicit registry arg)
    gf1 = Goldfisher(deck, turns=turns, sims=sims, seed=seed,
                     record_results="quartile")
    r1 = gf1.simulate()

    # Run with build_overridden_registry({}) -> should be identical copy
    registry = build_overridden_registry(DEFAULT_REGISTRY, {})
    gf2 = Goldfisher(deck, turns=turns, sims=sims, seed=seed,
                     registry=registry, record_results="quartile")
    r2 = gf2.simulate()

    assert r1.mean_mana == r2.mean_mana
    assert r1.mean_lands == r2.mean_lands
    assert r1.mean_draws == r2.mean_draws
    assert r1.mean_mulls == r2.mean_mulls
    assert r1.consistency == r2.consistency
