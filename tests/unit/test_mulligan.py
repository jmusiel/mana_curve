"""Tests for engine/mulligan.py."""

from mana_curve.engine.mulligan import CurveAwareMulligan, DefaultMulligan
from mana_curve.models.card import Card
from mana_curve.models.game_state import GameState


def _make_state_with_hand(cards: list[Card]) -> GameState:
    """Build a GameState with cards in hand, decklist populated."""
    state = GameState()
    state.decklist = cards
    state.hand = list(range(len(cards)))
    for i, card in enumerate(cards):
        card.index = i
        card.zone = state.hand
    return state


def _land(index=0):
    return Card(name="Island", cmc=0, cost="", text="", types=["land"], index=index)


def _ramp_rock(index=0):
    c = Card(name="Sol Ring", cmc=1, cost="{1}", text="", types=["artifact"], index=index)
    c.ramp = True
    return c


def _creature(cmc=2, index=0):
    return Card(name=f"Bear {index}", cmc=cmc, cost=f"{{{cmc}}}", text="",
                types=["creature"], index=index)


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


class TestCurveAwareMulligan:
    def test_keep_3_lands_with_early_spell(self):
        m = CurveAwareMulligan()
        cards = [_land(0), _land(1), _land(2),
                 _creature(2, 3), _creature(4, 4), _creature(5, 5), _creature(6, 6)]
        state = _make_state_with_hand(cards)
        assert m.should_keep(state, 7, 3) is True

    def test_keep_2_lands_with_ramp(self):
        m = CurveAwareMulligan()
        cards = [_land(0), _land(1), _ramp_rock(2),
                 _creature(3, 3), _creature(4, 4), _creature(5, 5), _creature(6, 6)]
        state = _make_state_with_hand(cards)
        assert m.should_keep(state, 7, 2) is True

    def test_mull_2_lands_no_ramp(self):
        m = CurveAwareMulligan()
        cards = [_land(0), _land(1), _creature(4, 2),
                 _creature(5, 3), _creature(6, 4), _creature(6, 5), _creature(6, 6)]
        state = _make_state_with_hand(cards)
        assert m.should_keep(state, 7, 2) is False

    def test_mull_5_lands(self):
        m = CurveAwareMulligan()
        cards = [_land(0), _land(1), _land(2), _land(3), _land(4),
                 _creature(2, 5), _creature(3, 6)]
        state = _make_state_with_hand(cards)
        assert m.should_keep(state, 7, 5) is False

    def test_keep_after_first_mulligan(self):
        m = CurveAwareMulligan()
        state = _make_state_with_hand([_land(0)])
        assert m.should_keep(state, 6, 0) is True

    def test_keep_3_lands_no_early_spells_fallback(self):
        """3-4 lands is still keepable even without early plays."""
        m = CurveAwareMulligan()
        cards = [_land(0), _land(1), _land(2),
                 _creature(5, 3), _creature(6, 4), _creature(7, 5), _creature(7, 6)]
        state = _make_state_with_hand(cards)
        assert m.should_keep(state, 7, 3) is True
