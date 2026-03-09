"""Tests for the card effects database."""

from auto_goldfish.effects.card_database import DEFAULT_REGISTRY, build_default_registry
from auto_goldfish.effects.types import CastTriggerEffect, OnPlayEffect, PerTurnEffect


def test_registry_is_populated():
    assert len(DEFAULT_REGISTRY) > 50


def test_all_names_registered():
    """Key card names should be in the registry."""
    expected_names = [
        # Repeatable Mana Producers
        "Sol Ring", "Arcane Signet", "Fellwar Stone", "Sakura-Tribe Elder",
        "Cultivate", "Farseek",
        # Scaling Mana (approximated)
        "As Foretold", "Smothering Tithe", "Gyre Sage",
        # Cost Reducers
        "Thunderclap Drake", "Hamza, Guardian of Arashin", "Jukai Naturalist",
        # Draw
        "Rishkar's Expertise", "Flame of Anor", "Read the Bones",
        # Draw + Discard
        "Windfall", "Fact or Fiction", "Brainstorm", "Faithless Looting",
        # Per-Turn Draw
        "Phyrexian Arena", "Esper Sentinel", "Mystic Remora",
        # Per-Cast Draw
        "Archmage Emeritus", "Beast Whisperer", "The Great Henge",
        "Sythis, Harvest's Hand", "Argothian Enchantress",
        # Special
        "Lórien Revealed", "Cabal Coffers",
    ]
    for name in expected_names:
        assert DEFAULT_REGISTRY.has(name), f"{name} not in registry"


def test_auto_labeled_cards_in_registry():
    """Cards auto-labeled by the LLM pipeline should be in the registry."""
    auto_labeled = [
        "Gemhide Sliver", "Cryptolith Rite", "Manaweft Sliver",
        "Sanctum Weaver",
    ]
    for name in auto_labeled:
        assert DEFAULT_REGISTRY.has(name), f"{name} should be in registry via auto-labeling"


def test_sol_ring_effects():
    effects = DEFAULT_REGISTRY.get("Sol Ring")
    assert effects is not None
    assert effects.ramp is True
    assert len(effects.on_play) == 1
    assert isinstance(effects.on_play[0], OnPlayEffect)


def test_great_henge_multi_effect():
    effects = DEFAULT_REGISTRY.get("The Great Henge")
    assert effects is not None
    assert len(effects.on_play) == 1  # ProduceMana(2)
    assert len(effects.cast_trigger) == 1  # PerCastDraw(creature)


def test_as_foretold_is_now_producer():
    """As Foretold was ScalingMana, now approximated as repeatable producer."""
    effects = DEFAULT_REGISTRY.get("As Foretold")
    assert effects is not None
    assert len(effects.on_play) == 1
    assert isinstance(effects.on_play[0], OnPlayEffect)
    assert effects.ramp is True


def test_per_turn_draw():
    effects = DEFAULT_REGISTRY.get("Phyrexian Arena")
    assert effects is not None
    assert len(effects.per_turn) == 1
    assert isinstance(effects.per_turn[0], PerTurnEffect)
    assert effects.draw is True


def test_draw_only_cards_have_draw_flag():
    """Cards with only draw effects should have draw=True and ramp=False."""
    draw_only_cards = [
        "Rishkar's Expertise", "Read the Bones", "Brainstorm",
        "Phyrexian Arena", "Archmage Emeritus", "Beast Whisperer",
    ]
    for name in draw_only_cards:
        effects = DEFAULT_REGISTRY.get(name)
        assert effects is not None, f"{name} not in registry"
        assert effects.draw is True, f"{name} should have draw=True"
        assert effects.ramp is False, f"{name} should have ramp=False"


def test_build_fresh_registry():
    reg = build_default_registry()
    assert len(reg) == len(DEFAULT_REGISTRY)
