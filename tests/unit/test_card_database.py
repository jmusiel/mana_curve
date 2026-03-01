"""Tests for the card effects database."""

from auto_goldfish.effects.card_database import DEFAULT_REGISTRY, build_default_registry
from auto_goldfish.effects.types import CastTriggerEffect, ManaFunctionEffect, OnPlayEffect, PerTurnEffect


def test_registry_is_populated():
    assert len(DEFAULT_REGISTRY) > 50


def test_all_names_registered():
    """All card names from the old cards.py should be in the registry."""
    expected_names = [
        # ManaProducer
        "Sol Ring", "Arcane Signet", "Fellwar Stone", "Sakura-Tribe Elder",
        "Cultivate", "Farseek",
        # ScalingManaProducer
        "As Foretold", "Smothering Tithe", "Gyre Sage",
        # CryptolithRite
        "Gemhide Sliver", "Cryptolith Rite",
        # Sanctum
        "Serra's Sanctum", "Sanctum Weaver",
        # CostReducer
        "Thunderclap Drake", "Hamza, Guardian of Arashin", "Jukai Naturalist",
        # Tutor
        "Green Sun's Zenith", "Finale of Devastation",
        # LandTutor
        "Tolaria West", "Urza's Cave",
        # Draw
        "Rishkar's Expertise", "Flame of Anor", "Read the Bones",
        # DrawDiscard
        "Windfall", "Fact or Fiction", "Brainstorm", "Faithless Looting",
        # PerTurnDraw
        "Phyrexian Arena", "Esper Sentinel", "Mystic Remora",
        # PerCastDraw
        "Archmage Emeritus", "Beast Whisperer", "The Great Henge",
        "Sythis, Harvest's Hand", "Argothian Enchantress",
        # Special
        "Lórien Revealed", "Cabal Coffers",
    ]
    for name in expected_names:
        assert DEFAULT_REGISTRY.has(name), f"{name} not in registry"


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
    assert len(effects.cast_trigger) == 1  # PerCastDraw(creature=1)


def test_as_foretold_per_turn():
    effects = DEFAULT_REGISTRY.get("As Foretold")
    assert effects is not None
    assert len(effects.per_turn) == 1
    assert isinstance(effects.per_turn[0], PerTurnEffect)


def test_cryptolith_rite_mana_function():
    effects = DEFAULT_REGISTRY.get("Cryptolith Rite")
    assert effects is not None
    assert len(effects.mana_function) == 1
    assert isinstance(effects.mana_function[0], ManaFunctionEffect)


def test_build_fresh_registry():
    reg = build_default_registry()
    assert len(reg) == len(DEFAULT_REGISTRY)
