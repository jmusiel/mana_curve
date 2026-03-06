"""Tests for the Scryfall card resolver."""

import json
from unittest.mock import patch, MagicMock

import pytest

from auto_goldfish.decklist.card_resolver import (
    CardResolutionError,
    resolve_cards,
    _parse_type_line,
    _infer_category,
    _scryfall_to_card_dict,
)
from auto_goldfish.decklist import rate_limiter


@pytest.fixture(autouse=True)
def reset_limiter():
    rate_limiter.reset()
    yield
    rate_limiter.reset()


class TestParseTypeLine:
    def test_basic_land(self):
        sup, types, sub = _parse_type_line("Basic Land \u2014 Island")
        assert sup == ["Basic"]
        assert types == ["Land"]
        assert sub == ["Island"]

    def test_legendary_creature(self):
        sup, types, sub = _parse_type_line("Legendary Creature \u2014 Rat Rogue")
        assert sup == ["Legendary"]
        assert types == ["Creature"]
        assert sub == ["Rat", "Rogue"]

    def test_artifact_no_subtype(self):
        sup, types, sub = _parse_type_line("Artifact")
        assert sup == []
        assert types == ["Artifact"]
        assert sub == []

    def test_dfc_type_line(self):
        sup, types, sub = _parse_type_line("Sorcery // Land")
        # Only front face used
        assert types == ["Sorcery"]

    def test_enchantment_creature(self):
        sup, types, sub = _parse_type_line("Enchantment Creature \u2014 God")
        assert types == ["Enchantment", "Creature"]
        assert sub == ["God"]


class TestInferCategory:
    def test_land(self):
        assert _infer_category(["Land"]) == "Land"

    def test_creature(self):
        assert _infer_category(["Creature"]) == "Creature"

    def test_instant(self):
        assert _infer_category(["Instant"]) == "Instant/Sorcery"

    def test_artifact(self):
        assert _infer_category(["Artifact"]) == "Artifact"

    def test_unknown(self):
        assert _infer_category([]) == "Other"


class TestScryfallToCardDict:
    def test_basic_card(self):
        raw = {
            "name": "Sol Ring",
            "cmc": 1.0,
            "mana_cost": "{1}",
            "oracle_text": "{T}: Add {C}{C}.",
            "type_line": "Artifact",
            "color_identity": [],
        }
        result = _scryfall_to_card_dict(raw, 1, False)
        assert result["name"] == "Sol Ring"
        assert result["oracle_cmc"] == 1.0
        assert result["cost"] == "{1}"
        assert result["types"] == ["Artifact"]
        assert result["commander"] is False
        assert result["user_category"] == "Artifact"

    def test_commander_flag(self):
        raw = {
            "name": "Vren",
            "cmc": 2.0,
            "mana_cost": "{U}{B}",
            "oracle_text": "text",
            "type_line": "Legendary Creature \u2014 Rat",
            "color_identity": ["U", "B"],
        }
        result = _scryfall_to_card_dict(raw, 1, True)
        assert result["commander"] is True
        assert result["super_types"] == ["Legendary"]

    def test_dfc_card(self):
        raw = {
            "name": "Agadeem's Awakening // Agadeem, the Undercrypt",
            "cmc": 3.0,
            "type_line": "Sorcery // Land",
            "color_identity": ["B"],
            "card_faces": [
                {
                    "mana_cost": "{X}{B}{B}{B}",
                    "oracle_text": "Return from graveyard...",
                    "type_line": "Sorcery",
                },
                {
                    "mana_cost": "",
                    "oracle_text": "enters tapped...",
                    "type_line": "Land",
                },
            ],
        }
        result = _scryfall_to_card_dict(raw, 1, False)
        assert result["cost"] == "{X}{B}{B}{B}//"
        assert "Sorcery" in result["types"]
        assert "Land" in result["types"]

    def test_user_category_override(self):
        raw = {
            "name": "Sol Ring",
            "cmc": 1.0,
            "type_line": "Artifact",
            "color_identity": [],
        }
        result = _scryfall_to_card_dict(raw, 1, False, user_category="Ramp")
        assert result["user_category"] == "Ramp"


