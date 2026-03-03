"""Tests for autocard label validator (category format)."""

from __future__ import annotations

import pytest

from auto_goldfish.autocard.validator import validate_label


class TestValidateLabel:
    def test_valid_label_sol_ring(self):
        """Sol Ring style: ramp producer."""
        label = {
            "categories": [
                {"category": "ramp", "immediate": False,
                 "producer": {"mana_amount": 2}},
            ],
            "metadata": {"priority": 0},
        }
        assert validate_label("Sol Ring", label) == []

    def test_valid_label_multi_category(self):
        """The Great Henge style: ramp producer + per_cast draw."""
        label = {
            "categories": [
                {"category": "ramp", "immediate": False,
                 "producer": {"mana_amount": 2}},
                {"category": "draw", "immediate": False,
                 "per_cast": {"amount": 1, "trigger": "creature"}},
            ],
            "metadata": {},
        }
        assert validate_label("The Great Henge", label) == []

    def test_empty_categories_and_metadata(self):
        """No-effect card (e.g. Lightning Bolt) is valid."""
        label = {"categories": [], "metadata": {}}
        assert validate_label("Lightning Bolt", label) == []

    def test_unknown_category(self):
        label = {
            "categories": [
                {"category": "fire_blast"},
            ],
            "metadata": {},
        }
        errors = validate_label("Bad Card", label)
        assert len(errors) == 1
        assert "unknown category" in errors[0]
        assert "fire_blast" in errors[0]

    def test_ramp_missing_variant(self):
        label = {
            "categories": [
                {"category": "ramp", "immediate": False},
            ],
            "metadata": {},
        }
        errors = validate_label("Bad Card", label)
        assert len(errors) == 1
        assert "producer" in errors[0]

    def test_ramp_producer_missing_amount(self):
        label = {
            "categories": [
                {"category": "ramp", "immediate": False,
                 "producer": {}},
            ],
            "metadata": {},
        }
        errors = validate_label("Bad Card", label)
        assert len(errors) == 1
        assert "mana_amount" in errors[0]

    def test_ramp_reducer_invalid_spell_type(self):
        label = {
            "categories": [
                {"category": "ramp", "immediate": False,
                 "reducer": {"spell_type": "planeswalker", "amount": 1}},
            ],
            "metadata": {},
        }
        errors = validate_label("Bad Card", label)
        assert len(errors) == 1
        assert "spell_type" in errors[0]

    def test_draw_immediate_missing_amount(self):
        label = {
            "categories": [
                {"category": "draw", "immediate": True},
            ],
            "metadata": {},
        }
        errors = validate_label("Bad Card", label)
        assert len(errors) == 1
        assert "amount" in errors[0]

    def test_draw_per_cast_invalid_trigger(self):
        label = {
            "categories": [
                {"category": "draw", "immediate": False,
                 "per_cast": {"amount": 1, "trigger": "planeswalker"}},
            ],
            "metadata": {},
        }
        errors = validate_label("Bad Card", label)
        assert len(errors) == 1
        assert "trigger" in errors[0]

    def test_discard_missing_amount(self):
        label = {
            "categories": [
                {"category": "discard"},
            ],
            "metadata": {},
        }
        errors = validate_label("Bad Card", label)
        assert len(errors) == 1
        assert "amount" in errors[0]

    def test_unknown_metadata_key(self):
        label = {
            "categories": [],
            "metadata": {"flying": True},
        }
        errors = validate_label("Bad Card", label)
        assert len(errors) == 1
        assert "unknown metadata key" in errors[0]
        assert "flying" in errors[0]

    def test_metadata_type_priority_must_be_int(self):
        label = {
            "categories": [],
            "metadata": {"priority": "high"},
        }
        errors = validate_label("Bad Card", label)
        assert len(errors) == 1
        assert "priority" in errors[0]
        assert "int" in errors[0]

    def test_metadata_type_ramp_must_be_bool(self):
        label = {
            "categories": [],
            "metadata": {"ramp": 1},
        }
        errors = validate_label("Bad Card", label)
        assert len(errors) == 1
        assert "ramp" in errors[0]
        assert "bool" in errors[0]

    def test_metadata_type_extra_types_must_be_list(self):
        label = {
            "categories": [],
            "metadata": {"extra_types": "land"},
        }
        errors = validate_label("Bad Card", label)
        assert len(errors) == 1
        assert "extra_types" in errors[0]

    def test_missing_categories_key(self):
        label = {"metadata": {}}
        errors = validate_label("Bad Card", label)
        assert len(errors) == 1
        assert "categories" in errors[0]

    def test_missing_metadata_key(self):
        label = {"categories": []}
        errors = validate_label("Bad Card", label)
        assert len(errors) == 1
        assert "metadata" in errors[0]

    def test_multiple_errors(self):
        """Multiple validation failures reported together."""
        label = {
            "categories": [
                {"category": "fake_cat"},
                {"category": "ramp", "immediate": False},
            ],
            "metadata": {"unknown_key": True},
        }
        errors = validate_label("Bad Card", label)
        assert len(errors) == 3

    def test_valid_land_tapped(self):
        label = {
            "categories": [{"category": "land", "tapped": True}],
            "metadata": {},
        }
        assert validate_label("Tolaria West", label) == []

    def test_valid_draw_per_turn(self):
        label = {
            "categories": [
                {"category": "draw", "immediate": False,
                 "per_turn": {"amount": 1}},
            ],
            "metadata": {},
        }
        assert validate_label("Phyrexian Arena", label) == []

    def test_valid_ramp_land_to_battlefield(self):
        label = {
            "categories": [
                {"category": "ramp", "immediate": True,
                 "land_to_battlefield": {"count": 1, "tempo": "tapped"}},
            ],
            "metadata": {},
        }
        assert validate_label("Rampant Growth", label) == []

    def test_valid_draw_and_discard(self):
        label = {
            "categories": [
                {"category": "draw", "immediate": True, "amount": 2},
                {"category": "discard", "amount": 2},
            ],
            "metadata": {},
        }
        assert validate_label("Faithless Looting", label) == []
