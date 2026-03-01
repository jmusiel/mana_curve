"""Validate LLM-generated card labels against the effect type system."""

from __future__ import annotations

from dataclasses import fields as dc_fields

from auto_goldfish.effects.json_loader import METADATA_FIELDS, TYPE_MAP, VALID_SLOTS

# Expected types for metadata values.
_METADATA_TYPES: dict[str, type | tuple[type, ...]] = {
    "priority": int,
    "ramp": bool,
    "is_land_tutor": bool,
    "tapped": bool,
    "override_cmc": int,
    "extra_types": list,
}

# Conservative subset: simpler types/slots the LLM can reliably classify.
CONSERVATIVE_VALID_TYPES = {
    "produce_mana",
    "draw_cards",
    "draw_discard",
    "reduce_cost",
    "per_turn_draw",
    "scaling_mana",
}
CONSERVATIVE_VALID_SLOTS = {"on_play", "per_turn"}
CONSERVATIVE_METADATA_FIELDS = METADATA_FIELDS - {"is_land_tutor"}


def validate_label(
    card_name: str,
    label: dict,
    conservative: bool = False,
) -> list[str]:
    """Validate a label dict against the effect schema.

    Args:
        card_name: Name of the card (for error messages).
        label: The label dict with 'effects' and 'metadata' keys.
        conservative: If True, reject types/slots/metadata outside the
            conservative subset.

    Returns a list of error strings. Empty list means valid.
    """
    errors: list[str] = []

    allowed_types = CONSERVATIVE_VALID_TYPES if conservative else set(TYPE_MAP)
    allowed_slots = CONSERVATIVE_VALID_SLOTS if conservative else VALID_SLOTS
    allowed_metadata = CONSERVATIVE_METADATA_FIELDS if conservative else METADATA_FIELDS

    # Top-level keys
    if not isinstance(label.get("effects"), list):
        errors.append(f"{card_name}: missing or invalid 'effects' (must be a list)")
    if not isinstance(label.get("metadata"), dict):
        errors.append(f"{card_name}: missing or invalid 'metadata' (must be a dict)")

    # If top-level structure is broken, can't validate further
    if errors:
        return errors

    # Validate effects
    for i, effect in enumerate(label["effects"]):
        prefix = f"{card_name}: effects[{i}]"

        etype = effect.get("type")
        if etype not in TYPE_MAP:
            errors.append(f"{prefix}: unknown type {etype!r}")
            continue
        if etype not in allowed_types:
            errors.append(f"{prefix}: disallowed type {etype!r} in conservative mode")
            continue

        slot = effect.get("slot")
        if slot not in VALID_SLOTS:
            errors.append(f"{prefix}: unknown slot {slot!r}")
        elif slot not in allowed_slots:
            errors.append(f"{prefix}: disallowed slot {slot!r} in conservative mode")

        # Validate params against dataclass fields
        cls = TYPE_MAP[etype]
        valid_params = {f.name for f in dc_fields(cls)}
        params = effect.get("params", {})
        for key in params:
            if key not in valid_params:
                errors.append(
                    f"{prefix}: unknown param {key!r} for type {etype!r} "
                    f"(valid: {sorted(valid_params)})"
                )

    # Validate metadata
    for key, value in label["metadata"].items():
        if key not in METADATA_FIELDS:
            errors.append(f"{card_name}: unknown metadata key {key!r}")
            continue
        if key not in allowed_metadata:
            errors.append(
                f"{card_name}: disallowed metadata {key!r} in conservative mode"
            )
            continue

        expected = _METADATA_TYPES.get(key)
        if expected and not isinstance(value, expected):
            errors.append(
                f"{card_name}: metadata {key!r} must be {expected.__name__}, "
                f"got {type(value).__name__}"
            )

    return errors
