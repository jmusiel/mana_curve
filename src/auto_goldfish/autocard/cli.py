"""CLI entry point for the autocard tool."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def cmd_fetch(args: argparse.Namespace) -> None:
    """Download top commander cards from Scryfall."""
    from .scryfall import fetch_top_cards, fetch_top_cards_by_tags, save_cards

    output = Path(args.output) if args.output else None
    if args.tags:
        print(f"Fetching cards by tags: {args.tags} (per_tag_count={args.per_tag_count})", flush=True)
        cards = fetch_top_cards_by_tags(
            tags=args.tags,
            per_tag_count=args.per_tag_count,
            base_query=args.query,
        )
    else:
        print(f"Fetching top {args.count} cards with query: {args.query!r}", flush=True)
        cards = fetch_top_cards(count=args.count, query=args.query)
    path = save_cards(cards, output)
    print(f"Saved {len(cards)} cards to {path}", flush=True)


def cmd_coverage(args: argparse.Namespace) -> None:
    """Run coverage analysis against the existing card registry."""
    from .coverage import analyze_coverage, print_coverage_report
    from .scryfall import load_cards

    cards_path = Path(args.cards) if args.cards else None
    registry_path = Path(args.registry) if args.registry else None

    cards = load_cards(cards_path)
    report = analyze_coverage(cards, registry_path)
    print_coverage_report(report)


def cmd_label(args: argparse.Namespace) -> None:
    """Run LLM labeling on unlabeled cards."""
    from .coverage import analyze_coverage
    from .labeler import label_cards
    from .scryfall import load_cards

    cards_path = Path(args.cards) if args.cards else None
    cards = load_cards(cards_path)

    # Filter to unlabeled cards only
    report = analyze_coverage(cards)
    unlabeled = [c for c in cards if c.name in report.unlabeled_names]

    if args.count:
        unlabeled = unlabeled[: args.count]

    if not unlabeled:
        print("All cards are already labeled!", flush=True)
        return

    print(
        f"Labeling {len(unlabeled)} cards with model {args.model}"
        f" (concurrency={args.concurrency}, batch_size={args.batch_size})...",
        flush=True,
    )
    output_path = Path(args.output) if args.output else None
    results = label_cards(
        unlabeled,
        model=args.model,
        output_path=output_path,
        resume=args.resume,
        concurrency=args.concurrency,
        batch_size=args.batch_size,
    )
    print(f"Labeled {len(results)} cards total.", flush=True)


def cmd_validate(args: argparse.Namespace) -> None:
    """Validate all labels in labeled_cards.json."""
    from .labeler import load_labeled
    from .validator import validate_label

    cards_path = Path(args.cards) if args.cards else None
    labeled = load_labeled(cards_path)

    if not labeled:
        print("No labeled cards found.")
        return

    total = 0
    failed = 0
    for card_name, label in labeled.items():
        total += 1
        errors = validate_label(card_name, label)
        if errors:
            failed += 1
            for error in errors:
                print(f"  FAIL: {error}")

    passed = total - failed
    print(f"\nValidation: {passed}/{total} passed, {failed} failed")


def cmd_fetch_otags(args: argparse.Namespace) -> None:
    """Fetch Scryfall otag data and write a compact otag registry."""
    import json
    from datetime import date

    from .scryfall import fetch_top_cards_by_tags

    tags = ["otag:card-advantage", "otag:ramp", "otag:cheaper-than-mv"]
    base_query = "-t:land f:commander"
    per_tag_count = args.per_tag_count or 100000

    print(f"Fetching otag cards: {tags}", flush=True)
    cards = fetch_top_cards_by_tags(tags=tags, per_tag_count=per_tag_count, base_query=base_query)

    registry = {
        "updated": date.today().isoformat(),
        "cards": {card.name: card.otags for card in cards},
    }

    from pathlib import Path

    if args.output:
        output = Path(args.output)
    else:
        output = Path(__file__).resolve().parent.parent / "effects" / "otag_registry.json"

    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2, ensure_ascii=False)

    print(f"Wrote {len(registry['cards'])} cards to {output}", flush=True)


def cmd_export(args: argparse.Namespace) -> None:
    """Export labeled cards to registry JSON."""
    from .exporter import export_to_registry
    from .labeler import load_labeled

    cards_path = Path(args.cards) if args.cards else None
    labeled = load_labeled(cards_path)

    if not labeled:
        print("No labeled cards found.")
        return

    output = Path(args.output) if args.output else None
    existing = Path(args.merge) if args.merge else None

    path = export_to_registry(labeled, output=output, existing_path=existing)
    print(f"Exported {len(labeled)} labeled cards to {path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="autocard",
        description="Auto-label Magic cards for the auto_goldfish simulator.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # fetch
    fetch_parser = subparsers.add_parser("fetch", help="Download top cards from Scryfall")
    fetch_parser.add_argument(
        "--count", type=int, default=1000,
        help="Number of cards to fetch (default: 1000)",
    )
    fetch_parser.add_argument(
        "--query", type=str, default="f:commander",
        help="Scryfall search query (default: 'f:commander')",
    )
    fetch_parser.add_argument(
        "--output", type=str, default=None,
        help="Output JSON path (default: autocard/data/top_cards.json)",
    )
    fetch_parser.add_argument(
        "--tags", nargs="+", default=None,
        help="Scryfall otags to fetch separately (e.g. otag:draw otag:ramp)",
    )
    fetch_parser.add_argument(
        "--per-tag-count", type=int, default=500,
        help="Max cards per tag when using --tags (default: 500)",
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

    # label
    label_parser = subparsers.add_parser("label", help="LLM-label unlabeled cards")
    label_parser.add_argument(
        "--count", type=int, default=None,
        help="Max number of cards to label",
    )
    label_parser.add_argument(
        "--model", type=str, default="llama4:16x17b",
        help="Ollama model name (default: llama4:16x17b)",
    )
    label_parser.add_argument(
        "--resume", action="store_true", default=True,
        help="Skip already-labeled cards (default: True)",
    )
    label_parser.add_argument(
        "--cards", type=str, default=None,
        help="Path to top_cards.json",
    )
    label_parser.add_argument(
        "--output", type=str, default=None,
        help="Path to labeled_cards.json output",
    )
    label_parser.add_argument(
        "--concurrency", type=int, default=1,
        help="Number of parallel Ollama requests (default: 1)",
    )
    label_parser.add_argument(
        "--batch-size", type=int, default=1,
        help="Cards per LLM call (default: 1, max ~5 due to schema size limits)",
    )
    label_parser.set_defaults(func=cmd_label)

    # validate
    val_parser = subparsers.add_parser("validate", help="Validate labeled_cards.json")
    val_parser.add_argument(
        "--cards", type=str, default=None,
        help="Path to labeled_cards.json",
    )
    val_parser.set_defaults(func=cmd_validate)

    # fetch-otags
    otag_parser = subparsers.add_parser("fetch-otags", help="Fetch Scryfall otags to otag registry")
    otag_parser.add_argument(
        "--per-tag-count", type=int, default=100000,
        help="Max cards per tag (default: 100000, effectively all)",
    )
    otag_parser.add_argument(
        "--output", type=str, default=None,
        help="Output path (default: effects/otag_registry.json)",
    )
    otag_parser.set_defaults(func=cmd_fetch_otags)

    # export
    exp_parser = subparsers.add_parser("export", help="Export labels to registry JSON")
    exp_parser.add_argument(
        "--output", type=str, default=None,
        help="Output path (default: data/card_effects_expanded.json)",
    )
    exp_parser.add_argument(
        "--merge", type=str, default=None,
        help="Path to existing card_effects.json to merge with",
    )
    exp_parser.add_argument(
        "--cards", type=str, default=None,
        help="Path to labeled_cards.json",
    )
    exp_parser.set_defaults(func=cmd_export)

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


if __name__ == "__main__":
    main()
