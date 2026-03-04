"""Wizard prioritization logic for the card labeling wizard."""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional

from auto_goldfish.effects.otag_loader import get_matching_cards, has_cheaper_than_mv


def build_wizard_card_list(
    deck_nonland_cards: List[Dict[str, Any]],
    saved_overrides: Dict[str, Any],
    otag_registry: Dict[str, Any],
    annotation_stats: Optional[Dict[str, Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Build a prioritized list of cards for the labeling wizard.

    Args:
        deck_nonland_cards: List of card dicts with name, cmc, types keys.
        saved_overrides: Current saved effect overrides (card_name -> override dict).
        otag_registry: Loaded otag registry with 'cards' key.
        annotation_stats: Optional annotation stats from DB (card_name -> stats dict).
            If None, DB is unavailable — falls back to otag-only filtering.

    Returns:
        List of wizard card dicts with keys:
            name, cmc, types, otags, prior_annotation, cheaper_than_mv, priority_group
    """
    card_names = [c["name"] for c in deck_nonland_cards]
    matching = get_matching_cards(card_names, otag_registry)

    # Build name -> card dict lookup
    card_by_name = {c["name"]: c for c in deck_nonland_cards}

    wizard_cards = []
    for name, otags in matching.items():
        card = card_by_name[name]

        # Determine prior annotation
        prior_annotation = None
        if name in saved_overrides and saved_overrides[name]:
            prior_annotation = saved_overrides[name]
        elif card.get("registry_override"):
            prior_annotation = card["registry_override"]

        cheaper = has_cheaper_than_mv(name, otag_registry)

        wizard_card = {
            "name": name,
            "cmc": card.get("cmc", 0),
            "types": card.get("types", []),
            "otags": otags,
            "prior_annotation": prior_annotation,
            "cheaper_than_mv": cheaper,
            "priority_group": 1,  # default, overridden below if DB available
        }
        wizard_cards.append(wizard_card)

    if annotation_stats is not None:
        _assign_priority_groups(wizard_cards, annotation_stats)
    else:
        # Without DB: all otag-matched cards in group 1
        for wc in wizard_cards:
            wc["priority_group"] = 1

    # Sort by priority_group, then CMC, then name
    wizard_cards.sort(key=lambda c: (c["priority_group"], c["cmc"], c["name"]))

    return wizard_cards


def _assign_priority_groups(
    wizard_cards: List[Dict[str, Any]],
    annotation_stats: Dict[str, Dict[str, Any]],
) -> None:
    """Assign priority groups based on annotation stats.

    P1: Never human-annotated or controversial
    P2: 3 random from human-labeled non-controversial (for verification sampling)
    P3: Remaining human-labeled non-controversial (hidden by default)
    """
    p1 = []
    settled = []

    for wc in wizard_cards:
        stats = annotation_stats.get(wc["name"])
        if stats is None or not stats.get("has_human") or stats.get("is_controversial"):
            wc["priority_group"] = 1
            p1.append(wc)
        else:
            settled.append(wc)

    # Pick up to 3 random from settled for verification
    sample_size = min(3, len(settled))
    sampled = set()
    if sample_size > 0:
        sampled_cards = random.sample(settled, sample_size)
        sampled = {c["name"] for c in sampled_cards}

    for wc in settled:
        if wc["name"] in sampled:
            wc["priority_group"] = 2
        else:
            wc["priority_group"] = 3
