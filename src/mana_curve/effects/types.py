"""Effect protocols for the card effects system.

Uses ``typing.Protocol`` (structural typing) so effect classes don't need
to inherit from any base -- they just need to implement the right method.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from mana_curve.models.card import Card
    from mana_curve.models.game_state import GameState


@runtime_checkable
class OnPlayEffect(Protocol):
    """Triggered once when a card is played."""

    def on_play(self, card: Card, state: GameState) -> None: ...


@runtime_checkable
class PerTurnEffect(Protocol):
    """Triggered at the start of each turn after the card is on the battlefield."""

    def per_turn(self, card: Card, state: GameState) -> None: ...


@runtime_checkable
class CastTriggerEffect(Protocol):
    """Triggered whenever *another* spell is cast while this card is in play."""

    def cast_trigger(self, card: Card, casted_card: Card, state: GameState) -> None: ...


@runtime_checkable
class ManaFunctionEffect(Protocol):
    """A function that contributes to the mana calculation each turn."""

    def mana_function(self, state: GameState) -> int: ...
