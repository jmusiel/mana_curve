"""Tests for mana_curve.models.game_state."""

from mana_curve.models.game_state import GameState


def test_default_state():
    gs = GameState()
    assert gs.turn == 0
    assert gs.hand == []
    assert gs.deck == []
    assert gs.mana_production == 0
    assert gs.treasure == 0
    assert gs.creatures_played == 0


def test_state_is_mutable():
    gs = GameState()
    gs.mana_production = 5
    gs.turn = 3
    gs.hand.append(0)
    assert gs.mana_production == 5
    assert gs.turn == 3
    assert gs.hand == [0]


def test_cost_reduction_defaults():
    gs = GameState()
    assert gs.nonpermanent_cost_reduction == 0
    assert gs.permanent_cost_reduction == 0
    assert gs.spell_cost_reduction == 0
    assert gs.creature_cost_reduction == 0
    assert gs.enchantment_cost_reduction == 0
