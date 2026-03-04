"""Composable, reusable effect classes.

Each class implements one or more of the effect protocols from ``types.py``.
Cards are built by composing these -- no new classes needed per card.

Classes (8 total):
  OnPlay:       ProduceMana, DrawCards, ImmediateMana, LandToBattlefield,
                DiscardCards, ReduceCost
  PerTurn:      PerTurnDraw
  CastTrigger:  PerCastDraw
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from auto_goldfish.models.card import Card
    from auto_goldfish.models.game_state import GameState


# ---------------------------------------------------------------------------
# OnPlay effects
# ---------------------------------------------------------------------------

@dataclass
class ProduceMana:
    """Adds fixed mana production when played (e.g. Sol Ring adds 2)."""
    amount: int = 1

    def on_play(self, card: Card, state: GameState) -> None:
        state.mana_production += self.amount

    def describe(self) -> str:
        return f"+{self.amount} mana"


@dataclass
class DrawCards:
    """Draw N cards when played (e.g. Rishkar's Expertise draws 4)."""
    amount: int = 1

    def on_play(self, card: Card, state: GameState) -> None:
        from auto_goldfish.engine.goldfisher import _draw
        for _ in range(self.amount):
            _draw(state)

    def describe(self) -> str:
        return f"Draw {self.amount} card{'s' if self.amount != 1 else ''}"


@dataclass
class ImmediateMana:
    """One-shot mana added as treasure (e.g. Dark Ritual adds 3)."""
    amount: int = 1

    def on_play(self, card: Card, state: GameState) -> None:
        state.treasure += self.amount

    def describe(self) -> str:
        return f"+{self.amount} treasure"


@dataclass
class LandToBattlefield:
    """Search deck for basic/effectless lands and put them onto the battlefield."""
    count: int = 1
    tapped: bool = True

    def on_play(self, card: Card, state: GameState) -> None:
        from auto_goldfish.engine.goldfisher import _find_effectless_lands
        land_indices = _find_effectless_lands(state, self.count)
        for idx in land_indices:
            land_card = state.decklist[idx]
            land_card.change_zone(state.lands)
            if not self.tapped:
                state.untapped_land_this_turn += 1
            if state.should_log:
                tap_str = " (tapped)" if self.tapped else ""
                state.log.append(f"Fetched {land_card.printable}{tap_str}")

    def describe(self) -> str:
        tap_str = " tapped" if self.tapped else " untapped"
        return f"Fetch {self.count} land{'s' if self.count != 1 else ''}{tap_str}"


@dataclass
class DiscardCards:
    """Discard N random cards from hand."""
    amount: int = 1

    def on_play(self, card: Card, state: GameState) -> None:
        from auto_goldfish.engine.goldfisher import _random_discard
        for _ in range(self.amount):
            if state.hand:
                _random_discard(state)
            else:
                break

    def describe(self) -> str:
        return f"Discard {self.amount}"


@dataclass
class ReduceCost:
    """Reduce the cost of a spell type when played."""
    spell_type: str = "creature"
    amount: int = 1

    def on_play(self, card: Card, state: GameState) -> None:
        attr = f"{self.spell_type}_cost_reduction"
        setattr(state, attr, getattr(state, attr) + self.amount)

    def describe(self) -> str:
        return f"{self.spell_type.capitalize()} costs -{self.amount}"


# ---------------------------------------------------------------------------
# PerTurn effects
# ---------------------------------------------------------------------------

@dataclass
class PerTurnDraw:
    """Draw N cards at the start of each turn (e.g. Phyrexian Arena)."""
    amount: int = 1

    def per_turn(self, card: Card, state: GameState) -> None:
        from auto_goldfish.engine.goldfisher import _draw
        for _ in range(self.amount):
            _draw(state)

    def describe(self) -> str:
        return f"Draw {self.amount} per turn"


# ---------------------------------------------------------------------------
# CastTrigger effects
# ---------------------------------------------------------------------------

@dataclass
class PerCastDraw:
    """Draw when a spell of the right type is cast.

    ``trigger`` is one of: "spell", "creature", "enchantment", "land",
    "artifact", "nonpermanent".
    """
    amount: int = 1
    trigger: str = "spell"

    def cast_trigger(self, card: Card, casted_card: Card, state: GameState) -> None:
        from auto_goldfish.engine.goldfisher import _draw
        if getattr(casted_card, self.trigger, False):
            for _ in range(self.amount):
                _draw(state)

    def describe(self) -> str:
        return f"Draw {self.amount} on {self.trigger} cast"