class TestResolveCards:
    def _mock_response(self, cards, not_found=None):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "data": cards,
            "not_found": not_found or [],
        }
        resp.raise_for_status = MagicMock()
        return resp

    @patch("auto_goldfish.decklist.card_resolver.requests.post")
    def test_resolve_single_card(self, mock_post):
        mock_post.return_value = self._mock_response([
            {
                "name": "Sol Ring",
                "cmc": 1.0,
                "mana_cost": "{1}",
                "oracle_text": "{T}: Add {C}{C}.",
                "type_line": "Artifact",
                "color_identity": [],
            }
        ])
        result = resolve_cards([(1, "Sol Ring", False)])
        assert len(result) == 1
        assert result[0]["name"] == "Sol Ring"
        mock_post.assert_called_once()

    @patch("auto_goldfish.decklist.card_resolver.requests.post")
    def test_resolve_duplicates_merged(self, mock_post):
        mock_post.return_value = self._mock_response([
            {
                "name": "Island",
                "cmc": 0,
                "mana_cost": "",
                "oracle_text": "({T}: Add {U}.)",
                "type_line": "Basic Land \u2014 Island",
                "color_identity": ["U"],
            }
        ])
        # 36 Islands should produce one API call but 36 card dicts
        result = resolve_cards([(36, "Island", False)])
        assert len(result) == 36
        assert all(c["name"] == "Island" for c in result)

    @patch("auto_goldfish.decklist.card_resolver.requests.post")
    def test_resolve_not_found_raises(self, mock_post):
        mock_post.return_value = self._mock_response(
            cards=[],
            not_found=[{"name": "Nonexistent Card"}],
        )
        with pytest.raises(CardResolutionError, match="Nonexistent Card"):
            resolve_cards([(1, "Nonexistent Card", False)])

    @patch("auto_goldfish.decklist.card_resolver.requests.post")
    def test_resolve_empty_list(self, mock_post):
        result = resolve_cards([])
        assert result == []
        mock_post.assert_not_called()

    @patch("auto_goldfish.decklist.card_resolver.requests.post")
    def test_resolve_respects_rate_limiter(self, mock_post):
        """Ensure rate_limiter.wait is called for each batch."""
        mock_post.return_value = self._mock_response([
            {
                "name": f"Card {i}",
                "cmc": i,
                "mana_cost": f"{{{i}}}",
                "oracle_text": "",
                "type_line": "Creature",
                "color_identity": [],
            }
            for i in range(2)
        ])
        with patch("auto_goldfish.decklist.card_resolver.rate_limiter.wait") as mock_wait:
            resolve_cards([(1, "Card 0", False), (1, "Card 1", False)])
            mock_wait.assert_called_with("scryfall")

    @patch("auto_goldfish.decklist.card_resolver.requests.post")
    def test_resolve_batches_large_lists(self, mock_post):
        """More than 75 cards should result in multiple API calls."""
        cards_data = [
            {
                "name": f"Card {i}",
                "cmc": 1,
                "mana_cost": "{1}",
                "oracle_text": "",
                "type_line": "Creature",
                "color_identity": [],
            }
            for i in range(80)
        ]
        # First batch returns 75, second returns 5
        mock_post.side_effect = [
            self._mock_response(cards_data[:75]),
            self._mock_response(cards_data[75:]),
        ]
        entries = [(1, f"Card {i}", False) for i in range(80)]
        result = resolve_cards(entries)
        assert len(result) == 80
        assert mock_post.call_count == 2

    @patch("auto_goldfish.decklist.card_resolver.requests.post")
    def test_resolve_split_card_sends_front_face(self, mock_post):
        """DFC names like 'A // B' should send only front face to Scryfall."""
        mock_post.return_value = self._mock_response([
            {
                "name": "Silundi Vision // Silundi Isle",
                "cmc": 3.0,
                "type_line": "Instant // Land",
                "color_identity": ["U"],
                "card_faces": [
                    {"mana_cost": "{2}{U}", "oracle_text": "Look at top six...", "type_line": "Instant"},
                    {"mana_cost": "", "oracle_text": "", "type_line": "Land"},
                ],
            }
        ])
        result = resolve_cards([(1, "Silundi Vision // Silundi Isle", False)])
        assert len(result) == 1
        assert result[0]["name"] == "Silundi Vision // Silundi Isle"
        # Verify we sent only the front face name to Scryfall
        sent_json = mock_post.call_args[1]["json"]
        assert sent_json["identifiers"][0]["name"] == "Silundi Vision"

    @patch("auto_goldfish.decklist.card_resolver.requests.post")
    def test_resolve_front_face_only_also_works(self, mock_post):
        """User can also paste just 'Silundi Vision' and it resolves."""
        mock_post.return_value = self._mock_response([
            {
                "name": "Silundi Vision // Silundi Isle",
                "cmc": 3.0,
                "type_line": "Instant // Land",
                "color_identity": ["U"],
                "card_faces": [
                    {"mana_cost": "{2}{U}", "oracle_text": "Look at top six...", "type_line": "Instant"},
                    {"mana_cost": "", "oracle_text": "", "type_line": "Land"},
                ],
            }
        ])
        result = resolve_cards([(1, "Silundi Vision", False)])
        assert len(result) == 1
        assert result[0]["name"] == "Silundi Vision // Silundi Isle"
