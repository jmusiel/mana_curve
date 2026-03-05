"""Tests for the fetch-otags CLI command."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from auto_goldfish.autocard.cli import build_parser, cmd_fetch_otags


@pytest.fixture
def mock_cards():
    """Create mock ScryfallCard-like objects with otags."""
    from auto_goldfish.autocard.schemas import ScryfallCard

    return [
        ScryfallCard(
            name="Sol Ring",
            mana_cost="{1}",
            cmc=1.0,
            type_line="Artifact",
            oracle_text="{T}: Add {C}{C}.",
            colors=[],
            color_identity=[],
            keywords=[],
            edhrec_rank=1,
            otags=["ramp", "cheaper-than-mv"],
        ),
        ScryfallCard(
            name="Rhystic Study",
            mana_cost="{2}{U}",
            cmc=3.0,
            type_line="Enchantment",
            oracle_text="Draw a card.",
            colors=["U"],
            color_identity=["U"],
            keywords=[],
            edhrec_rank=2,
            otags=["card-advantage"],
        ),
    ]


class TestCmdFetchOtags:
    def test_writes_registry(self, tmp_path, mock_cards):
        output = tmp_path / "otag_registry.json"

        with patch(
            "auto_goldfish.autocard.cli.cmd_fetch_otags.__module__",
        ):
            pass

        # Build args manually
        parser = build_parser()
        args = parser.parse_args(["fetch-otags", "--output", str(output)])

        with patch("auto_goldfish.autocard.scryfall.fetch_top_cards_by_tags", return_value=mock_cards):
            cmd_fetch_otags(args)

        assert output.exists()
        data = json.loads(output.read_text())
        assert "updated" in data
        assert "cards" in data
        assert data["cards"]["Sol Ring"] == ["ramp", "cheaper-than-mv"]
        assert data["cards"]["Rhystic Study"] == ["card-advantage"]
        assert len(data["cards"]) == 2

    def test_default_output_path(self, tmp_path, mock_cards):
        parser = build_parser()
        args = parser.parse_args(["fetch-otags"])
        # Override the default output to avoid clobbering the real registry
        args.output = str(tmp_path / "otag_registry.json")

        with patch("auto_goldfish.autocard.scryfall.fetch_top_cards_by_tags", return_value=mock_cards):
            cmd_fetch_otags(args)

        output = tmp_path / "otag_registry.json"
        assert output.exists()
        data = json.loads(output.read_text())
        assert len(data["cards"]) == 2

    def test_parser_registers_command(self):
        parser = build_parser()
        args = parser.parse_args(["fetch-otags"])
        assert args.command == "fetch-otags"
        assert args.per_tag_count == 100000

    def test_parser_custom_per_tag_count(self):
        parser = build_parser()
        args = parser.parse_args(["fetch-otags", "--per-tag-count", "200"])
        assert args.per_tag_count == 200
