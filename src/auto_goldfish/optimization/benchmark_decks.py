"""Benchmark deck definitions for optimizer testing.

Each entry defines a real Archidekt deck with metadata about its archetype.
Decks are fetched from Archidekt on first use and cached locally as JSON.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class BenchmarkDeck:
    """A real deck used for benchmarking optimizer performance."""

    name: str
    archidekt_url: str
    archetype: str  # e.g. "aggro", "midrange", "control", "combo"
    description: str


BENCHMARK_DECKS: List[BenchmarkDeck] = [
    BenchmarkDeck(
        name="rubys_ripjaw_raptors",
        archidekt_url="https://archidekt.com/decks/9603710/rubys_ripjaw_raptors",
        archetype="midrange",
        description="Dinosaur tribal with enrage synergies",
    ),
    BenchmarkDeck(
        name="hermes_cantripping_through_time",
        archidekt_url="https://archidekt.com/decks/16488991/hermes_cantripping_through_time",
        archetype="spellslinger",
        description="Cantrip-heavy spellslinger",
    ),
    BenchmarkDeck(
        name="the_rr_connection",
        archidekt_url="https://archidekt.com/decks/81320/the_rr_connection",
        archetype="combo",
        description="Riku combo/value",
    ),
    BenchmarkDeck(
        name="kesss_cozy_cantrips",
        archidekt_url="https://archidekt.com/decks/7947868/kesss_cozy_cantrips",
        archetype="spellslinger",
        description="Kess cantrip/flashback spellslinger",
    ),
    BenchmarkDeck(
        name="santas_etb_workshop",
        archidekt_url="https://archidekt.com/decks/9699790/santas_etb_workshop",
        archetype="midrange",
        description="ETB value/blink",
    ),
    BenchmarkDeck(
        name="will_the_real_mr_markov_please_stand_up",
        archidekt_url="https://archidekt.com/decks/3390122/will_the_real_mr_markov_please_stand_up",
        archetype="aggro",
        description="Edgar Markov vampire tribal aggro",
    ),
    BenchmarkDeck(
        name="cantripping_through_time",
        archidekt_url="https://archidekt.com/decks/12122030/cantripping_through_time",
        archetype="spellslinger",
        description="Time-themed cantrip spellslinger",
    ),
    BenchmarkDeck(
        name="bantchantress",
        archidekt_url="https://archidekt.com/decks/482754/bantchantress",
        archetype="enchantress",
        description="Bant enchantress value engine",
    ),
    BenchmarkDeck(
        name="hms_her_majestys_slivers",
        archidekt_url="https://archidekt.com/decks/9538770/hms_her_majestys_slivers",
        archetype="tribal",
        description="Five-color sliver tribal",
    ),
    BenchmarkDeck(
        name="lords_landed_libations",
        archidekt_url="https://archidekt.com/decks/1856247/lords_landed_libations",
        archetype="midrange",
        description="Lands-matter midrange",
    ),
    BenchmarkDeck(
        name="good_ol_superfriends",
        archidekt_url="https://archidekt.com/decks/1847823/good_ol_superfriends",
        archetype="control",
        description="Planeswalker-based superfriends control",
    ),
    BenchmarkDeck(
        name="riku_because_riku_is_bonkers",
        archidekt_url="https://archidekt.com/decks/1930237/riku_because_riku_is_bonkers",
        archetype="combo",
        description="Riku copy/value combo",
    ),
    BenchmarkDeck(
        name="vrens_murine_marauders",
        archidekt_url="https://archidekt.com/decks/19226307/vrens_murine_marauders",
        archetype="aggro",
        description="Vren rat tribal aggro",
    ),
    BenchmarkDeck(
        name="fly_yue_to_the_moon",
        archidekt_url="https://archidekt.com/decks/19793520/fly_yue_to_the_moon",
        archetype="midrange",
        description="Yue flying/evasion midrange",
    ),
]


def get_benchmark_deck_dicts(
    deck: BenchmarkDeck,
    cache_dir: Optional[str] = None,
    verbose: bool = False,
) -> List[Dict[str, Any]]:
    """Load a benchmark deck, fetching from Archidekt if not cached.

    Args:
        deck: BenchmarkDeck to load.
        cache_dir: Directory for cached JSON files.
            Defaults to ``<project_root>/decks``.
        verbose: Print progress during fetch.

    Returns:
        List of card dicts ready for Goldfisher.
    """
    import json

    if cache_dir is None:
        project_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        )
        cache_dir = os.path.join(project_root, "decks")

    deck_dir = os.path.join(cache_dir, deck.name)
    cache_path = os.path.join(deck_dir, f"{deck.name}.json")

    if os.path.isfile(cache_path):
        with open(cache_path) as f:
            return json.load(f)

    # Fetch from Archidekt
    from auto_goldfish.decklist.archidekt import fetch_and_save

    if verbose:
        print(f"Fetching {deck.name} from {deck.archidekt_url}...")
    return fetch_and_save(deck.archidekt_url, deck.name, verbose=verbose)


def fetch_all_benchmark_decks(
    cache_dir: Optional[str] = None, verbose: bool = True
) -> Dict[str, List[Dict[str, Any]]]:
    """Fetch and cache all benchmark decks. Returns name -> card dicts."""
    results: Dict[str, List[Dict[str, Any]]] = {}
    for deck in BENCHMARK_DECKS:
        try:
            deck_dicts = get_benchmark_deck_dicts(deck, cache_dir, verbose)
            results[deck.name] = deck_dicts
            if verbose:
                lands = sum(1 for c in deck_dicts if "Land" in c.get("types", []))
                print(f"  {deck.name}: {len(deck_dicts)} cards, {lands} lands")
        except Exception as e:
            if verbose:
                print(f"  FAILED {deck.name}: {e}")
    return results
