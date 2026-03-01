"""Tests for autocard exporter."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from mana_curve.autocard.exporter import export_to_registry, group_by_effects
from mana_curve.effects.json_loader import load_registry_from_json


_RAMP_LABEL = {
    "effects": [
        {"type": "produce_mana", "slot": "on_play", "params": {"amount": 1}},
    ],
    "metadata": {"ramp": True},
}

_DRAW_LABEL = {
    "effects": [
        {"type": "per_turn_draw", "slot": "per_turn", "params": {"amount": 1}},
    ],
    "metadata": {},
}

_EMPTY_LABEL = {"effects": [], "metadata": {}}


class TestGroupByEffects:
    def test_same_effects_grouped_together(self):
        """3 cards with identical effects -> 1 group."""
        labeled = {
            "Arcane Signet": _RAMP_LABEL,
            "Fellwar Stone": _RAMP_LABEL,
            "Commander's Sphere": _RAMP_LABEL,
        }
        groups = group_by_effects(labeled)
        assert len(groups) == 1
        assert len(groups[0]["cards"]) == 3

    def test_different_effects_separate_groups(self):
        """Cards with different effects -> separate groups."""
        labeled = {
            "Arcane Signet": _RAMP_LABEL,
            "Phyrexian Arena": _DRAW_LABEL,
        }
        groups = group_by_effects(labeled)
        assert len(groups) == 2

    def test_no_effect_cards_grouped(self):
        """No-effect cards grouped into 'Unlabeled / No Effect'."""
        labeled = {
            "Lightning Bolt": _EMPTY_LABEL,
            "Swords to Plowshares": _EMPTY_LABEL,
        }
        groups = group_by_effects(labeled)
        assert len(groups) == 1
        assert groups[0]["group"] == "Unlabeled / No Effect"

    def test_group_defaults_contain_effects_and_metadata(self):
        """Group defaults should have effects and metadata."""
        labeled = {"Sol Ring": {
            "effects": [
                {"type": "produce_mana", "slot": "on_play", "params": {"amount": 2}},
            ],
            "metadata": {"ramp": True},
        }}
        groups = group_by_effects(labeled)
        assert len(groups) == 1
        defaults = groups[0]["defaults"]
        assert "effects" in defaults
        assert defaults["ramp"] is True

    def test_empty_input(self):
        groups = group_by_effects({})
        assert groups == []


class TestExportToRegistry:
    def test_basic_export(self):
        labeled = {
            "Card A": _RAMP_LABEL,
            "Card B": _DRAW_LABEL,
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "output.json"
            export_to_registry(labeled, output=out)

            with open(out) as f:
                data = json.load(f)

        assert data["version"] == 1
        assert len(data["groups"]) == 2

    def test_preserves_existing_registry(self):
        """Cards in existing registry are NOT overwritten."""
        existing = {
            "version": 1,
            "groups": [{
                "group": "Existing",
                "defaults": {"ramp": True, "effects": [
                    {"type": "produce_mana", "slot": "on_play", "params": {"amount": 2}},
                ]},
                "cards": {"Sol Ring": {}},
            }],
        }
        labeled = {
            "Sol Ring": _RAMP_LABEL,  # already exists -> should be skipped
            "New Card": _DRAW_LABEL,   # new -> should be added
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            existing_path = Path(tmpdir) / "existing.json"
            with open(existing_path, "w") as f:
                json.dump(existing, f)

            out = Path(tmpdir) / "output.json"
            export_to_registry(labeled, output=out, existing_path=existing_path)

            with open(out) as f:
                data = json.load(f)

        # First group is the preserved existing one
        assert data["groups"][0]["group"] == "Existing"
        assert "Sol Ring" in data["groups"][0]["cards"]

        # New card added as a new group
        all_card_names = set()
        for g in data["groups"]:
            all_card_names.update(g["cards"].keys())
        assert "New Card" in all_card_names
        assert len(data["groups"]) == 2

    def test_round_trip_through_loader(self):
        """Exported JSON can be loaded back by load_registry_from_json."""
        labeled = {
            "Test Card A": _RAMP_LABEL,
            "Test Card B": _DRAW_LABEL,
            "Test Card C": _EMPTY_LABEL,
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "output.json"
            export_to_registry(labeled, output=out)

            registry = load_registry_from_json(out)

        # Cards with effects are loadable
        assert registry.has("Test Card A")
        assert registry.has("Test Card B")
        # No-effect card is also registered (with empty effect lists)
        assert registry.has("Test Card C")
        assert len(registry) == 3

    def test_export_no_existing(self):
        """Export without an existing registry just writes new groups."""
        labeled = {"Card X": _RAMP_LABEL}
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "output.json"
            export_to_registry(labeled, output=out, existing_path=None)

            with open(out) as f:
                data = json.load(f)
        assert len(data["groups"]) == 1
