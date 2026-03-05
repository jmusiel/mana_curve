"""Tests for otag registry loader."""

import json
import tempfile
from pathlib import Path

import pytest

from auto_goldfish.effects.otag_loader import (
    get_matching_cards,
    has_cheaper_than_mv,
    load_otag_registry,
)


@pytest.fixture
def sample_registry():
    return {
        "updated": "2026-03-04",
        "cards": {
            "Sol Ring": ["ramp", "cheaper-than-mv"],
            "Arcane Signet": ["ramp"],
            "Harmonize": ["card-advantage"],
            "Rhystic Study": ["card-advantage", "ramp"],
        },
    }


@pytest.fixture
def registry_file(sample_registry, tmp_path):
    path = tmp_path / "otag_registry.json"
    path.write_text(json.dumps(sample_registry))
    return path


class TestLoadOtagRegistry:
    def test_loads_from_file(self, registry_file, sample_registry):
        result = load_otag_registry(registry_file)
        assert result == sample_registry

    def test_missing_file_returns_empty(self, tmp_path):
        result = load_otag_registry(tmp_path / "nonexistent.json")
        assert result == {"updated": "", "cards": {}}

    def test_loads_default_path(self):
        """Loading from default path should not crash (file may be empty seed)."""
        result = load_otag_registry()
        assert "cards" in result
        assert "updated" in result


class TestGetMatchingCards:
    def test_returns_matching_cards(self, sample_registry):
        names = ["Sol Ring", "Arcane Signet", "Grizzly Bears"]
        result = get_matching_cards(names, sample_registry)
        assert "Sol Ring" in result
        assert "Arcane Signet" in result
        assert "Grizzly Bears" not in result

    def test_returns_otags(self, sample_registry):
        result = get_matching_cards(["Sol Ring"], sample_registry)
        assert result["Sol Ring"] == ["ramp", "cheaper-than-mv"]

    def test_empty_names(self, sample_registry):
        result = get_matching_cards([], sample_registry)
        assert result == {}

    def test_no_matches(self, sample_registry):
        result = get_matching_cards(["Nonexistent Card"], sample_registry)
        assert result == {}

    def test_empty_registry(self):
        result = get_matching_cards(["Sol Ring"], {"cards": {}})
        assert result == {}


class TestHasCheaperThanMv:
    def test_true_when_present(self, sample_registry):
        assert has_cheaper_than_mv("Sol Ring", sample_registry) is True

    def test_false_when_absent(self, sample_registry):
        assert has_cheaper_than_mv("Arcane Signet", sample_registry) is False

    def test_false_for_unknown_card(self, sample_registry):
        assert has_cheaper_than_mv("Grizzly Bears", sample_registry) is False

    def test_empty_registry(self):
        assert has_cheaper_than_mv("Sol Ring", {"cards": {}}) is False
