"""Shared helpers for card effect labels in the web UI."""

from __future__ import annotations

from auto_goldfish.effects.builtin import (
    DiscardCards,
    DrawCards,
    ImmediateMana,
    LandToBattlefield,
    PerCastDraw,
    PerTurnDraw,
    ProduceMana,
    ReduceCost,
)


def effects_to_override(card_effects):
    """Convert a CardEffects instance to the category-based override format."""
    categories = []
    for effect in card_effects.on_play:
        if isinstance(effect, ProduceMana):
            categories.append({"category": "ramp", "immediate": False,
                               "producer": {"mana_amount": effect.amount}})
        elif isinstance(effect, ImmediateMana):
            categories.append({"category": "ramp", "immediate": True,
                               "producer": {"mana_amount": effect.amount}})
        elif isinstance(effect, LandToBattlefield):
            tempo = "tapped" if effect.tapped else "untapped"
            categories.append({"category": "ramp", "immediate": True,
                               "land_to_battlefield": {"count": effect.count, "tempo": tempo}})
        elif isinstance(effect, ReduceCost):
            categories.append({"category": "ramp", "immediate": False,
                               "reducer": {"spell_type": effect.spell_type, "amount": effect.amount}})
        elif isinstance(effect, DrawCards):
            categories.append({"category": "draw", "immediate": True, "amount": effect.amount})
        elif isinstance(effect, DiscardCards):
            categories.append({"category": "discard", "amount": effect.amount})
    for effect in card_effects.per_turn:
        if isinstance(effect, PerTurnDraw):
            categories.append({"category": "draw", "immediate": False,
                               "per_turn": {"amount": effect.amount}})
    for effect in card_effects.cast_trigger:
        if isinstance(effect, PerCastDraw):
            categories.append({"category": "draw", "immediate": False,
                               "per_cast": {"amount": effect.amount, "trigger": effect.trigger}})

    result = {"categories": categories}
    if card_effects.priority:
        result["priority"] = card_effects.priority
    return result


def describe_effects(card_effects):
    """Build a compact technical description of a CardEffects instance."""
    parts = []
    for effect in card_effects.on_play:
        parts.append(f"{type(effect).__name__}({', '.join(f'{k}={v}' for k, v in vars(effect).items())})" if vars(effect) else type(effect).__name__)
    for effect in card_effects.per_turn:
        parts.append(f"{type(effect).__name__}({', '.join(f'{k}={v}' for k, v in vars(effect).items())})" if vars(effect) else type(effect).__name__)
    for effect in card_effects.cast_trigger:
        parts.append(f"{type(effect).__name__}({', '.join(f'{k}={v}' for k, v in vars(effect).items())})" if vars(effect) else type(effect).__name__)
    for effect in card_effects.mana_function:
        parts.append(type(effect).__name__)
    return ", ".join(parts) if parts else ""


def describe_annotation(annotation) -> str:
    """Human-readable label for a category annotation."""
    if not annotation or not annotation.get("categories"):
        return "No effects"

    parts = []
    for category in annotation.get("categories", []):
        if category.get("category") == "ramp":
            producer = category.get("producer")
            if producer:
                text = f"Ramp: produces {producer.get('mana_amount', 1)} mana"
                if category.get("immediate"):
                    text += " immediately"
                parts.append(text)
                continue
            land = category.get("land_to_battlefield")
            if land:
                parts.append(
                    f"Ramp: fetch {land.get('count', 1)} land {land.get('tempo', 'tapped')}"
                )
                continue
            reducer = category.get("reducer")
            if reducer:
                parts.append(
                    f"Ramp: reduce {reducer.get('spell_type', 'spell')} cost by {reducer.get('amount', 1)}"
                )
                continue
            parts.append("Ramp")
        elif category.get("category") == "draw":
            if category.get("immediate"):
                parts.append(f"Draw {category.get('amount', 1)}")
                continue
            per_turn = category.get("per_turn")
            if per_turn:
                parts.append(f"Draw {per_turn.get('amount', 1)} per turn")
                continue
            per_cast = category.get("per_cast")
            if per_cast:
                parts.append(
                    f"Draw {per_cast.get('amount', 1)} per {per_cast.get('trigger', 'spell')}"
                )
                continue
            parts.append("Draw")
        elif category.get("category") == "discard":
            parts.append(f"Discard {category.get('amount', 1)}")
        elif category.get("category") == "land":
            parts.append("Land")
        else:
            parts.append(str(category.get("category") or "Effect"))
    return ", ".join(parts) if parts else "No effects"
