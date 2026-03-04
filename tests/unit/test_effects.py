"""Tests for the effects system."""

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
from auto_goldfish.effects.registry import CardEffects, EffectRegistry
from auto_goldfish.effects.types import (
    CastTriggerEffect,
    OnPlayEffect,
    PerTurnEffect,
)
from auto_goldfish.models.card import Card
from auto_goldfish.models.game_state import GameState


class TestProtocols:
    def test_produce_mana_is_on_play(self):
        assert isinstance(ProduceMana(1), OnPlayEffect)

    def test_draw_cards_is_on_play(self):
        assert isinstance(DrawCards(1), OnPlayEffect)

    def test_immediate_mana_is_on_play(self):
        assert isinstance(ImmediateMana(1), OnPlayEffect)

    def test_land_to_battlefield_is_on_play(self):
        assert isinstance(LandToBattlefield(), OnPlayEffect)

    def test_discard_cards_is_on_play(self):
        assert isinstance(DiscardCards(1), OnPlayEffect)

    def test_reduce_cost_is_on_play(self):
        assert isinstance(ReduceCost(), OnPlayEffect)

    def test_per_turn_draw_is_per_turn(self):
        assert isinstance(PerTurnDraw(1), PerTurnEffect)

    def test_per_cast_draw_is_cast_trigger(self):
        assert isinstance(PerCastDraw(amount=1, trigger="creature"), CastTriggerEffect)


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


class TestImmediateMana:
    def test_adds_treasure(self):
        gs = GameState()
        card = Card(name="Dark Ritual", cmc=1, types=["instant"])
        ImmediateMana(3).on_play(card, gs)
        assert gs.treasure == 3

    def test_stacks(self):
        gs = GameState()
        card = Card(name="Ritual", cmc=1, types=["instant"])
        ImmediateMana(2).on_play(card, gs)
        ImmediateMana(1).on_play(card, gs)
        assert gs.treasure == 3


class TestDiscardCards:
    def test_discards_from_hand(self):
        gs = GameState()
        card = Card(name="Faithless Looting", cmc=1, types=["sorcery"])
        # Set up a hand with cards
        c1 = Card(name="A", cmc=1, types=["creature"])
        c2 = Card(name="B", cmc=2, types=["creature"])
        gs.decklist = [c1, c2]
        gs.hand = [0, 1]
        c1.zone = gs.hand
        c2.zone = gs.hand
        gs.should_log = False

        DiscardCards(1).on_play(card, gs)
        assert len(gs.hand) == 1

    def test_discard_stops_on_empty_hand(self):
        gs = GameState()
        card = Card(name="Faithless Looting", cmc=1, types=["sorcery"])
        gs.decklist = []
        gs.hand = []
        gs.should_log = False
        # Should not error
        DiscardCards(3).on_play(card, gs)
        assert len(gs.hand) == 0


class TestReduceCost:
    def test_reduces_creature_cost(self):
        gs = GameState()
        card = Card(name="Hamza", cmc=6, types=["creature"])
        ReduceCost(spell_type="creature", amount=1).on_play(card, gs)
        assert gs.creature_cost_reduction == 1

    def test_reduces_enchantment_cost(self):
        gs = GameState()
        card = Card(name="Jukai", cmc=2, types=["creature"])
        ReduceCost(spell_type="enchantment", amount=1).on_play(card, gs)
        assert gs.enchantment_cost_reduction == 1

    def test_reduces_spell_cost(self):
        gs = GameState()
        card = Card(name="Goblin", cmc=2, types=["creature"])
        ReduceCost(spell_type="spell", amount=2).on_play(card, gs)
        assert gs.spell_cost_reduction == 2


class TestPerCastDraw:
    def test_draws_on_creature_cast(self):
        gs = GameState()
        gs.should_log = False
        gs.decklist = [Card(name=f"C{i}", cmc=1, types=["creature"]) for i in range(5)]
        gs.deck = list(range(5))
        for i, c in enumerate(gs.decklist):
            c.zone = gs.deck

        trigger_card = Card(name="Trigger", cmc=3, types=["enchantment"])
        casted = Card(name="Bear", cmc=2, types=["creature"])

        PerCastDraw(amount=1, trigger="creature").cast_trigger(trigger_card, casted, gs)
        assert gs.draws == 1

    def test_no_draw_on_wrong_type(self):
        gs = GameState()
        gs.should_log = False

        trigger_card = Card(name="Trigger", cmc=3, types=["enchantment"])
        casted = Card(name="Bolt", cmc=1, types=["instant"])

        PerCastDraw(amount=1, trigger="creature").cast_trigger(trigger_card, casted, gs)
        assert gs.draws == 0

    def test_draws_on_spell_cast(self):
        gs = GameState()
        gs.should_log = False
        gs.decklist = [Card(name=f"C{i}", cmc=1, types=["creature"]) for i in range(5)]
        gs.deck = list(range(5))
        for i, c in enumerate(gs.decklist):
            c.zone = gs.deck

        trigger_card = Card(name="Trigger", cmc=3, types=["enchantment"])
        casted = Card(name="Bear", cmc=2, types=["creature"])

        PerCastDraw(amount=1, trigger="spell").cast_trigger(trigger_card, casted, gs)
        assert gs.draws == 1


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

    def test_immediate_mana_describe(self):
        assert ImmediateMana(3).describe() == "+3 treasure"

    def test_land_to_battlefield_describe_tapped(self):
        assert LandToBattlefield(1, tapped=True).describe() == "Fetch 1 land tapped"

    def test_land_to_battlefield_describe_untapped(self):
        assert LandToBattlefield(2, tapped=False).describe() == "Fetch 2 lands untapped"

    def test_discard_cards_describe(self):
        assert DiscardCards(2).describe() == "Discard 2"

    def test_reduce_cost_creature(self):
        desc = ReduceCost(spell_type="creature", amount=1).describe()
        assert desc == "Creature costs -1"

    def test_reduce_cost_enchantment(self):
        desc = ReduceCost(spell_type="enchantment", amount=2).describe()
        assert desc == "Enchantment costs -2"

    def test_per_turn_draw_describe(self):
        assert PerTurnDraw(1).describe() == "Draw 1 per turn"

    def test_per_cast_draw_describe(self):
        desc = PerCastDraw(amount=1, trigger="creature").describe()
        assert desc == "Draw 1 on creature cast"

    def test_per_cast_draw_describe_spell(self):
        desc = PerCastDraw(amount=1, trigger="spell").describe()
        assert desc == "Draw 1 on spell cast"


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
            cast_trigger=[PerCastDraw(amount=1, trigger="creature")],
        )
        desc = ce.describe_effects()
        assert "+2 mana" in desc
        assert "Draw 1 on creature cast" in desc
        assert "; " in desc

    def test_effects_across_multiple_lists(self):
        ce = CardEffects(
            on_play=[ProduceMana(1)],
            per_turn=[PerTurnDraw(1)],
            cast_trigger=[PerCastDraw(amount=1, trigger="creature")],
        )
        desc = ce.describe_effects()
        parts = desc.split("; ")
        assert len(parts) == 3
