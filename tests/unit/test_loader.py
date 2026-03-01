"""Tests for decklist/loader.py."""

import json
import os

from auto_goldfish.decklist.loader import (
    get_basic_island,
    get_hare_apparent,
    get_overrides_path,
    load_overrides,
    save_overrides,
)


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


def test_load_overrides_missing_file(tmp_path, monkeypatch):
    """load_overrides returns {} when the overrides file doesn't exist."""
    monkeypatch.setattr(
        "auto_goldfish.decklist.loader.get_overrides_path",
        lambda name: str(tmp_path / "nonexistent.overrides.json"),
    )
    result = load_overrides("nonexistent")
    assert result == {}


def test_save_and_load_overrides_round_trip(tmp_path, monkeypatch):
    """Saving then loading overrides returns the same data."""
    overrides_file = str(tmp_path / "test.overrides.json")
    monkeypatch.setattr(
        "auto_goldfish.decklist.loader.get_overrides_path",
        lambda name: overrides_file,
    )
    overrides = {
        "Sol Ring": {
            "effects": [{"type": "produce_mana", "slot": "on_play", "params": {"amount": 5}}],
            "ramp": True,
        }
    }
    path = save_overrides("test", overrides)
    assert path == overrides_file
    assert os.path.isfile(path)

    loaded = load_overrides("test")
    assert loaded == overrides
