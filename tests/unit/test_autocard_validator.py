"""Tests for autocard label validator."""

from __future__ import annotations

import pytest

from auto_goldfish.autocard.validator import validate_label


class TestValidateLabel:
    def test_valid_label_sol_ring(self):
        """Sol Ring style: produce_mana + ramp metadata."""
        label = {
            "effects": [
                {"type": "produce_mana", "slot": "on_play", "params": {"amount": 2}},
            ],
            "metadata": {"ramp": True, "priority": 0},
        }
        assert validate_label("Sol Ring", label) == []

    def test_valid_label_multi_effect(self):
        """The Great Henge style: on_play + cast_trigger."""
        label = {
            "effects": [
                {"type": "produce_mana", "slot": "on_play", "params": {"amount": 2}},
                {"type": "per_cast_draw", "slot": "cast_trigger", "params": {"creature": 1}},
            ],
            "metadata": {"ramp": True},
        }
        assert validate_label("The Great Henge", label) == []

    def test_empty_effects_and_metadata(self):
        """No-effect card (e.g. Lightning Bolt) is valid."""
        label = {"effects": [], "metadata": {}}
        assert validate_label("Lightning Bolt", label) == []

    def test_unknown_effect_type(self):
        label = {
            "effects": [
                {"type": "fire_blast", "slot": "on_play", "params": {}},
            ],
            "metadata": {},
        }
        errors = validate_label("Bad Card", label)
        assert len(errors) == 1
        assert "unknown type" in errors[0]
        assert "fire_blast" in errors[0]

    def test_unknown_slot(self):
        label = {
            "effects": [
                {"type": "produce_mana", "slot": "on_death", "params": {"amount": 1}},
            ],
            "metadata": {},
        }
        errors = validate_label("Bad Card", label)
        assert len(errors) == 1
        assert "unknown slot" in errors[0]
        assert "on_death" in errors[0]

    def test_invalid_param_name(self):
        label = {
            "effects": [
                {"type": "produce_mana", "slot": "on_play", "params": {"power": 5}},
            ],
            "metadata": {},
        }
        errors = validate_label("Bad Card", label)
        assert len(errors) == 1
        assert "unknown param" in errors[0]
        assert "power" in errors[0]

    def test_unknown_metadata_key(self):
        label = {
            "effects": [],
            "metadata": {"flying": True},
        }
        errors = validate_label("Bad Card", label)
        assert len(errors) == 1
        assert "unknown metadata key" in errors[0]
        assert "flying" in errors[0]

    def test_metadata_type_priority_must_be_int(self):
        label = {
            "effects": [],
            "metadata": {"priority": "high"},
        }
        errors = validate_label("Bad Card", label)
        assert len(errors) == 1
        assert "priority" in errors[0]
        assert "int" in errors[0]

    def test_metadata_type_ramp_must_be_bool(self):
        label = {
            "effects": [],
            "metadata": {"ramp": 1},
        }
        errors = validate_label("Bad Card", label)
        assert len(errors) == 1
        assert "ramp" in errors[0]
        assert "bool" in errors[0]

    def test_metadata_type_extra_types_must_be_list(self):
        label = {
            "effects": [],
            "metadata": {"extra_types": "land"},
        }
        errors = validate_label("Bad Card", label)
        assert len(errors) == 1
        assert "extra_types" in errors[0]

    def test_missing_effects_key(self):
        label = {"metadata": {}}
        errors = validate_label("Bad Card", label)
        assert len(errors) == 1
        assert "effects" in errors[0]

    def test_missing_metadata_key(self):
        label = {"effects": []}
        errors = validate_label("Bad Card", label)
        assert len(errors) == 1
        assert "metadata" in errors[0]

    def test_multiple_errors(self):
        """Multiple validation failures reported together."""
        label = {
            "effects": [
                {"type": "fake_type", "slot": "on_play", "params": {}},
                {"type": "produce_mana", "slot": "bad_slot", "params": {}},
            ],
            "metadata": {"unknown_key": True},
        }
        errors = validate_label("Bad Card", label)
        assert len(errors) == 3
