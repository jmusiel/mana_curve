"""Tests for the Archidekt decklist fetcher."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from auto_goldfish.decklist import rate_limiter
from auto_goldfish.decklist.archidekt import (
    ArchidektAPIError,
    _get_deck,
    fetch_decklist,
)


@pytest.fixture(autouse=True)
def reset_limiter():
    rate_limiter.reset()
    yield
    rate_limiter.reset()


def _oracle_card(name):
    return SimpleNamespace(
        name=name,
        cmc=2.0,
        mana_cost="{1}{W}",
        text="",
        sub_types=[],
        super_types=[],
        types=["Artifact"],
        color_identity=[],
        default_category="Artifact",
        faces=None,
    )


def _deck_card(name, categories):
    return SimpleNamespace(
        card=SimpleNamespace(oracle_card=_oracle_card(name)),
        categories=categories,
        quantity=1,
        label=None,
        custom_cmc=None,
    )


def _deck(cards, categories):
    return SimpleNamespace(
        cards=cards,
        categories=[
            SimpleNamespace(name=n, included_in_deck=inc)
            for n, inc in categories.items()
        ],
    )


class TestFetchDecklist:
    @patch("auto_goldfish.decklist.archidekt._get_deck")
    def test_uncategorized_cards_are_included(self, mock_get):
        """Archidekt leaves ``categories`` as None on cards the owner never tagged."""
        mock_get.return_value = _deck(
            [
                _deck_card("Sol Ring", None),
                _deck_card("Arcane Signet", []),
                _deck_card("Millicent", ["Commander"]),
            ],
            {"Commander": True},
        )
        result = fetch_decklist("https://archidekt.com/decks/123/x")

        assert [c["name"] for c in result] == ["Sol Ring", "Arcane Signet", "Millicent"]
        assert [c["user_category"] for c in result] == [None, None, "Commander"]
        assert [c["commander"] for c in result] == [False, False, True]

    @patch("auto_goldfish.decklist.archidekt._get_deck")
    def test_excluded_categories_are_dropped(self, mock_get):
        mock_get.return_value = _deck(
            [
                _deck_card("Sol Ring", ["Ramp"]),
                _deck_card("Shivan Dragon", ["Maybeboard"]),
            ],
            {"Ramp": True, "Maybeboard": False},
        )
        result = fetch_decklist("https://archidekt.com/decks/123/x")

        assert [c["name"] for c in result] == ["Sol Ring"]


class TestGetDeck:
    def _resp(self, status, text="", json_data=None):
        resp = MagicMock()
        resp.status_code = status
        resp.text = text
        resp.json.return_value = json_data or {}
        return resp

    @patch("auto_goldfish.decklist.archidekt.Deck")
    @patch("auto_goldfish.decklist.archidekt.requests.get")
    def test_sends_identifying_user_agent_and_timeout(self, mock_get, _mock_deck):
        mock_get.return_value = self._resp(200)
        _get_deck(123)

        kwargs = mock_get.call_args[1]
        assert kwargs["headers"]["User-Agent"].startswith("auto-goldfish/")
        assert "python-requests" not in kwargs["headers"]["User-Agent"]
        assert kwargs["timeout"] == 30

    @patch("auto_goldfish.decklist.archidekt.requests.get")
    def test_404_reports_missing_or_private(self, mock_get):
        mock_get.return_value = self._resp(404)
        with pytest.raises(ArchidektAPIError, match="not found"):
            _get_deck(123)

    @patch("auto_goldfish.decklist.archidekt.requests.get")
    def test_other_status_surfaces_code_and_body(self, mock_get):
        """The status code is what tells us throttling apart from an outage."""
        mock_get.return_value = self._resp(429, text="Too Many Requests")
        with pytest.raises(ArchidektAPIError) as exc:
            _get_deck(123)

        assert "429" in str(exc.value)
        assert "Too Many Requests" in str(exc.value)

    @patch("auto_goldfish.decklist.archidekt.Deck")
    @patch("auto_goldfish.decklist.archidekt.requests.get")
    def test_respects_rate_limiter(self, mock_get, _mock_deck):
        mock_get.return_value = self._resp(200)
        with patch("auto_goldfish.decklist.archidekt.rate_limiter.wait") as mock_wait:
            _get_deck(123)
            mock_wait.assert_called_once_with("archidekt")
