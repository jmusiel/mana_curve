"""Validate LLM-generated card labels against the category schema."""

from __future__ import annotations

from auto_goldfish.effects.json_loader import METADATA_FIELDS, VALID_CATEGORIES

# Expected types for metadata values.
_METADATA_TYPES: dict[str, type | tuple[type, ...]] = {
    "priority": int,
    "ramp": bool,
    "tapped": bool,
    "override_cmc": int,
    "extra_types": list,
}

# Valid spell_type values for reducer
_VALID_SPELL_TYPES = {"creature", "enchantment", "nonpermanent", "permanent", "spell"}

# Valid trigger values for per_cast
_VALID_TRIGGERS = {"spell", "creature", "enchantment", "land", "artifact", "nonpermanent"}

# Valid tempo values
_VALID_TEMPOS = {"untapped", "tapped", "summoning_sick"}


def validate_label(card_name: str, label: dict) -> list[str]:
    """Validate a label dict against the category schema.

    Returns a list of error strings. Empty list means valid.
    """
    errors: list[str] = []

    # Top-level keys
    if not isinstance(label.get("categories"), list):
        errors.append(f"{card_name}: missing or invalid 'categories' (must be a list)")
    # metadata is optional — default to empty dict
    if "metadata" not in label:
        label["metadata"] = {}
    elif not isinstance(label["metadata"], dict):
        errors.append(f"{card_name}: 'metadata' must be a dict if provided")

    # If top-level structure is broken, can't validate further
    if errors:
        return errors

    # Validate categories
    for i, cat in enumerate(label["categories"]):
        prefix = f"{card_name}: categories[{i}]"

        if not isinstance(cat, dict):
            errors.append(f"{prefix}: must be a dict")
            continue

        category = cat.get("category")
        if category not in VALID_CATEGORIES:
            errors.append(f"{prefix}: unknown category {category!r}")
            continue

        if category == "ramp":
            _validate_ramp(cat, prefix, errors)
        elif category == "draw":
            _validate_draw(cat, prefix, errors)
        elif category == "discard":
            if "amount" not in cat:
                errors.append(f"{prefix}: discard missing 'amount'")
            elif not isinstance(cat["amount"], int):
                errors.append(f"{prefix}: discard 'amount' must be int")

    # Validate metadata
    for key, value in label["metadata"].items():
        if key not in METADATA_FIELDS:
            errors.append(f"{card_name}: unknown metadata key {key!r}")
            continue

        expected = _METADATA_TYPES.get(key)
        if expected and not isinstance(value, expected):
            errors.append(
                f"{card_name}: metadata {key!r} must be {expected.__name__}, "
                f"got {type(value).__name__}"
            )

    return errors


def _validate_ramp(cat: dict, prefix: str, errors: list[str]) -> None:
    """Validate a ramp category dict."""
    has_variant = any(k in cat for k in ("producer", "land_to_battlefield", "reducer"))
    if not has_variant:
        errors.append(f"{prefix}: ramp must have 'producer', 'land_to_battlefield', or 'reducer'")
        return

    if "producer" in cat:
        prod = cat["producer"]
        if not isinstance(prod, dict):
            errors.append(f"{prefix}: producer must be a dict")
        elif "mana_amount" not in prod:
            errors.append(f"{prefix}: producer missing 'mana_amount'")
        elif not isinstance(prod["mana_amount"], int):
            errors.append(f"{prefix}: producer 'mana_amount' must be int")
        if isinstance(prod, dict) and "tempo" in prod:
            if prod["tempo"] not in _VALID_TEMPOS:
                errors.append(f"{prefix}: producer tempo {prod['tempo']!r} invalid")

    elif "land_to_battlefield" in cat:
        ltb = cat["land_to_battlefield"]
        if not isinstance(ltb, dict):
            errors.append(f"{prefix}: land_to_battlefield must be a dict")
        elif "count" not in ltb:
            errors.append(f"{prefix}: land_to_battlefield missing 'count'")

    elif "reducer" in cat:
        red = cat["reducer"]
        if not isinstance(red, dict):
            errors.append(f"{prefix}: reducer must be a dict")
        else:
            if "spell_type" not in red:
                errors.append(f"{prefix}: reducer missing 'spell_type'")
            elif red["spell_type"] not in _VALID_SPELL_TYPES:
                errors.append(f"{prefix}: reducer spell_type {red['spell_type']!r} invalid")
            if "amount" not in red:
                errors.append(f"{prefix}: reducer missing 'amount'")


def _validate_draw(cat: dict, prefix: str, errors: list[str]) -> None:
    """Validate a draw category dict."""
    immediate = cat.get("immediate", True)
    if immediate:
        if "amount" not in cat:
            errors.append(f"{prefix}: immediate draw missing 'amount'")
        elif not isinstance(cat["amount"], int):
            errors.append(f"{prefix}: draw 'amount' must be int")
    else:
        has_variant = "per_turn" in cat or "per_cast" in cat
        if not has_variant:
            errors.append(f"{prefix}: repeatable draw must have 'per_turn' or 'per_cast'")
            return

        if "per_turn" in cat:
            pt = cat["per_turn"]
            if not isinstance(pt, dict):
                errors.append(f"{prefix}: per_turn must be a dict")
            elif "amount" not in pt:
                errors.append(f"{prefix}: per_turn missing 'amount'")

        if "per_cast" in cat:
            pc = cat["per_cast"]
            if not isinstance(pc, dict):
                errors.append(f"{prefix}: per_cast must be a dict")
            else:
                if "amount" not in pc:
                    errors.append(f"{prefix}: per_cast missing 'amount'")
                if "trigger" not in pc:
                    errors.append(f"{prefix}: per_cast missing 'trigger'")
                elif pc["trigger"] not in _VALID_TRIGGERS:
                    errors.append(f"{prefix}: per_cast trigger {pc['trigger']!r} invalid")
