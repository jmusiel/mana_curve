"""EffectRegistry -- maps card names to their effect descriptors."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class CardEffects:
    """Bundle of effects attached to a single card name.

    Each field is a list because a card can have multiple effects
    (e.g. The Great Henge produces mana AND draws on creature cast).
    """

    on_play: List[Any] = field(default_factory=list)
    per_turn: List[Any] = field(default_factory=list)
    cast_trigger: List[Any] = field(default_factory=list)
    mana_function: List[Any] = field(default_factory=list)
    priority: int = 0
    ramp: bool = False
    is_land_tutor: bool = False
    extra_types: List[str] | None = None
    override_cmc: int | None = None
    tapped: bool = False


class EffectRegistry:
    """Central registry mapping card names to their ``CardEffects``.

    Usage::

        registry = EffectRegistry()
        registry.register("Sol Ring", CardEffects(
            on_play=[ProduceMana(2)],
            ramp=True,
        ))
        effects = registry.get("Sol Ring")
    """

    def __init__(self) -> None:
        self._registry: Dict[str, CardEffects] = {}

    def register(self, name: str, effects: CardEffects) -> None:
        self._registry[name] = effects

    def register_many(self, names: list[str], effects: CardEffects) -> None:
        """Register the same effects for multiple card names."""
        for name in names:
            self._registry[name] = effects

    def get(self, name: str) -> CardEffects | None:
        return self._registry.get(name)

    def has(self, name: str) -> bool:
        return name in self._registry

    def all_names(self) -> list[str]:
        return list(self._registry.keys())

    def __len__(self) -> int:
        return len(self._registry)

    def __contains__(self, name: str) -> bool:
        return name in self._registry
