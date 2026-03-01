"""Export labeled cards to the card_effects.json registry format."""

from __future__ import annotations

import json
from pathlib import Path

from .labeler import load_labeled, save_labeled

_DEFAULT_REGISTRY = Path(__file__).resolve().parent.parent / "effects" / "card_effects.json"
_DEFAULT_OUTPUT = Path(__file__).parent / "data" / "card_effects_expanded.json"


def _effect_signature(label: dict) -> str:
    """Create a hashable signature from a label's effects + metadata."""
    effects = label.get("effects", [])
    metadata = label.get("metadata", {})
    # Normalize to sorted JSON for stable comparison
    return json.dumps({"effects": effects, "metadata": metadata}, sort_keys=True)


def group_by_effects(labeled: dict[str, dict]) -> list[dict]:
    """Group cards with identical effect signatures into registry groups.

    Returns a list of group dicts in card_effects.json format.
    """
    # Bucket cards by their effect signature
    buckets: dict[str, list[str]] = {}
    sig_to_label: dict[str, dict] = {}

    for card_name, label in labeled.items():
        sig = _effect_signature(label)
        buckets.setdefault(sig, []).append(card_name)
        sig_to_label[sig] = label

    groups = []
    for sig, card_names in buckets.items():
        label = sig_to_label[sig]
        effects = label.get("effects", [])
        metadata = label.get("metadata", {})

        # Build group name
        if not effects:
            group_name = "Unlabeled / No Effect"
        elif len(card_names) == 1:
            group_name = f"Auto-labeled: {card_names[0]}"
        else:
            # Use the first effect type as the group name hint
            first_type = effects[0]["type"]
            group_name = f"Auto-labeled: {first_type} ({len(card_names)} cards)"

        group: dict = {
            "group": group_name,
            "defaults": {},
            "cards": {},
        }

        # Put shared effects + metadata in defaults
        if effects:
            group["defaults"]["effects"] = effects
        for key, value in metadata.items():
            group["defaults"][key] = value

        # All cards inherit group defaults (empty overrides)
        for name in sorted(card_names):
            group["cards"][name] = {}

        groups.append(group)

    return groups


def export_to_registry(
    labeled: dict[str, dict],
    output: Path | None = None,
    existing_path: Path | None = None,
) -> Path:
    """Export labeled cards to a registry JSON file.

    Args:
        labeled: Dict mapping card name to label dict.
        output: Output path (default: data/card_effects_expanded.json).
        existing_path: Path to existing card_effects.json to merge with.
            Cards already in the existing registry are not overwritten.

    Returns:
        Path to the written file.
    """
    if output is None:
        output = _DEFAULT_OUTPUT

    existing_groups: list[dict] = []
    existing_names: set[str] = set()

    if existing_path is not None:
        with open(existing_path, encoding="utf-8") as f:
            existing_data = json.load(f)
        existing_groups = existing_data.get("groups", [])
        for group in existing_groups:
            existing_names.update(group.get("cards", {}).keys())

    # Filter out cards already in the existing registry
    new_labeled = {
        name: label
        for name, label in labeled.items()
        if name not in existing_names
    }

    # Group new cards
    new_groups = group_by_effects(new_labeled) if new_labeled else []

    # Merge: existing groups first, then new auto-labeled groups
    merged = {
        "version": 1,
        "groups": existing_groups + new_groups,
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2)

    return output
