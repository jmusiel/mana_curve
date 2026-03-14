#!/usr/bin/env python3
"""Fetch and cache all benchmark decks from Archidekt.

Run once to populate the decks/ cache so benchmarks don't need network access.

Usage:
    .venv/bin/python scripts/fetch_benchmark_decks.py
"""

from auto_goldfish.optimization.benchmark_decks import (
    BENCHMARK_DECKS,
    fetch_all_benchmark_decks,
)


def main() -> None:
    print(f"Fetching {len(BENCHMARK_DECKS)} benchmark decks...\n")
    results = fetch_all_benchmark_decks(verbose=True)
    print(f"\nDone. {len(results)}/{len(BENCHMARK_DECKS)} decks cached successfully.")


if __name__ == "__main__":
    main()
