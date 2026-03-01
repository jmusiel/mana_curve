"""Tests for the effects system."""

from mana_curve.effects.builtin import (
    CryptolithRitesMana,
    EnchantmentSanctumMana,
    PerCastDraw,
    PerTurnDraw,
    ProduceMana,
    ReduceCost,
    ScalingMana,
)
from mana_curve.effects.registry import CardEffects, EffectRegistry
from mana_curve.effects.types import (
    CastTriggerEffect,
    ManaFunctionEffect,
    OnPlayEffect,
    PerTurnEffect,
)
from mana_curve.models.card import Card
from mana_curve.models.game_state import GameState


class TestProtocols:
    def test_produce_mana_is_on_play(self):
        assert isinstance(ProduceMana(1), OnPlayEffect)

    def test_scaling_mana_is_per_turn(self):
        assert isinstance(ScalingMana(1), PerTurnEffect)

    def test_per_cast_draw_is_cast_trigger(self):
        assert isinstance(PerCastDraw(creature=1), CastTriggerEffect)

    def test_cryptolith_is_mana_function(self):
        assert isinstance(CryptolithRitesMana(), ManaFunctionEffect)


class TestProduceMana:
    def test_adds_mana(self):
        gs = GameState()
        card = Card(name="Sol Ring", cmc=1, types=["artifact"])
        ProduceMana(2).on_play(card, gs)
        assert gs.mana_production == 2

    def test_stacks(self):
        gs = GameState()
        card = Card(name="Ring", cmc=1, types=["artifact"])
        ProduceMana(2).on_play(card, gs)
        ProduceMana(1).on_play(card, gs)
        assert gs.mana_production == 3


class TestReduceCost:
    def test_reduces_creature_cost(self):
        gs = GameState()
        card = Card(name="Hamza", cmc=6, types=["creature"])
        ReduceCost(creature=1).on_play(card, gs)
        assert gs.creature_cost_reduction == 1

    def test_reduces_enchantment_cost(self):
        gs = GameState()
        card = Card(name="Jukai", cmc=2, types=["creature"])
        ReduceCost(enchantment=1).on_play(card, gs)
        assert gs.enchantment_cost_reduction == 1


class TestScalingMana:
    def test_adds_mana_each_turn(self):
        gs = GameState()
        card = Card(name="As Foretold", cmc=3, types=["enchantment"])
        sm = ScalingMana(1)
        sm.per_turn(card, gs)
        assert gs.mana_production == 1
        sm.per_turn(card, gs)
        assert gs.mana_production == 2


class TestCryptolithRitesMana:
    def test_taps_creatures_for_mana(self):
        gs = GameState()
        gs.creatures_played = 3
        gs.tapped_creatures_this_turn = 0
        cr = CryptolithRitesMana()
        mana = cr.mana_function(gs)
        assert mana == 3
        assert gs.tapped_creatures_this_turn == 3

    def test_no_double_tap(self):
        gs = GameState()
        gs.creatures_played = 3
        gs.tapped_creatures_this_turn = 3
        cr = CryptolithRitesMana()
        mana = cr.mana_function(gs)
        assert mana == 0


class TestEnchantmentSanctumMana:
    def test_mana_from_enchantments(self):
        gs = GameState()
        gs.enchantments_played = 5
        es = EnchantmentSanctumMana()
        assert es.mana_function(gs) == 5


class TestRegistry:
    def test_register_and_get(self):
        reg = EffectRegistry()
        effects = CardEffects(on_play=[ProduceMana(2)], ramp=True)
        reg.register("Sol Ring", effects)
        assert reg.get("Sol Ring") is effects
        assert reg.has("Sol Ring")
        assert "Sol Ring" in reg

    def test_register_many(self):
        reg = EffectRegistry()
        effects = CardEffects(on_play=[ProduceMana(1)], ramp=True)
        reg.register_many(["Arcane Signet", "Fellwar Stone"], effects)
        assert reg.has("Arcane Signet")
        assert reg.has("Fellwar Stone")
        assert len(reg) == 2

    def test_get_missing_returns_none(self):
        reg = EffectRegistry()
        assert reg.get("Nonexistent") is None
        assert not reg.has("Nonexistent")
