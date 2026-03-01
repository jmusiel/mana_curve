"""Card effects database -- loads card-to-effect mappings from JSON.

Adding a new card = one entry in ``card_effects.json``, no new classes needed.
"""

from __future__ import annotations

from .json_loader import load_registry_from_json
from .registry import EffectRegistry


def build_default_registry() -> EffectRegistry:
    """Build and return the default card effects registry."""
    return load_registry_from_json()


# Singleton default registry
DEFAULT_REGISTRY = build_default_registry()
