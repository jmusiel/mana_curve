"""Tests for decklist/builder.py."""

from auto_goldfish.decklist.builder import adjust_land_count
from auto_goldfish.decklist.loader import get_basic_island


def _make_creature(name: str, cmc: int = 2) -> dict:
    return {
        "name": name,
        "cmc": cmc,
        "types": ["Creature"],
        "commander": False,
    }


def _make_land(name: str = "Island") -> dict:
    return get_basic_island() | {"name": name}


def test_add_lands():
    deck = [_make_creature("A"), _make_land("Island")]
    result = adjust_land_count(deck, 3)
    lands = [c for c in result if "Land" in c.get("types", [])]
    assert len(lands) == 3


def test_remove_lands():
    deck = [_make_creature("A"), _make_land("Island"), _make_land("Plains"), _make_land("Swamp")]
    result = adjust_land_count(deck, 1)
    lands = [c for c in result if "Land" in c.get("types", [])]
    assert len(lands) == 1


def test_no_change():
    deck = [_make_creature("A"), _make_land("Island"), _make_land("Plains")]
    result = adjust_land_count(deck, 2)
    lands = [c for c in result if "Land" in c.get("types", [])]
    assert len(lands) == 2
    assert len(result) == 3
