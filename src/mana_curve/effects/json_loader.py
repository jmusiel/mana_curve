"""Load card effects from a JSON data file into an EffectRegistry."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from .builtin import (
    CryptolithRitesMana,
    DrawCards,
    DrawDiscard,
    EnchantmentSanctumMana,
    PerCastDraw,
    PerTurnDraw,
    ProduceMana,
    ReduceCost,
    ScalingMana,
    TutorToHand,
)
from .registry import CardEffects, EffectRegistry

# Maps JSON type strings to effect classes.
TYPE_MAP: Dict[str, type] = {
    "produce_mana": ProduceMana,
    "draw_cards": DrawCards,
    "draw_discard": DrawDiscard,
    "reduce_cost": ReduceCost,
    "tutor_to_hand": TutorToHand,
    "per_turn_draw": PerTurnDraw,
    "scaling_mana": ScalingMana,
    "per_cast_draw": PerCastDraw,
    "cryptolith_rites_mana": CryptolithRitesMana,
    "enchantment_sanctum_mana": EnchantmentSanctumMana,
}

VALID_SLOTS = {"on_play", "per_turn", "cast_trigger", "mana_function"}

METADATA_FIELDS = {"priority", "ramp", "is_land_tutor", "extra_types", "override_cmc", "tapped"}

_DEFAULT_JSON = Path(__file__).parent / "card_effects.json"


def _hydrate_effect(effect_data: dict) -> Any:
    """Instantiate an effect class from a JSON effect descriptor."""
    type_str = effect_data["type"]
    if type_str not in TYPE_MAP:
        raise ValueError(f"Unknown effect type: {type_str!r}")
    cls = TYPE_MAP[type_str]
    params = effect_data.get("params", {})
    return cls(**params)


def _merge_metadata(defaults: dict, card_data: dict) -> dict:
    """Merge group defaults with per-card overrides for metadata fields."""
    merged = {}
    for field in METADATA_FIELDS:
        if field in card_data:
            merged[field] = card_data[field]
        elif field in defaults:
            merged[field] = defaults[field]
    return merged


def load_registry_from_json(path: Path | str | None = None) -> EffectRegistry:
    """Read the JSON card effects file and return a populated EffectRegistry."""
    if path is None:
        path = _DEFAULT_JSON
    path = Path(path)

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    registry = EffectRegistry()
    seen_names: set[str] = set()

    for group in data["groups"]:
        defaults = group.get("defaults", {})
        default_effects = defaults.get("effects", [])

        for card_name, card_data in group["cards"].items():
            if card_name in seen_names:
                raise ValueError(f"Duplicate card name: {card_name!r}")
            seen_names.add(card_name)

            # Use card-level effects if present, otherwise group default effects
            effect_list = card_data.get("effects", default_effects)

            # Build slot lists
            slots: Dict[str, list] = {s: [] for s in VALID_SLOTS}
            for effect_data in effect_list:
                slot = effect_data["slot"]
                if slot not in VALID_SLOTS:
                    raise ValueError(
                        f"Invalid slot {slot!r} for card {card_name!r}"
                    )
                slots[slot].append(_hydrate_effect(effect_data))

            # Merge metadata
            metadata = _merge_metadata(defaults, card_data)

            card_effects = CardEffects(
                on_play=slots["on_play"],
                per_turn=slots["per_turn"],
                cast_trigger=slots["cast_trigger"],
                mana_function=slots["mana_function"],
                **metadata,
            )
            registry.register(card_name, card_effects)

    return registry
