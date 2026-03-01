"""Mulligan strategy.

The default strategy keeps a hand with 3-4 lands, or accepts any hand
smaller than 7 cards (after a previous mulligan).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from mana_curve.models.game_state import GameState


class MulliganStrategy(Protocol):
    """Protocol for pluggable mulligan strategies."""

    def should_keep(self, state: GameState, hand_size: int, lands_in_hand: int) -> bool: ...


class DefaultMulligan:
    """Keep if 3-4 lands in hand, or if already mulliganed below 7."""

    def should_keep(self, state: GameState, hand_size: int, lands_in_hand: int) -> bool:
        if lands_in_hand > 2 and lands_in_hand < 5:
            return True
        if hand_size < 7:
            return True
        return False
