"""Tests for mana_curve.models.card."""

from mana_curve.models.card import Card
from mana_curve.models.game_state import GameState


class TestCardCreation:
    def test_basic_creature(self):
        c = Card(name="Bear", cmc=2, types=["creature"])
        assert c.creature is True
        assert c.spell is True
        assert c.permanent is True
        assert c.nonpermanent is False
        assert c.land is False

    def test_basic_land(self):
        c = Card(name="Island", cmc=0, types=["land"])
        assert c.land is True
        assert c.permanent is True
        assert c.spell is False

    def test_instant(self):
        c = Card(name="Bolt", cmc=1, types=["instant"])
        assert c.instant is True
        assert c.spell is True
        assert c.nonpermanent is True

    def test_sorcery(self):
        c = Card(name="Wrath", cmc=4, types=["sorcery"])
        assert c.sorcery is True
        assert c.nonpermanent is True

    def test_artifact(self):
        c = Card(name="Sol Ring", cmc=1, types=["artifact"])
        assert c.artifact is True
        assert c.permanent is True

    def test_enchantment(self):
        c = Card(name="Aura", cmc=2, types=["enchantment"])
        assert c.enchantment is True
        assert c.permanent is True

    def test_mdfc_land_spell(self):
        c = Card(name="Recovery", cmc=3, types=["sorcery", "land"])
        assert c.mdfc is True
        assert c.land is True
        assert c.spell is True
        assert c.land_priority == -1

    def test_types_lowercased(self):
        c = Card(name="Test", types=["Creature", "Artifact"])
        assert c.types == ["creature", "artifact"]
        assert c.creature is True
        assert c.artifact is True

    def test_cost_text_lowercased(self):
        c = Card(name="Test", cost="{2}{U}", text="Draw a card.")
        assert c.cost == "{2}{u}"
        assert c.text == "draw a card."


class TestCardOrdering:
    def test_sort_by_cmc(self):
        a = Card(name="A", cmc=1, types=["creature"])
        b = Card(name="B", cmc=3, types=["creature"])
        assert a < b

    def test_sort_by_priority(self):
        a = Card(name="A", cmc=5, types=["creature"])
        b = Card(name="B", cmc=1, types=["creature"])
        a.priority = 2
        b.priority = 0
        assert b < a

    def test_equality_by_name(self):
        a = Card(name="Sol Ring", cmc=1)
        b = Card(name="Sol Ring", cmc=1)
        assert a == b

    def test_inequality(self):
        a = Card(name="Sol Ring", cmc=1)
        b = Card(name="Arcane Signet", cmc=2)
        assert a != b


class TestCardCostReduction:
    def test_creature_cost_reduction(self):
        gs = GameState()
        gs.creature_cost_reduction = 2
        c = Card(name="Big Bear", cmc=5, types=["creature"])
        assert c.get_current_cost(gs) == 3

    def test_cost_never_below_one(self):
        gs = GameState()
        gs.spell_cost_reduction = 100
        c = Card(name="Cheap", cmc=2, types=["creature"])
        assert c.get_current_cost(gs) == 1

    def test_multiple_reductions_stack(self):
        gs = GameState()
        gs.enchantment_cost_reduction = 1
        gs.permanent_cost_reduction = 1
        c = Card(name="Enchantment", cmc=5, types=["enchantment"])
        assert c.get_current_cost(gs) == 3


class TestCardZones:
    def test_change_zone(self):
        hand = [0]
        bf = []
        c = Card(name="Test", index=0)
        c.zone = hand
        c.change_zone(bf)
        assert c.zone is bf
        assert 0 in bf
        assert 0 not in hand
