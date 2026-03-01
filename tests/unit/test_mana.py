"""Tests for engine/mana.py."""

from auto_goldfish.engine.mana import land_mana, mana_rocks
from auto_goldfish.models.game_state import GameState


def test_land_mana():
    gs = GameState()
    gs.lands = [0, 1, 2]
    assert land_mana(gs) == 3


def test_land_mana_empty():
    gs = GameState()
    assert land_mana(gs) == 0


def test_mana_rocks():
    gs = GameState()
    gs.mana_production = 5
    assert mana_rocks(gs) == 5
