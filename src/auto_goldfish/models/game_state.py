"""Mutable game state extracted from the Goldfisher class."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional

from .card import Card


@dataclass
class GameState:
    """All mutable state for a single goldfishing game.

    Extracted from the old ``Goldfisher`` so that state is inspectable,
    serializable, and testable in isolation.
    """

    # Zones (lists of card indices into the decklist)
    command_zone: List[int] = field(default_factory=list)
    deck: List[int] = field(default_factory=list)
    hand: List[int] = field(default_factory=list)
    battlefield: List[int] = field(default_factory=list)
    yard: List[int] = field(default_factory=list)
    exile: List[int] = field(default_factory=list)
    lands: List[int] = field(default_factory=list)

    # Turn counters
    turn: int = 0
    draws: int = 0
    played_land_this_turn: int = 0
    untapped_land_this_turn: int = 0
    tapped_creatures_this_turn: int = 0
    lands_per_turn: int = 1

    # Mana state
    mana_production: int = 0
    treasure: int = 0

    # Cost reductions
    nonpermanent_cost_reduction: int = 0
    permanent_cost_reduction: int = 0
    spell_cost_reduction: int = 0
    creature_cost_reduction: int = 0
    enchantment_cost_reduction: int = 0

    # Played counters
    creatures_played: int = 0
    enchantments_played: int = 0
    artifacts_played: int = 0

    # Effect tracking (populated by the engine)
    per_turn_effects: List[Any] = field(default_factory=list)
    cast_triggers: List[Any] = field(default_factory=list)
    mana_functions: List[Callable] = field(default_factory=list)

    # Starting hand info
    starting_hand: List[Card] = field(default_factory=list)
    starting_hand_land_count: Optional[int] = None

    # Per-card cast turn tracking (one slot per card in decklist)
    card_cast_turn: List[Optional[int]] = field(default_factory=list)

    # Game log
    log: List[str] = field(default_factory=list)
    should_log: bool = True

    # References to the decklist (set by engine, used by module-level helpers)
    decklist: List[Card] = field(default_factory=list, repr=False)
    deckdict: dict = field(default_factory=dict, repr=False)

    # Card play algorithm settings (set by engine from Goldfisher config)
    min_cost_floor: int = 1
