"""Tests for autocard coverage analysis."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from auto_goldfish.autocard.coverage import CoverageReport, analyze_coverage, print_coverage_report
from auto_goldfish.autocard.schemas import ScryfallCard
from auto_goldfish.effects.registry import CardEffects, EffectRegistry


def _make_card(name: str, rank: int = 1) -> ScryfallCard:
    return ScryfallCard(
        name=name,
        mana_cost="{2}",
        cmc=2.0,
        type_line="Artifact",
        oracle_text="",
        colors=[],
        color_identity=[],
        keywords=[],
        edhrec_rank=rank,
    )


def _make_registry(names: list[str]) -> EffectRegistry:
    registry = EffectRegistry()
    for name in names:
        registry.register(name, CardEffects())
    return registry


class TestAnalyzeCoverage:
    def test_full_coverage(self):
        cards = [_make_card("Sol Ring"), _make_card("Arcane Signet")]
        with patch(
            "auto_goldfish.autocard.coverage.load_registry_from_json",
            return_value=_make_registry(["Sol Ring", "Arcane Signet"]),
        ):
            report = analyze_coverage(cards)

        assert report.total_cards == 2
        assert report.labeled == 2
        assert report.unlabeled == 0
        assert report.coverage_pct == 100.0
        assert report.labeled_names == ["Sol Ring", "Arcane Signet"]
        assert report.unlabeled_names == []

    def test_no_coverage(self):
        cards = [_make_card("Sol Ring"), _make_card("Arcane Signet")]
        with patch(
            "auto_goldfish.autocard.coverage.load_registry_from_json",
            return_value=_make_registry([]),
        ):
            report = analyze_coverage(cards)

        assert report.total_cards == 2
        assert report.labeled == 0
        assert report.unlabeled == 2
        assert report.coverage_pct == 0.0

    def test_partial_coverage(self):
        cards = [
            _make_card("Sol Ring"),
            _make_card("Arcane Signet"),
            _make_card("Lightning Bolt"),
        ]
        with patch(
            "auto_goldfish.autocard.coverage.load_registry_from_json",
            return_value=_make_registry(["Sol Ring"]),
        ):
            report = analyze_coverage(cards)

        assert report.total_cards == 3
        assert report.labeled == 1
        assert report.unlabeled == 2
        assert report.coverage_pct == pytest.approx(33.3, abs=0.1)
        assert "Sol Ring" in report.labeled_names
        assert "Lightning Bolt" in report.unlabeled_names

    def test_empty_card_list(self):
        with patch(
            "auto_goldfish.autocard.coverage.load_registry_from_json",
            return_value=_make_registry(["Sol Ring"]),
        ):
            report = analyze_coverage([])

        assert report.total_cards == 0
        assert report.coverage_pct == 0.0


class TestPrintCoverageReport:
    def test_print_report(self, capsys):
        report = CoverageReport(
            total_cards=100,
            labeled=25,
            unlabeled=75,
            coverage_pct=25.0,
            labeled_names=["Sol Ring"],
            unlabeled_names=["Card " + str(i) for i in range(75)],
        )
        print_coverage_report(report)
        output = capsys.readouterr().out
        assert "Coverage Report" in output
        assert "Total cards:   100" in output
        assert "Labeled:       25" in output
        assert "Unlabeled:     75" in output
        assert "25.0%" in output
        assert "Sol Ring" in output
        assert "... and 55 more" in output

    def test_print_report_empty(self, capsys):
        report = CoverageReport(
            total_cards=0,
            labeled=0,
            unlabeled=0,
            coverage_pct=0.0,
            labeled_names=[],
            unlabeled_names=[],
        )
        print_coverage_report(report)
        output = capsys.readouterr().out
        assert "0.0%" in output
