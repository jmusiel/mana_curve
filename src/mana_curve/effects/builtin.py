"""Composable, reusable effect classes.

Each class implements one or more of the effect protocols from ``types.py``.
Cards are built by composing these -- no new classes needed per card.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from mana_curve.models.card import Card
    from mana_curve.models.game_state import GameState


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
        from mana_curve.engine.goldfisher import _draw
        for _ in range(self.amount):
            _draw(state)

    def describe(self) -> str:
        return f"Draw {self.amount} card{'s' if self.amount != 1 else ''}"


@dataclass
class DrawDiscard:
    """Draw then discard, then optionally draw again and make treasures."""
    first_draw: int = 0
    discard: int = 0
    second_draw: int = 0
    make_treasures: int = 0

    def on_play(self, card: Card, state: GameState) -> None:
        from mana_curve.engine.goldfisher import _draw, _random_discard
        for _ in range(self.first_draw):
            _draw(state)
        for _ in range(self.discard):
            if state.hand:
                _random_discard(state)
            else:
                break
        for _ in range(self.second_draw):
            _draw(state)
        state.treasure += self.make_treasures

    def describe(self) -> str:
        parts = []
        if self.first_draw:
            parts.append(f"Draw {self.first_draw}")
        if self.discard:
            parts.append(f"discard {self.discard}")
        if self.second_draw:
            parts.append(f"draw {self.second_draw}")
        if self.make_treasures:
            parts.append(f"{self.make_treasures} treasure{'s' if self.make_treasures != 1 else ''}")
        return ", ".join(parts) if parts else "Draw/discard"


@dataclass
class ReduceCost:
    """Reduce the cost of certain spell types when played."""
    nonpermanent: int = 0
    permanent: int = 0
    spell: int = 0
    creature: int = 0
    enchantment: int = 0

    def on_play(self, card: Card, state: GameState) -> None:
        state.nonpermanent_cost_reduction += self.nonpermanent
        state.permanent_cost_reduction += self.permanent
        state.spell_cost_reduction += self.spell
        state.creature_cost_reduction += self.creature
        state.enchantment_cost_reduction += self.enchantment

    def describe(self) -> str:
        reductions = []
        for attr in ("creature", "enchantment", "permanent", "nonpermanent", "spell"):
            val = getattr(self, attr)
            if val:
                reductions.append(f"{attr.capitalize()} costs -{val}")
        return "; ".join(reductions) if reductions else "Cost reduction"


@dataclass
class TutorToHand:
    """Search deck for the first available target and put it in hand."""
    targets: List[str]

    def on_play(self, card: Card, state: GameState) -> None:
        from mana_curve.engine.goldfisher import _find_card_by_name
        for target_name in self.targets:
            target = _find_card_by_name(state, target_name)
            if target is not None and target.zone is state.deck:
                if state.should_log:
                    state.log.append(f"Tutored {target.printable}")
                target.change_zone(state.hand)
                return
            elif target is not None:
                if state.should_log:
                    state.log.append(f"Failed to find {target.printable}")

    def describe(self) -> str:
        names = ", ".join(self.targets[:3])
        if len(self.targets) > 3:
            names += ", ..."
        return f"Tutor: {names}"


# ---------------------------------------------------------------------------
# PerTurn effects
# ---------------------------------------------------------------------------

@dataclass
class PerTurnDraw:
    """Draw N cards at the start of each turn (e.g. Phyrexian Arena)."""
    amount: int = 1

    def per_turn(self, card: Card, state: GameState) -> None:
        from mana_curve.engine.goldfisher import _draw
        for _ in range(self.amount):
            _draw(state)

    def describe(self) -> str:
        return f"Draw {self.amount} per turn"


@dataclass
class ScalingMana:
    """Gain additional mana production each turn (e.g. As Foretold)."""
    amount: int = 1

    def per_turn(self, card: Card, state: GameState) -> None:
        state.mana_production += self.amount

    def describe(self) -> str:
        return f"+{self.amount} mana per turn (scaling)"


# ---------------------------------------------------------------------------
# CastTrigger effects
# ---------------------------------------------------------------------------

@dataclass
class PerCastDraw:
    """Draw when a spell of the right type is cast."""
    nonpermanent: int = 0
    spell: int = 0
    creature: int = 0
    enchantment: int = 0

    def cast_trigger(self, card: Card, casted_card: Card, state: GameState) -> None:
        from mana_curve.engine.goldfisher import _draw
        draws = 0
        if casted_card.nonpermanent:
            draws += self.nonpermanent
        if casted_card.spell:
            draws += self.spell
        if casted_card.creature:
            draws += self.creature
        if casted_card.enchantment:
            draws += self.enchantment
        for _ in range(draws):
            _draw(state)

    def describe(self) -> str:
        triggers = []
        for attr in ("creature", "enchantment", "nonpermanent", "spell"):
            val = getattr(self, attr)
            if val:
                triggers.append(f"Draw {val} on {attr} cast")
        return "; ".join(triggers) if triggers else "Draw on cast"


# ---------------------------------------------------------------------------
# ManaFunction effects
# ---------------------------------------------------------------------------

@dataclass
class CryptolithRitesMana:
    """Tap creatures for mana (Cryptolith Rite / Gemhide Sliver)."""

    def mana_function(self, state: GameState) -> int:
        mana = max(0, state.creatures_played - state.tapped_creatures_this_turn)
        state.tapped_creatures_this_turn = state.creatures_played
        return mana

    def describe(self) -> str:
        return "Tap creatures for mana"


@dataclass
class EnchantmentSanctumMana:
    """Produce mana equal to enchantments played (Serra's Sanctum)."""

    def mana_function(self, state: GameState) -> int:
        return state.enchantments_played

    def describe(self) -> str:
        return "Mana from enchantments"
