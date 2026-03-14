"""Deck configuration for optimization.

A DeckConfig represents a set of modifications to a base deck:
land count changes and added generic draw/ramp cards.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from auto_goldfish.optimization.candidate_cards import (
    ALL_CANDIDATES,
    CandidateCard,
)


@dataclass(frozen=True)
class DeckConfig:
    """Immutable, hashable description of deck modifications."""

    land_delta: int = 0
    added_cards: tuple[str, ...] = ()  # Candidate IDs

    def describe(self) -> str:
        """Human-readable compact description of changes vs base deck.

        Format: Draw2(mv2), Ramp+1(mv2), +1 land
        """
        parts: list[str] = []
        if self.land_delta > 0:
            parts.append(f"+{self.land_delta} land")
        elif self.land_delta < 0:
            parts.append(f"{self.land_delta} land")

        for card_id in self.added_cards:
            candidate = ALL_CANDIDATES.get(card_id)
            if candidate:
                parts.append(candidate.compact_label)
            else:
                parts.append(card_id)

        return ", ".join(parts) if parts else "Base deck (no changes)"

    @property
    def draw_count(self) -> int:
        return sum(
            1 for cid in self.added_cards
            if cid in ALL_CANDIDATES and ALL_CANDIDATES[cid].card_type == "draw"
        )

    @property
    def ramp_count(self) -> int:
        return sum(
            1 for cid in self.added_cards
            if cid in ALL_CANDIDATES and ALL_CANDIDATES[cid].card_type == "ramp"
        )


def enumerate_configs(
    enabled_candidates: Dict[str, CandidateCard],
    max_draw: int = 2,
    max_ramp: int = 2,
    land_range: int = 2,
    land_delta_min: Optional[int] = None,
    land_delta_max: Optional[int] = None,
) -> List[DeckConfig]:
    """Enumerate all valid deck configurations.

    Generates the full cross-product of:
    - Land deltas from land_delta_min to land_delta_max
      (defaults to -land_range..+land_range if not specified)
    - 0..max_draw draw candidates (combinations with replacement)
    - 0..max_ramp ramp candidates (combinations with replacement)

    Returns a list of unique DeckConfig instances including the base config.
    """
    from itertools import combinations_with_replacement

    draw_ids = sorted(
        cid for cid, c in enabled_candidates.items() if c.card_type == "draw"
    )
    ramp_ids = sorted(
        cid for cid, c in enabled_candidates.items() if c.card_type == "ramp"
    )

    # Generate all draw combinations (0 to max_draw picks)
    draw_combos: list[tuple[str, ...]] = [()]
    for k in range(1, max_draw + 1):
        draw_combos.extend(combinations_with_replacement(draw_ids, k))

    # Generate all ramp combinations (0 to max_ramp picks)
    ramp_combos: list[tuple[str, ...]] = [()]
    for k in range(1, max_ramp + 1):
        ramp_combos.extend(combinations_with_replacement(ramp_ids, k))

    lo = land_delta_min if land_delta_min is not None else -land_range
    hi = land_delta_max if land_delta_max is not None else land_range

    configs: list[DeckConfig] = []
    for land_delta in range(lo, hi + 1):
        for draw_cards in draw_combos:
            for ramp_cards in ramp_combos:
                added = tuple(sorted(draw_cards + ramp_cards))
                configs.append(DeckConfig(
                    land_delta=land_delta,
                    added_cards=added,
                ))

    return configs


def apply_config(
    goldfisher,
    config: DeckConfig,
    candidates: Dict[str, CandidateCard],
    swap_mode: bool = False,
) -> None:
    """Apply a DeckConfig to a Goldfisher instance, mutating its decklist.

    1. Reset to original decklist
    2. Apply land delta
    3. Inject synthetic candidate cards (with registry entries)
    4. If swap_mode, remove no-effect spells to maintain deck size
    """
    from auto_goldfish.effects.json_loader import build_overridden_registry

    # Reset to original state
    goldfisher.restore_original_decklist()

    # Apply land changes
    if config.land_delta != 0:
        target_lands = goldfisher.land_count + config.land_delta
        goldfisher.set_lands(target_lands)

    if not config.added_cards:
        return

    # Build registry with synthetic card entries
    overrides: Dict[str, dict] = {}
    cards_to_add: list[dict] = []
    for card_id in config.added_cards:
        candidate = candidates.get(card_id)
        if candidate is None:
            continue
        card_dict = candidate.to_card_dict()
        cards_to_add.append(card_dict)
        overrides[candidate.registry_name] = candidate.to_registry_override()

    if not cards_to_add:
        return

    # Update registry
    goldfisher.registry = build_overridden_registry(goldfisher.registry, overrides)

    # If swap mode, find no-effect spells to remove
    if swap_mode:
        _remove_no_effect_spells(goldfisher, len(cards_to_add))

    # Append synthetic cards to the decklist
    for card_dict in cards_to_add:
        idx = len(goldfisher.decklist)
        card = goldfisher._make_card(card_dict, idx)
        goldfisher.decklist.append(card)
        goldfisher.deckdict[card.name] = card


def _remove_no_effect_spells(goldfisher, count: int) -> None:
    """Remove up to `count` no-effect spells from the decklist.

    Prefers highest-CMC spells with no registered effects.
    """
    removable: list[tuple[int, int]] = []  # (index_in_decklist, cmc)
    for i, card in enumerate(goldfisher.decklist):
        if card.land or card.commander:
            continue
        effects = goldfisher.registry.get(card.name)
        if effects is not None:
            continue
        removable.append((i, card.cmc))

    # Sort by CMC descending — remove expensive no-ops first
    removable.sort(key=lambda x: -x[1])

    indices_to_remove = {idx for idx, _ in removable[:count]}
    if not indices_to_remove:
        return

    goldfisher.decklist = [
        c for i, c in enumerate(goldfisher.decklist) if i not in indices_to_remove
    ]
    # Rebuild indices and deckdict
    for i, card in enumerate(goldfisher.decklist):
        card.index = i
    goldfisher.deckdict = {c.name: c for c in goldfisher.decklist}
