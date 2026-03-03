"""Load card effects from a JSON data file into an EffectRegistry."""

from __future__ import annotations

import dataclasses
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


def build_overridden_registry(
    base: EffectRegistry, overrides: Dict[str, Dict[str, Any]]
) -> EffectRegistry:
    """Create a copy of *base* with user overrides applied.

    *overrides* maps card names to dicts matching the per-card JSON structure::

        {"Sol Ring": {"effects": [{"type": "produce_mana", "slot": "on_play",
                                   "params": {"amount": 3}}], "ramp": true}}
    """
    registry = base.copy()
    for card_name, card_data in overrides.items():
        effect_list = card_data.get("effects", [])
        slots: Dict[str, list] = {s: [] for s in VALID_SLOTS}
        for effect_data in effect_list:
            slot = effect_data["slot"]
            if slot not in VALID_SLOTS:
                raise ValueError(
                    f"Invalid slot {slot!r} for override card {card_name!r}"
                )
            slots[slot].append(_hydrate_effect(effect_data))

        metadata = _merge_metadata({}, card_data)
        card_effects = CardEffects(
            on_play=slots["on_play"],
            per_turn=slots["per_turn"],
            cast_trigger=slots["cast_trigger"],
            mana_function=slots["mana_function"],
            **metadata,
        )
        registry.register(card_name, card_effects)
    return registry


# Maps effect classes to their canonical slot based on which protocol they implement.
_CLASS_SLOT_MAP: Dict[type, str] = {}
for _type_str, _cls in TYPE_MAP.items():
    for _method, _slot in [
        ("on_play", "on_play"),
        ("per_turn", "per_turn"),
        ("cast_trigger", "cast_trigger"),
        ("mana_function", "mana_function"),
    ]:
        if hasattr(_cls, _method) and callable(getattr(_cls, _method)):
            _CLASS_SLOT_MAP[_cls] = _slot
            break


def _python_type_name(t: Any) -> str:
    """Return a JSON-friendly type name for a dataclass field type.

    Handles both real types and string annotations (from __future__ annotations).
    """
    if isinstance(t, str):
        t_lower = t.strip().lower()
        for name in ("int", "float", "bool", "str"):
            if t_lower == name:
                return name
        if t_lower.startswith("list"):
            return "list"
        return "str"
    if t is int:
        return "int"
    if t is float:
        return "float"
    if t is bool:
        return "bool"
    if t is str:
        return "str"
    origin = getattr(t, "__origin__", None)
    if origin is list:
        return "list"
    return "str"


def get_effect_schema() -> Dict[str, Any]:
    """Return a JSON-serializable schema describing all available effect types.

    Example output::

        {"produce_mana": {"label": "ProduceMana", "slot": "on_play",
                          "params": {"amount": {"type": "int", "default": 1}}}}
    """
    schema: Dict[str, Any] = {}
    for type_str, cls in TYPE_MAP.items():
        slot = _CLASS_SLOT_MAP.get(cls, "on_play")
        params: Dict[str, Any] = {}
        if dataclasses.is_dataclass(cls):
            for f in dataclasses.fields(cls):
                param_info: Dict[str, Any] = {"type": _python_type_name(f.type)}
                if f.default is not dataclasses.MISSING:
                    param_info["default"] = f.default
                elif f.default_factory is not dataclasses.MISSING:
                    param_info["default"] = f.default_factory()
                params[f.name] = param_info
        schema[type_str] = {
            "label": cls.__name__,
            "slot": slot,
            "params": params,
        }
    return schema
