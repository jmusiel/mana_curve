"""Unit tests for mana efficiency selection modes."""

import pytest

from auto_goldfish.engine.mana_efficiency import (
    VALID_MANA_EFFICIENCY_MODES,
    select_cards_to_play,
)
from auto_goldfish.models.card import Card
from auto_goldfish.models.game_state import GameState


def _card(name: str, cmc: int, *, ramp: bool = False, draw: bool = False) -> Card:
    c = Card(name=name, cmc=cmc, types=["Creature"])
    c.ramp = ramp
    c.draw = draw
    return c


def _state() -> GameState:
    return GameState()


class TestGreedySelect:
    def test_plays_highest_priority_first(self):
        """Greedy iterates reversed, so last element is played first."""
        cards = [_card("A", 2), _card("B", 3)]  # sorted ascending
        result = select_cards_to_play("greedy", cards, 5, _state())
        # reversed = [B, A]; B costs 3 <= 5, A costs 2 <= 2; both played
        assert len(result) == 2

    def test_skips_unaffordable(self):
        cards = [_card("Cheap", 1), _card("Expensive", 5)]
        result = select_cards_to_play("greedy", cards, 3, _state())
        assert len(result) == 1
        assert result[0].name == "Cheap"

    def test_empty_playables(self):
        assert select_cards_to_play("greedy", [], 10, _state()) == []


class TestManaEfficientSelect:
    def test_maximizes_mana_spent(self):
        """Given 5 mana and cards costing 3 and 3, picks both (costs 6? no, 3+3=6 > 5).
        So pick just one 3. But with 2+3=5, picks both."""
        cards = [_card("Two", 2), _card("Three", 3)]
        result = select_cards_to_play("mana_efficient", cards, 5, _state())
        total = sum(c.cmc for c in result)
        assert total == 5  # 2 + 3 = 5, uses all mana

    def test_prefers_full_mana_usage(self):
        """With 6 mana: {4, 3, 3} -> picks 3+3=6 over just 4."""
        cards = [_card("A", 3), _card("B", 3), _card("C", 4)]
        result = select_cards_to_play("mana_efficient", cards, 6, _state())
        total = sum(c.cmc for c in result)
        assert total == 6

    def test_empty_playables(self):
        assert select_cards_to_play("mana_efficient", [], 10, _state()) == []

    def test_single_card(self):
        cards = [_card("Solo", 3)]
        result = select_cards_to_play("mana_efficient", cards, 5, _state())
        assert len(result) == 1
        assert result[0].name == "Solo"


class TestSpellCountSelect:
    def test_maximizes_card_count(self):
        """With 5 mana: {1, 1, 1, 4} -> picks three 1s (3 cards) over one 4."""
        cards = [_card("A", 1), _card("B", 1), _card("C", 1), _card("D", 4)]
        result = select_cards_to_play("spell_count", cards, 5, _state())
        assert len(result) >= 3
        # Should pick at least the three 1-cost cards
        names = {c.name for c in result}
        assert {"A", "B", "C"}.issubset(names)

    def test_picks_cheaper_cards(self):
        """With 4 mana: {1, 2, 3} -> picks 1+2+... or 1+3 (both 2 cards, but 1+3=4 or 1+2=3).
        Spell count mode should pick 1+2 (2 cards) or 1+3 (2 cards). Both are 2 cards."""
        cards = [_card("A", 1), _card("B", 2), _card("C", 3)]
        result = select_cards_to_play("spell_count", cards, 4, _state())
        assert len(result) == 2


class TestInvalidMode:
    def test_raises_on_invalid(self):
        with pytest.raises(ValueError, match="Invalid mana_efficiency"):
            select_cards_to_play("bogus", [], 10, _state())
