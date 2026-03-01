"""Tests for engine/mulligan.py."""

from mana_curve.engine.mulligan import DefaultMulligan
from mana_curve.models.game_state import GameState


class TestDefaultMulligan:
    def test_keep_3_lands(self):
        m = DefaultMulligan()
        assert m.should_keep(GameState(), 7, 3) is True

    def test_keep_4_lands(self):
        m = DefaultMulligan()
        assert m.should_keep(GameState(), 7, 4) is True

    def test_mull_0_lands(self):
        m = DefaultMulligan()
        assert m.should_keep(GameState(), 7, 0) is False

    def test_mull_5_lands(self):
        m = DefaultMulligan()
        assert m.should_keep(GameState(), 7, 5) is False

    def test_keep_small_hand(self):
        m = DefaultMulligan()
        assert m.should_keep(GameState(), 6, 0) is True

    def test_mull_2_lands_7_cards(self):
        m = DefaultMulligan()
        assert m.should_keep(GameState(), 7, 2) is False
