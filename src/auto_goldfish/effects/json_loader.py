"""Load card effects from a JSON data file into an EffectRegistry.

Version 2 format uses *categories* (land, ramp, draw, discard) instead of
the old type/slot/params descriptors.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .builtin import (
    DiscardCards,
    DrawCards,
    ImmediateMana,
    LandToBattlefield,
    PerCastDraw,
    PerTurnDraw,
    ProduceMana,
    ReduceCost,
)
from .registry import CardEffects, EffectRegistry

VALID_SLOTS = {"on_play", "per_turn", "cast_trigger", "mana_function"}

METADATA_FIELDS = {"priority", "ramp", "extra_types", "override_cmc", "tapped"}

_DEFAULT_JSON = Path(__file__).parent / "card_effects.json"

VALID_CATEGORIES = {"land", "ramp", "draw", "discard"}


def _translate_category(cat: dict) -> Tuple[List[Tuple[str, Any]], dict]:
    """Convert a single category dict to (slot, effect) pairs and metadata.

    Returns ``(effects, meta)`` where *effects* is a list of
    ``(slot_name, effect_instance)`` tuples and *meta* is a dict of
    derived metadata (``ramp``, ``tapped``, etc.).
    """
    category = cat["category"]
    if category not in VALID_CATEGORIES:
        raise ValueError(f"Unknown category: {category!r}")

    effects: List[Tuple[str, Any]] = []
    meta: dict = {}

    if category == "land":
        if cat.get("tapped", False):
            meta["tapped"] = True

    elif category == "ramp":
        meta["ramp"] = True
        immediate = cat.get("immediate", False)

        if "producer" in cat:
            prod = cat["producer"]
            amount = prod["mana_amount"]
            if immediate:
                effects.append(("on_play", ImmediateMana(amount=amount)))
            else:
                effects.append(("on_play", ProduceMana(amount=amount)))
                if prod.get("tempo") in ("tapped", "summoning_sick"):
                    meta["tapped"] = True

        elif "land_to_battlefield" in cat:
            ltb = cat["land_to_battlefield"]
            tapped = ltb.get("tempo", "tapped") == "tapped"
            effects.append(("on_play", LandToBattlefield(
                count=ltb["count"], tapped=tapped,
            )))

        elif "reducer" in cat:
            red = cat["reducer"]
            effects.append(("on_play", ReduceCost(
                spell_type=red["spell_type"], amount=red["amount"],
            )))

    elif category == "draw":
        immediate = cat.get("immediate", True)
        if immediate:
            effects.append(("on_play", DrawCards(amount=cat["amount"])))
        elif "per_turn" in cat:
            effects.append(("per_turn", PerTurnDraw(
                amount=cat["per_turn"]["amount"],
            )))
        elif "per_cast" in cat:
            pc = cat["per_cast"]
            effects.append(("cast_trigger", PerCastDraw(
                amount=pc["amount"], trigger=pc["trigger"],
            )))

    elif category == "discard":
        effects.append(("on_play", DiscardCards(amount=cat["amount"])))

    return effects, meta


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
        default_categories = defaults.get("categories", [])

        for card_name, card_data in group["cards"].items():
            if card_name in seen_names:
                raise ValueError(f"Duplicate card name: {card_name!r}")
            seen_names.add(card_name)

            categories = card_data.get("categories", default_categories)

            # Translate categories to effects + derived metadata
            slots: Dict[str, list] = {s: [] for s in VALID_SLOTS}
            derived_meta: dict = {}
            for cat in categories:
                effects, meta = _translate_category(cat)
                for slot, effect in effects:
                    slots[slot].append(effect)
                derived_meta.update(meta)

            # Explicit metadata (group defaults + card overrides) wins over derived
            explicit_meta = _merge_metadata(defaults, card_data)
            final_meta = {**derived_meta, **explicit_meta}

            card_effects = CardEffects(
                on_play=slots["on_play"],
                per_turn=slots["per_turn"],
                cast_trigger=slots["cast_trigger"],
                mana_function=slots["mana_function"],
                **final_meta,
            )
            registry.register(card_name, card_effects)

    return registry


def build_overridden_registry(
    base: EffectRegistry, overrides: Dict[str, Dict[str, Any]]
) -> EffectRegistry:
    """Create a copy of *base* with user overrides applied.

    *overrides* maps card names to dicts using the category format::

        {"Sol Ring": {"categories": [{"category": "ramp", "immediate": false,
                       "producer": {"mana_amount": 3}}]}}
    """
    registry = base.copy()
    for card_name, card_data in overrides.items():
        categories = card_data.get("categories", [])

        slots: Dict[str, list] = {s: [] for s in VALID_SLOTS}
        derived_meta: dict = {}
        for cat in categories:
            effects, meta = _translate_category(cat)
            for slot, effect in effects:
                slots[slot].append(effect)
            derived_meta.update(meta)

        explicit_meta = _merge_metadata({}, card_data)
        final_meta = {**derived_meta, **explicit_meta}

        card_effects = CardEffects(
            on_play=slots["on_play"],
            per_turn=slots["per_turn"],
            cast_trigger=slots["cast_trigger"],
            mana_function=slots["mana_function"],
            **final_meta,
        )
        registry.register(card_name, card_effects)
    return registry


def get_effect_schema() -> Dict[str, Any]:
    """Return a JSON-serializable schema describing the category format.

    Used by the web UI to build the effect editor.
    """
    return {
        "categories": {
            "land": {
                "fields": {
                    "tapped": {"type": "bool", "default": False},
                },
            },
            "ramp": {
                "fields": {
                    "immediate": {"type": "bool", "default": False},
                },
                "variants": {
                    "producer": {
                        "fields": {
                            "mana_amount": {"type": "int"},
                            "producer_type": {
                                "type": "str",
                                "options": ["rock", "dork", "aura", "land"],
                            },
                            "tempo": {
                                "type": "str",
                                "options": ["untapped", "tapped", "summoning_sick"],
                            },
                        },
                    },
                    "land_to_battlefield": {
                        "fields": {
                            "count": {"type": "int", "default": 1},
                            "tempo": {
                                "type": "str",
                                "options": ["tapped", "untapped"],
                                "default": "tapped",
                            },
                        },
                    },
                    "reducer": {
                        "fields": {
                            "spell_type": {
                                "type": "str",
                                "options": [
                                    "creature", "enchantment",
                                    "nonpermanent", "permanent", "spell",
                                ],
                            },
                            "amount": {"type": "int", "default": 1},
                        },
                    },
                },
            },
            "draw": {
                "fields": {
                    "immediate": {"type": "bool", "default": True},
                    "amount": {"type": "int", "description": "For immediate draw"},
                },
                "variants": {
                    "per_turn": {
                        "fields": {"amount": {"type": "int", "default": 1}},
                    },
                    "per_cast": {
                        "fields": {
                            "amount": {"type": "int", "default": 1},
                            "trigger": {
                                "type": "str",
                                "options": [
                                    "spell", "creature", "enchantment",
                                    "land", "artifact", "nonpermanent",
                                ],
                            },
                        },
                    },
                },
            },
            "discard": {
                "fields": {"amount": {"type": "int"}},
            },
        },
        "metadata": {
            "priority": {"type": "int", "default": 0},
            "override_cmc": {"type": "int"},
            "extra_types": {"type": "list"},
        },
    }
