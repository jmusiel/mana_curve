"""CLI entry point for the autocard tool."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def cmd_fetch(args: argparse.Namespace) -> None:
    """Download top commander cards from Scryfall."""
    from .scryfall import fetch_top_cards, save_cards

    output = Path(args.output) if args.output else None
    print(f"Fetching top {args.count} commander cards from Scryfall...")
    cards = fetch_top_cards(count=args.count)
    path = save_cards(cards, output)
    print(f"Saved {len(cards)} cards to {path}")


def cmd_coverage(args: argparse.Namespace) -> None:
    """Run coverage analysis against the existing card registry."""
    from .coverage import analyze_coverage, print_coverage_report
    from .scryfall import load_cards

    cards_path = Path(args.cards) if args.cards else None
    registry_path = Path(args.registry) if args.registry else None

    cards = load_cards(cards_path)
    report = analyze_coverage(cards, registry_path)
    print_coverage_report(report)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="autocard",
        description="Auto-label Magic cards for the mana_curve simulator.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # fetch
    fetch_parser = subparsers.add_parser("fetch", help="Download top cards from Scryfall")
    fetch_parser.add_argument(
        "--count", type=int, default=1000,
        help="Number of cards to fetch (default: 1000)",
    )
    fetch_parser.add_argument(
        "--output", type=str, default=None,
        help="Output JSON path (default: autocard/data/top_cards.json)",
    )
    fetch_parser.set_defaults(func=cmd_fetch)

    # coverage
    cov_parser = subparsers.add_parser("coverage", help="Coverage report vs existing registry")
    cov_parser.add_argument(
        "--cards", type=str, default=None,
        help="Path to top_cards.json (default: autocard/data/top_cards.json)",
    )
    cov_parser.add_argument(
        "--registry", type=str, default=None,
        help="Path to card_effects.json (default: built-in registry)",
    )
    cov_parser.set_defaults(func=cmd_coverage)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nAborted.", file=sys.stderr)
        sys.exit(130)
