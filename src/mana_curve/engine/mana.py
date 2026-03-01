"""Mana calculation functions.

Each function takes a ``GameState`` and returns the mana contributed by
that source. The engine sums all functions to compute available mana.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mana_curve.models.game_state import GameState


def land_mana(state: GameState) -> int:
    """Mana from lands in play."""
    return len(state.lands)


def mana_rocks(state: GameState) -> int:
    """Mana from rocks / fixed mana producers."""
    return state.mana_production
