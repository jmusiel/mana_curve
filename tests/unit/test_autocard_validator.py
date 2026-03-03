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


class TestConservativeValidation:
    """Conservative mode rejects disallowed types, slots, and metadata."""

    def test_accepts_valid_conservative_label(self):
        """A label using only conservative types/slots/metadata passes."""
        label = {
            "effects": [
                {"type": "produce_mana", "slot": "on_play", "params": {"amount": 2}},
                {"type": "per_turn_draw", "slot": "per_turn", "params": {"amount": 1}},
            ],
            "metadata": {"ramp": True, "priority": 2},
        }
        errors = validate_label("Good Card", label, conservative=True)
        assert errors == []

    def test_accepts_empty_label(self):
        """Empty effects and metadata is always valid."""
        label = {"effects": [], "metadata": {}}
        errors = validate_label("Empty Card", label, conservative=True)
        assert errors == []

    def test_rejects_tutor_to_hand(self):
        label = {
            "effects": [
                {"type": "tutor_to_hand", "slot": "on_play",
                 "params": {"targets": ["Sol Ring"]}},
            ],
            "metadata": {},
        }
        errors = validate_label("Tutor Card", label, conservative=True)
        assert len(errors) == 1
        assert "disallowed type" in errors[0]
        assert "tutor_to_hand" in errors[0]

    def test_rejects_per_cast_draw(self):
        label = {
            "effects": [
                {"type": "per_cast_draw", "slot": "cast_trigger",
                 "params": {"creature": 1}},
            ],
            "metadata": {},
        }
        errors = validate_label("Cast Draw Card", label, conservative=True)
        assert any("disallowed type" in e for e in errors)

    def test_rejects_cryptolith_rites_mana(self):
        label = {
            "effects": [
                {"type": "cryptolith_rites_mana", "slot": "mana_function",
                 "params": {}},
            ],
            "metadata": {},
        }
        errors = validate_label("Rites Card", label, conservative=True)
        assert any("disallowed type" in e for e in errors)

    def test_rejects_enchantment_sanctum_mana(self):
        label = {
            "effects": [
                {"type": "enchantment_sanctum_mana", "slot": "mana_function",
                 "params": {}},
            ],
            "metadata": {},
        }
        errors = validate_label("Sanctum Card", label, conservative=True)
        assert any("disallowed type" in e for e in errors)

    def test_rejects_cast_trigger_slot(self):
        label = {
            "effects": [
                {"type": "draw_cards", "slot": "cast_trigger",
                 "params": {"amount": 1}},
            ],
            "metadata": {},
        }
        errors = validate_label("Bad Slot Card", label, conservative=True)
        assert len(errors) == 1
        assert "disallowed slot" in errors[0]
        assert "cast_trigger" in errors[0]

    def test_rejects_mana_function_slot(self):
        label = {
            "effects": [
                {"type": "produce_mana", "slot": "mana_function",
                 "params": {"amount": 1}},
            ],
            "metadata": {},
        }
        errors = validate_label("Bad Slot Card", label, conservative=True)
        assert len(errors) == 1
        assert "disallowed slot" in errors[0]
        assert "mana_function" in errors[0]

    def test_rejects_is_land_tutor_metadata(self):
        label = {
            "effects": [],
            "metadata": {"is_land_tutor": True},
        }
        errors = validate_label("Tutor Meta Card", label, conservative=True)
        assert len(errors) == 1
        assert "disallowed metadata" in errors[0]
        assert "is_land_tutor" in errors[0]

    def test_allows_disallowed_types_when_not_conservative(self):
        """Non-conservative mode still accepts all types/slots."""
        label = {
            "effects": [
                {"type": "per_cast_draw", "slot": "cast_trigger",
                 "params": {"creature": 1}},
                {"type": "cryptolith_rites_mana", "slot": "mana_function",
                 "params": {}},
            ],
            "metadata": {"is_land_tutor": True},
        }
        errors = validate_label("Full Card", label, conservative=False)
        assert errors == []
