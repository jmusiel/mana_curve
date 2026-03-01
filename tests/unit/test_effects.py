"""Tests for the effects system."""

from auto_goldfish.effects.builtin import (
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
from auto_goldfish.effects.registry import CardEffects, EffectRegistry
from auto_goldfish.effects.types import (
    CastTriggerEffect,
    ManaFunctionEffect,
    OnPlayEffect,
    PerTurnEffect,
)
from auto_goldfish.models.card import Card
from auto_goldfish.models.game_state import GameState


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


class TestDescribe:
    """Tests for describe() methods on effect classes."""

    def test_produce_mana_describe(self):
        assert ProduceMana(2).describe() == "+2 mana"

    def test_produce_mana_describe_one(self):
        assert ProduceMana(1).describe() == "+1 mana"

    def test_draw_cards_describe(self):
        assert DrawCards(3).describe() == "Draw 3 cards"

    def test_draw_cards_describe_one(self):
        assert DrawCards(1).describe() == "Draw 1 card"

    def test_draw_discard_describe(self):
        desc = DrawDiscard(2, 1, 0, 0).describe()
        assert "Draw 2" in desc
        assert "discard 1" in desc

    def test_draw_discard_with_treasures(self):
        desc = DrawDiscard(0, 0, 0, 2).describe()
        assert "treasure" in desc

    def test_reduce_cost_creature(self):
        desc = ReduceCost(creature=1).describe()
        assert "Creature costs -1" in desc

    def test_reduce_cost_multiple(self):
        desc = ReduceCost(creature=1, enchantment=2).describe()
        assert "Creature" in desc
        assert "Enchantment" in desc

    def test_tutor_to_hand_describe(self):
        desc = TutorToHand(["Sol Ring"]).describe()
        assert "Tutor: Sol Ring" == desc

    def test_tutor_to_hand_multiple_targets(self):
        desc = TutorToHand(["Sol Ring", "Mana Crypt"]).describe()
        assert "Sol Ring" in desc
        assert "Mana Crypt" in desc

    def test_per_turn_draw_describe(self):
        assert PerTurnDraw(1).describe() == "Draw 1 per turn"

    def test_scaling_mana_describe(self):
        assert ScalingMana(1).describe() == "+1 mana per turn (scaling)"

    def test_per_cast_draw_describe(self):
        desc = PerCastDraw(creature=1).describe()
        assert "Draw 1 on creature cast" == desc

    def test_per_cast_draw_multiple_types(self):
        desc = PerCastDraw(creature=1, enchantment=1).describe()
        assert "creature" in desc
        assert "enchantment" in desc

    def test_cryptolith_rites_describe(self):
        assert CryptolithRitesMana().describe() == "Tap creatures for mana"

    def test_enchantment_sanctum_describe(self):
        assert EnchantmentSanctumMana().describe() == "Mana from enchantments"


class TestDescribeEffects:
    """Tests for CardEffects.describe_effects() method."""

    def test_empty_card_effects(self):
        ce = CardEffects()
        assert ce.describe_effects() == ""

    def test_single_effect(self):
        ce = CardEffects(on_play=[ProduceMana(2)])
        assert ce.describe_effects() == "+2 mana"

    def test_multiple_effects(self):
        ce = CardEffects(
            on_play=[ProduceMana(2)],
            cast_trigger=[PerCastDraw(creature=1)],
        )
        desc = ce.describe_effects()
        assert "+2 mana" in desc
        assert "Draw 1 on creature cast" in desc
        assert "; " in desc

    def test_effects_across_all_lists(self):
        ce = CardEffects(
            on_play=[ProduceMana(1)],
            per_turn=[PerTurnDraw(1)],
            cast_trigger=[PerCastDraw(creature=1)],
            mana_function=[CryptolithRitesMana()],
        )
        desc = ce.describe_effects()
        parts = desc.split("; ")
        assert len(parts) == 4
