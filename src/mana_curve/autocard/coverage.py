"""Coverage analysis: compare Scryfall cards against the existing card registry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from ..effects.json_loader import load_registry_from_json
from .schemas import ScryfallCard


@dataclass
class CoverageReport:
    """Summary of how many top cards are already labeled in the registry."""

    total_cards: int
    labeled: int
    unlabeled: int
    coverage_pct: float
    labeled_names: List[str]
    unlabeled_names: List[str]


def analyze_coverage(
    cards: List[ScryfallCard],
    registry_path=None,
) -> CoverageReport:
    """Check which Scryfall cards already exist in the effect registry."""
    registry = load_registry_from_json(registry_path)
    registry_names = set(registry._registry.keys())

    labeled = []
    unlabeled = []

    for card in cards:
        if card.name in registry_names:
            labeled.append(card.name)
        else:
            unlabeled.append(card.name)

    total = len(cards)
    pct = (len(labeled) / total * 100) if total > 0 else 0.0

    return CoverageReport(
        total_cards=total,
        labeled=len(labeled),
        unlabeled=len(unlabeled),
        coverage_pct=pct,
        labeled_names=labeled,
        unlabeled_names=unlabeled,
    )


def print_coverage_report(report: CoverageReport) -> None:
    """Print a human-readable coverage summary to stdout."""
    print(f"\n{'='*50}")
    print("Autocard Coverage Report")
    print(f"{'='*50}")
    print(f"Total cards:   {report.total_cards}")
    print(f"Labeled:       {report.labeled}")
    print(f"Unlabeled:     {report.unlabeled}")
    print(f"Coverage:      {report.coverage_pct:.1f}%")
    print(f"{'='*50}")

    if report.labeled_names:
        print(f"\nLabeled cards ({report.labeled}):")
        for name in sorted(report.labeled_names):
            print(f"  + {name}")

    if report.unlabeled_names:
        print(f"\nUnlabeled cards ({report.unlabeled}) — first 20:")
        for name in sorted(report.unlabeled_names)[:20]:
            print(f"  - {name}")
        if report.unlabeled > 20:
            print(f"  ... and {report.unlabeled - 20} more")
