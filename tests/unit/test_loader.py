"""Tests for decklist/loader.py."""

from mana_curve.decklist.loader import get_basic_island, get_hare_apparent


def test_basic_island():
    island = get_basic_island()
    assert island["name"] == "Island"
    assert island["cmc"] == 0
    assert "Land" in island["types"]
    assert island["commander"] is False


def test_hare_apparent():
    hare = get_hare_apparent()
    assert hare["name"] == "Hare Apparent"
    assert hare["cmc"] == 2
    assert "Creature" in hare["types"]
