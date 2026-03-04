"""Tests for autocard Scryfall fetcher (fetch_top_cards_by_tags)."""

from __future__ import annotations

from unittest.mock import patch

from auto_goldfish.autocard.schemas import ScryfallCard
from auto_goldfish.autocard.scryfall import fetch_top_cards_by_tags


def _make_card(name: str, edhrec_rank: int | None = None) -> ScryfallCard:
    return ScryfallCard(
        name=name,
        mana_cost="{1}",
        cmc=1.0,
        type_line="Artifact",
        oracle_text="",
        colors=[],
        color_identity=[],
        keywords=[],
        edhrec_rank=edhrec_rank,
    )


class TestFetchTopCardsByTags:
    @patch("auto_goldfish.autocard.scryfall.fetch_top_cards")
    def test_deduplicates_by_name(self, mock_fetch):
        """Same card from two tags should appear once with both tags."""
        mock_fetch.side_effect = [
            [_make_card("Sol Ring", 1)],  # otag:draw
            [_make_card("Sol Ring", 1)],  # otag:ramp
        ]

        result = fetch_top_cards_by_tags(
            tags=["otag:draw", "otag:ramp"], per_tag_count=100,
        )

        assert len(result) == 1
        assert result[0].name == "Sol Ring"
        assert sorted(result[0].otags) == ["draw", "ramp"]

    @patch("auto_goldfish.autocard.scryfall.fetch_top_cards")
    def test_collects_multiple_tags(self, mock_fetch):
        """Card appearing in all 3 tags gets all 3 tag names."""
        mock_fetch.side_effect = [
            [_make_card("Mystic Remora", 10)],
            [_make_card("Mystic Remora", 10)],
            [_make_card("Mystic Remora", 10)],
        ]

        result = fetch_top_cards_by_tags(
            tags=["otag:draw", "otag:card-advantage", "otag:ramp"],
            per_tag_count=100,
        )

        assert len(result) == 1
        assert sorted(result[0].otags) == ["card-advantage", "draw", "ramp"]

    @patch("auto_goldfish.autocard.scryfall.fetch_top_cards")
    def test_sorts_by_edhrec_rank(self, mock_fetch):
        """Combined list should be sorted by edhrec_rank ascending."""
        mock_fetch.side_effect = [
            [_make_card("Card B", 50)],
            [_make_card("Card A", 10)],
        ]

        result = fetch_top_cards_by_tags(
            tags=["otag:draw", "otag:ramp"], per_tag_count=100,
        )

        assert len(result) == 2
        assert result[0].name == "Card A"
        assert result[1].name == "Card B"

    @patch("auto_goldfish.autocard.scryfall.fetch_top_cards")
    def test_none_edhrec_rank_sorts_last(self, mock_fetch):
        """Cards without edhrec_rank should sort to end."""
        mock_fetch.side_effect = [
            [_make_card("No Rank", None)],
            [_make_card("Has Rank", 5)],
        ]

        result = fetch_top_cards_by_tags(
            tags=["otag:draw", "otag:ramp"], per_tag_count=100,
        )

        assert result[0].name == "Has Rank"
        assert result[1].name == "No Rank"

    @patch("auto_goldfish.autocard.scryfall.fetch_top_cards")
    def test_base_query_passthrough(self, mock_fetch):
        """base_query should be appended to each tag query."""
        mock_fetch.return_value = []

        fetch_top_cards_by_tags(
            tags=["otag:draw", "otag:ramp"],
            per_tag_count=100,
            base_query="-t:land f:commander",
        )

        calls = mock_fetch.call_args_list
        assert len(calls) == 2
        assert calls[0].kwargs["query"] == "otag:draw -t:land f:commander"
        assert calls[1].kwargs["query"] == "otag:ramp -t:land f:commander"

    @patch("auto_goldfish.autocard.scryfall.fetch_top_cards")
    def test_per_tag_count_passthrough(self, mock_fetch):
        """per_tag_count should be passed as count to fetch_top_cards."""
        mock_fetch.return_value = []

        fetch_top_cards_by_tags(
            tags=["otag:draw"], per_tag_count=250,
        )

        mock_fetch.assert_called_once_with(count=250, query="otag:draw -t:land f:commander")

    @patch("auto_goldfish.autocard.scryfall.fetch_top_cards")
    def test_extracts_short_tag_name(self, mock_fetch):
        """'otag:card-advantage' should become 'card-advantage' in otags."""
        mock_fetch.side_effect = [
            [_make_card("Test Card", 1)],
        ]

        result = fetch_top_cards_by_tags(tags=["otag:card-advantage"], per_tag_count=100)

        assert result[0].otags == ["card-advantage"]

    @patch("auto_goldfish.autocard.scryfall.fetch_top_cards")
    def test_tag_without_colon(self, mock_fetch):
        """Tag without colon prefix is used as-is."""
        mock_fetch.side_effect = [
            [_make_card("Test Card", 1)],
        ]

        result = fetch_top_cards_by_tags(tags=["ramp"], per_tag_count=100)

        assert result[0].otags == ["ramp"]

    @patch("auto_goldfish.autocard.scryfall.fetch_top_cards")
    def test_empty_tags_returns_empty(self, mock_fetch):
        """Empty tag list returns empty result."""
        result = fetch_top_cards_by_tags(tags=[], per_tag_count=100)

        assert result == []
        mock_fetch.assert_not_called()

    @patch("auto_goldfish.autocard.scryfall.fetch_top_cards")
    def test_no_duplicate_tag_entries(self, mock_fetch):
        """If same card appears twice in same tag result, tag only added once."""
        card1 = _make_card("Sol Ring", 1)
        card2 = _make_card("Sol Ring", 1)
        mock_fetch.side_effect = [
            [card1, card2],  # same card twice in one tag result
        ]

        result = fetch_top_cards_by_tags(tags=["otag:draw"], per_tag_count=100)

        assert len(result) == 1
        assert result[0].otags == ["draw"]
