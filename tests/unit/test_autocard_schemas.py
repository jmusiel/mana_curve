"""Tests for autocard ScryfallCard schema."""

from __future__ import annotations

import pytest

from auto_goldfish.autocard.schemas import ScryfallCard


@pytest.fixture
def sol_ring_dict():
    return {
        "name": "Sol Ring",
        "mana_cost": "{1}",
        "cmc": 1.0,
        "type_line": "Artifact",
        "oracle_text": "{T}: Add {C}{C}.",
        "colors": [],
        "color_identity": [],
        "keywords": [],
        "edhrec_rank": 1,
        "layout": "normal",
        "card_faces": None,
        "produced_mana": ["C"],
    }


@pytest.fixture
def double_faced_dict():
    return {
        "name": "Delver of Secrets // Insectile Aberration",
        "mana_cost": "{U} // ",
        "cmc": 1.0,
        "type_line": "Creature — Human Wizard // Creature — Human Insect",
        "oracle_text": (
            "At the beginning of your upkeep, look at the top card of your library. "
            "You may reveal that card. If an instant or sorcery card is revealed this way, "
            "transform Delver of Secrets."
            " // "
            "Flying"
        ),
        "colors": ["U"],
        "color_identity": ["U"],
        "keywords": ["Flying", "Transform"],
        "edhrec_rank": 5000,
        "layout": "transform",
        "card_faces": [
            {
                "name": "Delver of Secrets",
                "mana_cost": "{U}",
                "oracle_text": (
                    "At the beginning of your upkeep, look at the top card of your library. "
                    "You may reveal that card. If an instant or sorcery card is revealed this way, "
                    "transform Delver of Secrets."
                ),
            },
            {
                "name": "Insectile Aberration",
                "mana_cost": "",
                "oracle_text": "Flying",
            },
        ],
        "produced_mana": [],
    }


class TestScryfallCardSerialization:
    def test_round_trip(self, sol_ring_dict):
        card = ScryfallCard.from_dict(sol_ring_dict)
        assert card.to_dict() == sol_ring_dict

    def test_from_dict_basic_fields(self, sol_ring_dict):
        card = ScryfallCard.from_dict(sol_ring_dict)
        assert card.name == "Sol Ring"
        assert card.mana_cost == "{1}"
        assert card.cmc == 1.0
        assert card.type_line == "Artifact"
        assert card.oracle_text == "{T}: Add {C}{C}."
        assert card.colors == []
        assert card.color_identity == []
        assert card.edhrec_rank == 1
        assert card.produced_mana == ["C"]

    def test_from_dict_defaults(self):
        minimal = {
            "name": "Test Card",
            "mana_cost": "{2}",
            "cmc": 2.0,
            "type_line": "Artifact",
            "oracle_text": "",
            "colors": [],
            "color_identity": [],
            "keywords": [],
        }
        card = ScryfallCard.from_dict(minimal)
        assert card.edhrec_rank is None
        assert card.layout == "normal"
        assert card.card_faces is None
        assert card.produced_mana == []

    def test_round_trip_double_faced(self, double_faced_dict):
        card = ScryfallCard.from_dict(double_faced_dict)
        result = card.to_dict()
        assert result == double_faced_dict
        assert card.layout == "transform"
        assert len(card.card_faces) == 2
        assert " // " in card.oracle_text

    def test_to_dict_produces_json_serializable(self, sol_ring_dict):
        """Verify to_dict() output can be serialized to JSON."""
        import json

        card = ScryfallCard.from_dict(sol_ring_dict)
        json_str = json.dumps(card.to_dict())
        assert isinstance(json_str, str)


class TestScryfallCardFromScryfall:
    def test_from_scryfall_normal_card(self):
        """Test from_scryfall_object with a mock normal card (property access)."""

        class MockCard:
            name = "Sol Ring"
            mana_cost = "{1}"
            cmc = 1.0
            type_line = "Artifact"
            oracle_text = "{T}: Add {C}{C}."
            colors = []
            color_identity = []
            keywords = []
            edhrec_rank = 1
            layout = "normal"
            card_faces = None
            produced_mana = ["C"]

        card = ScryfallCard.from_scryfall_object(MockCard())
        assert card.name == "Sol Ring"
        assert card.oracle_text == "{T}: Add {C}{C}."
        assert card.card_faces is None
        assert card.produced_mana == ["C"]

    def test_from_scryfall_double_faced(self):
        """Test from_scryfall_object with a mock double-faced card."""

        class MockDFC:
            name = "Delver of Secrets // Insectile Aberration"
            mana_cost = "{U}"
            cmc = 1.0
            type_line = "Creature — Human Wizard // Creature — Human Insect"
            oracle_text = ""
            colors = ["U"]
            color_identity = ["U"]
            keywords = ["Flying", "Transform"]
            edhrec_rank = 5000
            layout = "transform"
            card_faces = [
                {"oracle_text": "Look at the top card", "mana_cost": "{U}"},
                {"oracle_text": "Flying", "mana_cost": ""},
            ]
            produced_mana = []

        card = ScryfallCard.from_scryfall_object(MockDFC())
        assert " // " in card.oracle_text
        assert "Look at the top card" in card.oracle_text
        assert "Flying" in card.oracle_text
        assert card.mana_cost == "{U} // "
        assert card.card_faces is not None
        assert len(card.card_faces) == 2

    def test_from_scryfall_missing_produced_mana(self):
        """Cards without produced_mana should default to empty list."""

        class MockNoMana:
            name = "Lightning Bolt"
            mana_cost = "{R}"
            cmc = 1.0
            type_line = "Instant"
            oracle_text = "Deal 3 damage."
            colors = ["R"]
            color_identity = ["R"]
            keywords = []
            edhrec_rank = 100
            layout = "normal"
            card_faces = None

            @property
            def produced_mana(self):
                raise AttributeError("no produced mana")

        card = ScryfallCard.from_scryfall_object(MockNoMana())
        assert card.produced_mana == []
