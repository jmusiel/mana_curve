"""Tests for wizard prioritization logic."""

import pytest

from auto_goldfish.web.wizard import build_wizard_card_list


@pytest.fixture
def deck_cards():
    return [
        {"name": "Sol Ring", "cmc": 1, "types": ["Artifact"]},
        {"name": "Arcane Signet", "cmc": 2, "types": ["Artifact"]},
        {"name": "Harmonize", "cmc": 4, "types": ["Sorcery"]},
        {"name": "Grizzly Bears", "cmc": 2, "types": ["Creature"]},
        {"name": "Rhystic Study", "cmc": 3, "types": ["Enchantment"]},
    ]


@pytest.fixture
def otag_registry():
    return {
        "updated": "2026-03-04",
        "cards": {
            "Sol Ring": ["ramp", "cheaper-than-mv"],
            "Arcane Signet": ["ramp"],
            "Harmonize": ["card-advantage"],
            "Rhystic Study": ["card-advantage"],
        },
    }


class TestBuildWizardCardListWithoutDB:
    def test_filters_to_otag_matched(self, deck_cards, otag_registry):
        result = build_wizard_card_list(deck_cards, {}, otag_registry)
        names = [c["name"] for c in result]
        assert "Grizzly Bears" not in names
        assert "Sol Ring" in names
        assert len(result) == 4

    def test_attaches_otags(self, deck_cards, otag_registry):
        result = build_wizard_card_list(deck_cards, {}, otag_registry)
        sol = next(c for c in result if c["name"] == "Sol Ring")
        assert sol["otags"] == ["ramp", "cheaper-than-mv"]

    def test_cheaper_than_mv_flag(self, deck_cards, otag_registry):
        result = build_wizard_card_list(deck_cards, {}, otag_registry)
        sol = next(c for c in result if c["name"] == "Sol Ring")
        signet = next(c for c in result if c["name"] == "Arcane Signet")
        assert sol["cheaper_than_mv"] is True
        assert signet["cheaper_than_mv"] is False

    def test_prior_annotation_from_overrides(self, deck_cards, otag_registry):
        overrides = {"Sol Ring": {"categories": [{"category": "ramp"}]}}
        result = build_wizard_card_list(deck_cards, overrides, otag_registry)
        sol = next(c for c in result if c["name"] == "Sol Ring")
        assert sol["prior_annotation"] == {"categories": [{"category": "ramp"}]}

    def test_prior_annotation_from_registry_override(self, deck_cards, otag_registry):
        # Add registry_override to card dict
        deck_cards_with_reg = [
            {**c, "registry_override": {"categories": [{"category": "draw"}]}}
            if c["name"] == "Harmonize" else c
            for c in deck_cards
        ]
        result = build_wizard_card_list(deck_cards_with_reg, {}, otag_registry)
        harm = next(c for c in result if c["name"] == "Harmonize")
        assert harm["prior_annotation"] == {"categories": [{"category": "draw"}]}

    def test_all_group_1_without_db(self, deck_cards, otag_registry):
        result = build_wizard_card_list(deck_cards, {}, otag_registry)
        assert all(c["priority_group"] == 1 for c in result)

    def test_sorted_by_cmc(self, deck_cards, otag_registry):
        result = build_wizard_card_list(deck_cards, {}, otag_registry)
        cmcs = [c["cmc"] for c in result]
        assert cmcs == sorted(cmcs)

    def test_empty_registry(self, deck_cards):
        result = build_wizard_card_list(deck_cards, {}, {"cards": {}})
        assert result == []

    def test_empty_deck(self, otag_registry):
        result = build_wizard_card_list([], {}, otag_registry)
        assert result == []


class TestBuildWizardCardListWithDB:
    def test_p1_for_never_annotated(self, deck_cards, otag_registry):
        stats = {
            "Sol Ring": {"human_count": 0, "has_human": False, "is_controversial": False,
                         "latest_effects_json": None, "latest_source": None},
        }
        result = build_wizard_card_list(deck_cards, {}, otag_registry, annotation_stats=stats)
        sol = next(c for c in result if c["name"] == "Sol Ring")
        assert sol["priority_group"] == 1

    def test_p1_for_controversial(self, deck_cards, otag_registry):
        stats = {
            "Sol Ring": {"human_count": 2, "has_human": True, "is_controversial": True,
                         "latest_effects_json": '{}', "latest_source": "human"},
        }
        result = build_wizard_card_list(deck_cards, {}, otag_registry, annotation_stats=stats)
        sol = next(c for c in result if c["name"] == "Sol Ring")
        assert sol["priority_group"] == 1

    def test_settled_cards_get_p2_or_p3(self, deck_cards, otag_registry):
        stats = {
            "Sol Ring": {"human_count": 1, "has_human": True, "is_controversial": False,
                         "latest_effects_json": '{}', "latest_source": "human"},
            "Arcane Signet": {"human_count": 1, "has_human": True, "is_controversial": False,
                              "latest_effects_json": '{}', "latest_source": "human"},
            "Harmonize": {"human_count": 1, "has_human": True, "is_controversial": False,
                          "latest_effects_json": '{}', "latest_source": "human"},
            "Rhystic Study": {"human_count": 1, "has_human": True, "is_controversial": False,
                              "latest_effects_json": '{}', "latest_source": "human"},
        }
        result = build_wizard_card_list(deck_cards, {}, otag_registry, annotation_stats=stats)
        groups = {c["priority_group"] for c in result}
        # All are settled, so some should be P2 (up to 3) and rest P3
        assert 2 in groups or 3 in groups
        p2_count = sum(1 for c in result if c["priority_group"] == 2)
        assert p2_count <= 3

    def test_p1_sorted_before_p2(self, deck_cards, otag_registry):
        stats = {
            "Sol Ring": {"human_count": 0, "has_human": False, "is_controversial": False,
                         "latest_effects_json": None, "latest_source": None},
            "Arcane Signet": {"human_count": 1, "has_human": True, "is_controversial": False,
                              "latest_effects_json": '{}', "latest_source": "human"},
            "Harmonize": {"human_count": 1, "has_human": True, "is_controversial": False,
                          "latest_effects_json": '{}', "latest_source": "human"},
            "Rhystic Study": {"human_count": 1, "has_human": True, "is_controversial": False,
                              "latest_effects_json": '{}', "latest_source": "human"},
        }
        result = build_wizard_card_list(deck_cards, {}, otag_registry, annotation_stats=stats)
        groups = [c["priority_group"] for c in result]
        # P1 cards should come before P2/P3
        assert groups[0] == 1

    def test_missing_stats_treated_as_no_annotation(self, deck_cards, otag_registry):
        # Only provide stats for some cards
        stats = {
            "Sol Ring": {"human_count": 1, "has_human": True, "is_controversial": False,
                         "latest_effects_json": '{}', "latest_source": "human"},
        }
        result = build_wizard_card_list(deck_cards, {}, otag_registry, annotation_stats=stats)
        # Cards not in stats should be P1
        signet = next(c for c in result if c["name"] == "Arcane Signet")
        assert signet["priority_group"] == 1
