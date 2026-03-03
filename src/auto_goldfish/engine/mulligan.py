"""Mulligan strategy.

The default strategy keeps a hand with 3-4 lands, or accepts any hand
smaller than 7 cards (after a previous mulligan).

The curve-aware strategy additionally considers whether the hand has
playable early spells and ramp.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from auto_goldfish.models.game_state import GameState


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


class CurveAwareMulligan:
    """Smarter mulligan that considers curve and ramp.

    Keeps a hand if:
    - Already mulliganed (hand_size < 7)
    - Has 3-4 lands AND at least one playable spell in turns 1-3
    - Has 2 lands but includes ramp (mana rock / dork)
    - Has 3-4 lands (fallback, same as default)
    """

    def should_keep(self, state: GameState, hand_size: int, lands_in_hand: int) -> bool:
        # Always keep after first mulligan
        if hand_size < 7:
            return True

        # Count playable early spells and ramp in hand
        has_ramp = False
        early_spells = 0
        for i in state.hand:
            card = state.decklist[i]
            if card.land:
                continue
            if card.ramp and card.cmc <= 2:
                has_ramp = True
            if card.spell and card.cmc <= 3:
                early_spells += 1

        # 3-4 lands with early plays: great hand
        if 3 <= lands_in_hand <= 4 and early_spells >= 1:
            return True

        # 2 lands with ramp: keepable (ramp compensates for fewer lands)
        if lands_in_hand == 2 and has_ramp:
            return True

        # 3-4 lands without early plays: still acceptable
        if 3 <= lands_in_hand <= 4:
            return True

        return False
