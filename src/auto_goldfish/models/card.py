"""Card dataclass -- pure data, no simulation logic."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Card:
    """Represents a single Magic: The Gathering card.

    Parameters
    ----------
    name : str
        Card name (e.g. "Sol Ring").
    cmc : int
        Converted mana cost used by the simulation (may differ from oracle_cmc
        when the user overrides it in Archidekt).
    cost : str
        Mana cost string (e.g. "{1}{U}").
    text : str
        Oracle text (lowercased on creation).
    types : list[str]
        Card types (e.g. ["creature", "artifact"]).
    """

    name: str = ""
    quantity: int = 1
    oracle_cmc: int = 0
    cmc: int = 0
    cost: str = ""
    text: str = ""
    sub_types: List[str] = field(default_factory=list)
    super_types: List[str] = field(default_factory=list)
    types: List[str] = field(default_factory=list)
    identity: List[str] = field(default_factory=list)
    default_category: Optional[str] = None
    user_category: Optional[str] = None
    tag: Optional[str] = None
    commander: bool = False
    index: int = 0

    # Derived type flags (set in __post_init__)
    spell: bool = field(init=False, default=False)
    permanent: bool = field(init=False, default=False)
    nonpermanent: bool = field(init=False, default=False)
    creature: bool = field(init=False, default=False)
    land: bool = field(init=False, default=False)
    artifact: bool = field(init=False, default=False)
    enchantment: bool = field(init=False, default=False)
    planeswalker: bool = field(init=False, default=False)
    battle: bool = field(init=False, default=False)
    instant: bool = field(init=False, default=False)
    sorcery: bool = field(init=False, default=False)
    mdfc: bool = field(init=False, default=False)

    # Simulation state (mutated during a game)
    zone: Optional[list] = field(init=False, default=None, repr=False)
    tapped: bool = field(init=False, default=False)
    mana_spent_when_played: int = field(init=False, default=0, repr=False)

    # Sorting keys
    priority: int = field(init=False, default=0)
    land_priority: int = field(init=False, default=0)
    ramp: bool = field(init=False, default=False)
    draw: bool = field(init=False, default=False)

    def __post_init__(self) -> None:
        self.cost = self.cost.lower() if self.cost else ""
        self.text = self.text.lower() if self.text else ""
        self.sub_types = [t.lower() for t in self.sub_types]
        self.types = [t.lower() for t in self.types]
        self.super_types = [t.lower() for t in self.super_types]

        for t in self.types:
            if t == "instant":
                self.instant = self.spell = self.nonpermanent = True
            elif t == "sorcery":
                self.sorcery = self.spell = self.nonpermanent = True
            elif t == "creature":
                self.creature = self.spell = self.permanent = True
            elif t == "artifact":
                self.artifact = self.spell = self.permanent = True
            elif t == "enchantment":
                self.enchantment = self.spell = self.permanent = True
            elif t == "planeswalker":
                self.planeswalker = self.spell = self.permanent = True
            elif t == "battle":
                self.battle = self.spell = self.permanent = True
            elif t == "land":
                self.land = self.permanent = True

        if self.land and self.spell:
            self.mdfc = True
            self.land_priority = -1

    @property
    def printable(self) -> str:
        if self.land and not self.spell:
            return f"(Land) {self.name}"
        return self.name

    @property
    def unique_name(self) -> str:
        return f"{self.name} ({self.index})"

    # -- zone helpers ----------------------------------------------------------

    def change_zone(self, new_zone: list) -> None:
        """Move this card from its current zone to *new_zone*."""
        if self.zone is not None:
            self.zone.remove(self.index)
        self.zone = new_zone
        new_zone.append(self.index)

    # -- cost helpers ----------------------------------------------------------

    def get_current_cost(self, game_state) -> int:
        """Return effective cost after all cost reductions from *game_state*."""
        cost = self.cmc
        if self.nonpermanent:
            cost -= game_state.nonpermanent_cost_reduction
        if self.permanent:
            cost -= game_state.permanent_cost_reduction
        if self.spell:
            cost -= game_state.spell_cost_reduction
        if self.creature:
            cost -= game_state.creature_cost_reduction
        if self.enchantment:
            cost -= game_state.enchantment_cost_reduction
        return max(1, cost)

    # -- ordering --------------------------------------------------------------

    def __lt__(self, other: Card) -> bool:
        if self.priority != other.priority:
            return self.priority < other.priority
        if self.land_priority != other.land_priority:
            return self.land_priority < other.land_priority
        return self.cmc < other.cmc

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Card):
            return NotImplemented
        return self.name == other.name

    def __hash__(self) -> int:
        return hash(self.name)

    def __str__(self) -> str:
        return f"{self.name}: {self.cost}"

    def __repr__(self) -> str:
        return f"Card({self.name!r}, cmc={self.cmc})"
