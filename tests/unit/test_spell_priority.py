"""Unit tests for spell priority sort modes."""

import pytest

from auto_goldfish.engine.spell_priority import (
    VALID_SPELL_PRIORITIES,
    get_spell_sort_key,
)
from auto_goldfish.models.card import Card


def _card(name: str, cmc: int, *, ramp: bool = False, draw: bool = False,
          priority: int = 0, types: list[str] | None = None) -> Card:
    """Build a minimal Card for sorting tests."""
    types = types or ["Creature"]
    c = Card(name=name, cmc=cmc, types=types)
    c.ramp = ramp
    c.draw = draw
    c.priority = priority
    return c


class TestDefaultMode:
    def test_returns_none_key(self):
        assert get_spell_sort_key("priority_then_cmc") is None

    def test_sorted_by_priority_then_cmc(self):
        cards = [
            _card("Big", 5, priority=0),
            _card("Small", 1, priority=0),
            _card("HighPri", 3, priority=-1),
        ]
        result = sorted(cards)
        assert [c.name for c in result] == ["HighPri", "Small", "Big"]


class TestRampFirst:
    def test_ramp_before_value(self):
        key = get_spell_sort_key("ramp_first")
        cards = [
            _card("Value3", 3),
            _card("Ramp2", 2, ramp=True),
            _card("Draw4", 4, draw=True),
        ]
        result = sorted(cards, key=key)
        names = [c.name for c in result]
        assert names.index("Ramp2") < names.index("Draw4")
        assert names.index("Draw4") < names.index("Value3")

    def test_within_ramp_sorted_by_cmc(self):
        key = get_spell_sort_key("ramp_first")
        cards = [
            _card("Ramp3", 3, ramp=True),
            _card("Ramp1", 1, ramp=True),
        ]
        result = sorted(cards, key=key)
        assert [c.name for c in result] == ["Ramp1", "Ramp3"]


class TestValueFirst:
    def test_value_before_ramp_and_draw(self):
        key = get_spell_sort_key("value_first")
        cards = [
            _card("Ramp2", 2, ramp=True),
            _card("Value3", 3),
            _card("Draw4", 4, draw=True),
        ]
        result = sorted(cards, key=key)
        names = [c.name for c in result]
        assert names.index("Value3") < names.index("Draw4")
        assert names.index("Value3") < names.index("Ramp2")


class TestDrawFirst:
    def test_draw_before_others(self):
        key = get_spell_sort_key("draw_first")
        cards = [
            _card("Value3", 3),
            _card("Draw2", 2, draw=True),
            _card("Ramp1", 1, ramp=True),
        ]
        result = sorted(cards, key=key)
        assert result[0].name == "Draw2"


class TestHighestCmcFirst:
    def test_highest_cmc_sorts_first(self):
        key = get_spell_sort_key("highest_cmc_first")
        cards = [
            _card("Small", 1),
            _card("Big", 5),
            _card("Mid", 3),
        ]
        result = sorted(cards, key=key)
        assert [c.name for c in result] == ["Big", "Mid", "Small"]


class TestInvalidMode:
    def test_raises_on_invalid(self):
        with pytest.raises(ValueError, match="Invalid spell_priority"):
            get_spell_sort_key("nonexistent")


class TestValidPriorities:
    def test_all_modes_return_key(self):
        for mode in VALID_SPELL_PRIORITIES:
            # Should not raise
            get_spell_sort_key(mode)
