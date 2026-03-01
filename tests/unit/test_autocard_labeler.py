"""Tests for autocard LLM labeler."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Mock ollama before importing labeler so the local import works
_mock_ollama = MagicMock()


@pytest.fixture(autouse=True)
def _patch_ollama():
    """Inject a mock ollama module so label_card's local import works."""
    with patch.dict(sys.modules, {"ollama": _mock_ollama}):
        _mock_ollama.reset_mock(side_effect=True)
        _mock_ollama.chat.reset_mock(side_effect=True)
        _mock_ollama.chat.side_effect = None
        _mock_ollama.chat.return_value = None
        yield


from mana_curve.autocard.labeler import (
    build_card_prompt,
    label_card,
    label_cards,
    load_labeled,
    save_labeled,
)
from mana_curve.autocard.schemas import ScryfallCard


def _make_card(name: str = "Sol Ring", oracle_text: str = "{T}: Add {C}{C}.") -> ScryfallCard:
    return ScryfallCard(
        name=name,
        mana_cost="{1}",
        cmc=1.0,
        type_line="Artifact",
        oracle_text=oracle_text,
        colors=[],
        color_identity=[],
        keywords=[],
        edhrec_rank=1,
    )


_VALID_LABEL = {
    "effects": [
        {"type": "produce_mana", "slot": "on_play", "params": {"amount": 2}},
    ],
    "metadata": {"ramp": True},
}

_EMPTY_LABEL = {"effects": [], "metadata": {}}


def _mock_chat_response(label: dict) -> dict:
    return {"message": {"content": json.dumps(label)}}


class TestBuildCardPrompt:
    def test_includes_card_fields(self):
        card = _make_card()
        prompt = build_card_prompt(card)
        assert "Sol Ring" in prompt
        assert "{1}" in prompt
        assert "{T}: Add {C}{C}." in prompt
        assert "Artifact" in prompt

    def test_includes_keywords(self):
        card = _make_card()
        card.keywords = ["Flying", "Haste"]
        prompt = build_card_prompt(card)
        assert "Flying" in prompt
        assert "Haste" in prompt

    def test_includes_produced_mana(self):
        card = _make_card()
        card.produced_mana = ["C"]
        prompt = build_card_prompt(card)
        assert "produced_mana" in prompt


class TestLabelCard:
    def test_valid_response(self):
        _mock_ollama.chat.return_value = _mock_chat_response(_VALID_LABEL)

        result = label_card(_make_card())

        assert result == _VALID_LABEL
        _mock_ollama.chat.assert_called_once()

    def test_retry_on_invalid_json(self):
        """First call returns garbage, second returns valid JSON."""
        _mock_ollama.chat.side_effect = [
            {"message": {"content": "not json at all"}},
            _mock_chat_response(_VALID_LABEL),
        ]

        result = label_card(_make_card(), max_retries=3)

        assert result == _VALID_LABEL
        assert _mock_ollama.chat.call_count == 2

    def test_raises_after_max_retries(self):
        """All retries fail -> ValueError."""
        _mock_ollama.chat.side_effect = [
            {"message": {"content": "bad"}},
            {"message": {"content": "bad"}},
            {"message": {"content": "bad"}},
        ]

        with pytest.raises(ValueError, match="Failed to get valid JSON"):
            label_card(_make_card(), max_retries=3)

    def test_custom_model(self):
        _mock_ollama.chat.return_value = _mock_chat_response(_EMPTY_LABEL)

        label_card(_make_card(), model="llama3:8b")

        call_kwargs = _mock_ollama.chat.call_args
        assert call_kwargs.kwargs["model"] == "llama3:8b"


class TestLabelCards:
    @patch("mana_curve.autocard.labeler.label_card")
    def test_labels_all_cards(self, mock_label_card):
        mock_label_card.return_value = _VALID_LABEL
        cards = [_make_card("Card A"), _make_card("Card B")]

        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "labeled.json"
            results = label_cards(cards, output_path=out, resume=False)

        assert "Card A" in results
        assert "Card B" in results
        assert mock_label_card.call_count == 2

    @patch("mana_curve.autocard.labeler.label_card")
    def test_resume_skips_existing(self, mock_label_card):
        """Resume skips already-labeled cards."""
        mock_label_card.return_value = _EMPTY_LABEL

        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "labeled.json"
            # Pre-populate with Card A
            save_labeled({"Card A": _VALID_LABEL}, out)

            cards = [_make_card("Card A"), _make_card("Card B")]
            results = label_cards(cards, output_path=out, resume=True)

        # Card A kept its original label, Card B was newly labeled
        assert results["Card A"] == _VALID_LABEL
        assert results["Card B"] == _EMPTY_LABEL
        # label_card only called for Card B
        assert mock_label_card.call_count == 1

    @patch("mana_curve.autocard.labeler.label_card")
    def test_incremental_save(self, mock_label_card):
        """Results saved after each card."""
        mock_label_card.return_value = _VALID_LABEL

        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "labeled.json"
            label_cards([_make_card("Card A")], output_path=out, resume=False)

            # File should exist with Card A
            saved = load_labeled(out)
            assert "Card A" in saved


class TestLoadSaveLabeled:
    def test_round_trip(self):
        data = {"Sol Ring": _VALID_LABEL}
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.json"
            save_labeled(data, path)
            loaded = load_labeled(path)
        assert loaded == data

    def test_load_nonexistent_returns_empty(self):
        result = load_labeled(Path("/nonexistent/file.json"))
        assert result == {}
