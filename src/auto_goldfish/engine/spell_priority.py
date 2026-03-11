"""Spell priority modes for the card play algorithm.

Each mode provides a different sort key for deciding which playable spell
to cast first when multiple spells are affordable.
"""

from __future__ import annotations

from enum import Enum
from functools import cmp_to_key
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from auto_goldfish.models.card import Card

VALID_SPELL_PRIORITIES = (
    "priority_then_cmc",
    "ramp_first",
    "value_first",
    "highest_cmc_first",
    "draw_first",
)


def _default_cmp(a: Card, b: Card) -> int:
    """Default comparison: priority -> land_priority -> cmc (ascending)."""
    if a.priority != b.priority:
        return -1 if a.priority < b.priority else 1
    if a.land_priority != b.land_priority:
        return -1 if a.land_priority < b.land_priority else 1
    if a.cmc != b.cmc:
        return -1 if a.cmc < b.cmc else 1
    return 0


def _category_order(card: Card, first: str) -> int:
    """Return a category rank for the card. Lower = played first.

    *first* is the category name to prioritize: "ramp", "draw", or "value".
    """
    if first == "ramp":
        if card.ramp:
            return 0
        if card.draw:
            return 1
        return 2
    elif first == "draw":
        if card.draw:
            return 0
        if card.ramp:
            return 1
        return 2
    else:  # value first
        if not card.ramp and not card.draw:
            return 0
        if card.draw:
            return 1
        return 2


def _make_category_cmp(first: str) -> Callable[[Card, Card], int]:
    """Build a comparator that prioritises a category then falls back to default."""

    def cmp(a: Card, b: Card) -> int:
        cat_a = _category_order(a, first)
        cat_b = _category_order(b, first)
        if cat_a != cat_b:
            return -1 if cat_a < cat_b else 1
        return _default_cmp(a, b)

    return cmp


def _highest_cmc_cmp(a: Card, b: Card) -> int:
    """Play the most expensive card first, break ties with default."""
    if a.cmc != b.cmc:
        return -1 if a.cmc > b.cmc else 1  # higher cmc = lower rank
    return _default_cmp(a, b)


def get_spell_sort_key(mode: str) -> Callable[[Card], object]:
    """Return a sort key function for the given spell priority mode.

    Cards are sorted ascending; the *last* element (via ``reversed()``) is
    played first.  So "lowest sort key" = "played last".

    For ``priority_then_cmc`` we return ``None`` to signal that the caller
    should use the default ``sorted(playables)`` which relies on
    ``Card.__lt__``.
    """
    if mode == "priority_then_cmc":
        return None  # type: ignore[return-value]
    elif mode == "ramp_first":
        return cmp_to_key(_make_category_cmp("ramp"))
    elif mode == "value_first":
        return cmp_to_key(_make_category_cmp("value"))
    elif mode == "highest_cmc_first":
        return cmp_to_key(_highest_cmc_cmp)
    elif mode == "draw_first":
        return cmp_to_key(_make_category_cmp("draw"))
    else:
        raise ValueError(
            f"Invalid spell_priority: {mode!r}. "
            f"Must be one of {VALID_SPELL_PRIORITIES}"
        )
