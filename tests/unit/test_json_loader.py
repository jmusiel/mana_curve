"""Tests for the JSON card effects loader (v2 category format)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from auto_goldfish.effects import builtin
from auto_goldfish.effects.json_loader import (
    METADATA_FIELDS,
    VALID_CATEGORIES,
    _merge_metadata,
    _translate_category,
    build_overridden_registry,
    get_effect_schema,
    load_registry_from_json,
)
from auto_goldfish.effects.registry import CardEffects, EffectRegistry

_JSON_PATH = Path(__file__).resolve().parents[2] / "src" / "auto_goldfish" / "effects" / "card_effects.json"


@pytest.fixture
def json_data():
    with open(_JSON_PATH, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def registry():
    return load_registry_from_json(_JSON_PATH)


# ---------------------------------------------------------------------------
# Validation: JSON structure
# ---------------------------------------------------------------------------

def test_json_parses(json_data):
    assert "version" in json_data
    assert "groups" in json_data
    assert json_data["version"] == 2


def test_all_categories_valid(json_data):
    """Every category string in the JSON must be a valid category."""
    for group in json_data["groups"]:
        defaults = group.get("defaults", {})
        for cat in defaults.get("categories", []):
            assert cat["category"] in VALID_CATEGORIES, (
                f"Unknown category {cat['category']!r} in defaults of group {group['group']!r}"
            )
        for card_name, card_data in group["cards"].items():
            for cat in card_data.get("categories", []):
                assert cat["category"] in VALID_CATEGORIES, (
                    f"Unknown category {cat['category']!r} in card {card_name!r}"
                )


def test_no_duplicate_card_names(json_data):
    """Card names must be unique across all groups."""
    seen = set()
    for group in json_data["groups"]:
        for name in group["cards"]:
            assert name not in seen, f"Duplicate card name: {name!r}"
            seen.add(name)


def test_metadata_fields_match_card_effects():
    """METADATA_FIELDS should match the non-slot fields of CardEffects."""
    import dataclasses
    slot_fields = {"on_play", "per_turn", "cast_trigger", "mana_function"}
    card_effects_fields = {f.name for f in dataclasses.fields(CardEffects)}
    expected_metadata = card_effects_fields - slot_fields
    assert METADATA_FIELDS == expected_metadata


# ---------------------------------------------------------------------------
# _translate_category tests
# ---------------------------------------------------------------------------

class TestTranslateCategory:
    def test_land_untapped(self):
        effects, meta = _translate_category({"category": "land"})
        assert effects == []
        assert meta == {}

    def test_land_tapped(self):
        effects, meta = _translate_category({"category": "land", "tapped": True})
        assert effects == []
        assert meta == {"tapped": True}

    def test_ramp_repeatable_producer(self):
        effects, meta = _translate_category({
            "category": "ramp", "immediate": False,
            "producer": {"mana_amount": 2},
        })
        assert len(effects) == 1
        slot, eff = effects[0]
        assert slot == "on_play"
        assert isinstance(eff, builtin.ProduceMana)
        assert eff.amount == 2
        assert meta["ramp"] is True

    def test_ramp_immediate_producer(self):
        effects, meta = _translate_category({
            "category": "ramp", "immediate": True,
            "producer": {"mana_amount": 3},
        })
        assert len(effects) == 1
        slot, eff = effects[0]
        assert slot == "on_play"
        assert isinstance(eff, builtin.ImmediateMana)
        assert eff.amount == 3
        assert meta["ramp"] is True

    def test_ramp_land_to_battlefield(self):
        effects, meta = _translate_category({
            "category": "ramp", "immediate": True,
            "land_to_battlefield": {"count": 1, "tempo": "tapped"},
        })
        assert len(effects) == 1
        slot, eff = effects[0]
        assert slot == "on_play"
        assert isinstance(eff, builtin.LandToBattlefield)
        assert eff.count == 1
        assert eff.tapped is True

    def test_ramp_land_to_battlefield_untapped(self):
        effects, meta = _translate_category({
            "category": "ramp", "immediate": True,
            "land_to_battlefield": {"count": 2, "tempo": "untapped"},
        })
        slot, eff = effects[0]
        assert isinstance(eff, builtin.LandToBattlefield)
        assert eff.tapped is False

    def test_ramp_reducer(self):
        effects, meta = _translate_category({
            "category": "ramp", "immediate": False,
            "reducer": {"spell_type": "creature", "amount": 1},
        })
        slot, eff = effects[0]
        assert slot == "on_play"
        assert isinstance(eff, builtin.ReduceCost)
        assert eff.spell_type == "creature"
        assert eff.amount == 1

    def test_draw_immediate(self):
        effects, meta = _translate_category({
            "category": "draw", "immediate": True, "amount": 3,
        })
        slot, eff = effects[0]
        assert slot == "on_play"
        assert isinstance(eff, builtin.DrawCards)
        assert eff.amount == 3

    def test_draw_per_turn(self):
        effects, meta = _translate_category({
            "category": "draw", "immediate": False,
            "per_turn": {"amount": 1},
        })
        slot, eff = effects[0]
        assert slot == "per_turn"
        assert isinstance(eff, builtin.PerTurnDraw)
        assert eff.amount == 1

    def test_draw_per_cast(self):
        effects, meta = _translate_category({
            "category": "draw", "immediate": False,
            "per_cast": {"amount": 1, "trigger": "creature"},
        })
        slot, eff = effects[0]
        assert slot == "cast_trigger"
        assert isinstance(eff, builtin.PerCastDraw)
        assert eff.amount == 1
        assert eff.trigger == "creature"

    def test_discard(self):
        effects, meta = _translate_category({
            "category": "discard", "amount": 2,
        })
        slot, eff = effects[0]
        assert slot == "on_play"
        assert isinstance(eff, builtin.DiscardCards)
        assert eff.amount == 2

    def test_unknown_category_raises(self):
        with pytest.raises(ValueError, match="Unknown category"):
            _translate_category({"category": "nonexistent"})

    def test_tapped_tempo_sets_metadata(self):
        effects, meta = _translate_category({
            "category": "ramp", "immediate": False,
            "producer": {"mana_amount": 1, "tempo": "tapped"},
        })
        assert meta.get("tapped") is True

    def test_summoning_sick_sets_tapped(self):
        effects, meta = _translate_category({
            "category": "ramp", "immediate": False,
            "producer": {"mana_amount": 1, "tempo": "summoning_sick"},
        })
        assert meta.get("tapped") is True


# ---------------------------------------------------------------------------
# Round-trip: loaded registry matches expected
# ---------------------------------------------------------------------------

def test_sol_ring(registry):
    effects = registry.get("Sol Ring")
    assert effects is not None
    assert effects.ramp is True
    assert len(effects.on_play) == 1
    assert isinstance(effects.on_play[0], builtin.ProduceMana)
    assert effects.on_play[0].amount == 2


def test_great_henge(registry):
    effects = registry.get("The Great Henge")
    assert effects is not None
    assert effects.priority == 1
    assert len(effects.cast_trigger) == 1
    assert isinstance(effects.cast_trigger[0], builtin.PerCastDraw)
    assert effects.cast_trigger[0].trigger == "creature"
    assert effects.cast_trigger[0].amount == 1
    assert len(effects.on_play) == 1
    assert isinstance(effects.on_play[0], builtin.ProduceMana)
    assert effects.on_play[0].amount == 2


def test_archmage_of_runes_consolidated(registry):
    """Archmage of Runes should have both cast_trigger and on_play effects."""
    effects = registry.get("Archmage of Runes")
    assert effects is not None
    assert len(effects.cast_trigger) == 1
    assert isinstance(effects.cast_trigger[0], builtin.PerCastDraw)
    assert effects.cast_trigger[0].trigger == "nonpermanent"
    assert len(effects.on_play) == 1
    assert isinstance(effects.on_play[0], builtin.ReduceCost)
    assert effects.on_play[0].spell_type == "nonpermanent"


def test_tolaria_west(registry):
    effects = registry.get("Tolaria West")
    assert effects is not None
    assert effects.tapped is True
    # No effects — effectless land
    assert effects.on_play == []


def test_cabal_coffers_empty_effects(registry):
    effects = registry.get("Cabal Coffers")
    assert effects is not None
    assert effects.extra_types == ["artifact"]
    assert effects.on_play == []
    assert effects.per_turn == []
    assert effects.cast_trigger == []
    assert effects.mana_function == []


def test_unicode_card_names(registry):
    """Cards with Unicode characters should load correctly."""
    assert registry.has("Lórien Revealed")
    assert registry.has("Séance Board")
    assert registry.has("Bolas's Citadel")


def test_faithless_looting_draw_and_discard(registry):
    effects = registry.get("Faithless Looting")
    assert effects is not None
    assert len(effects.on_play) == 2
    assert isinstance(effects.on_play[0], builtin.DrawCards)
    assert effects.on_play[0].amount == 2
    assert isinstance(effects.on_play[1], builtin.DiscardCards)
    assert effects.on_play[1].amount == 2


def test_deadly_dispute_draw_and_treasure(registry):
    effects = registry.get("Deadly Dispute")
    assert effects is not None
    assert len(effects.on_play) == 2
    assert isinstance(effects.on_play[0], builtin.DrawCards)
    assert effects.on_play[0].amount == 2
    assert isinstance(effects.on_play[1], builtin.ImmediateMana)
    assert effects.on_play[1].amount == 1


def test_scaling_mana_approximated_as_producer(registry):
    """Former ScalingMana cards are now approximated as repeatable producers."""
    effects = registry.get("As Foretold")
    assert effects is not None
    assert effects.ramp is True
    assert effects.priority == 2
    assert len(effects.on_play) == 1
    assert isinstance(effects.on_play[0], builtin.ProduceMana)


def test_card_count(registry):
    """Registry should contain hand-curated + auto-labeled cards."""
    # 109 hand-curated + ~4639 auto-labeled with effects
    assert len(registry) > 4000


# ---------------------------------------------------------------------------
# Defaults & merge
# ---------------------------------------------------------------------------

def test_merge_metadata_defaults_apply():
    defaults = {"ramp": True, "priority": 2}
    card_data = {}
    merged = _merge_metadata(defaults, card_data)
    assert merged == {"ramp": True, "priority": 2}


def test_merge_metadata_card_overrides():
    defaults = {"ramp": True, "priority": 2}
    card_data = {"priority": 3, "tapped": True}
    merged = _merge_metadata(defaults, card_data)
    assert merged == {"ramp": True, "priority": 3, "tapped": True}


def test_group_defaults_apply(registry):
    """Cards in 'Repeatable Mana Producers (1 mana)' should inherit ramp from categories."""
    effects = registry.get("Arcane Signet")
    assert effects is not None
    assert effects.ramp is True
    assert len(effects.on_play) == 1
    assert isinstance(effects.on_play[0], builtin.ProduceMana)
    assert effects.on_play[0].amount == 1


def test_card_categories_override_default_categories(registry):
    """Archmage of Runes overrides group default categories with its own list."""
    emeritus = registry.get("Archmage Emeritus")
    assert emeritus is not None
    assert len(emeritus.on_play) == 0
    assert len(emeritus.cast_trigger) == 1

    runes = registry.get("Archmage of Runes")
    assert runes is not None
    assert len(runes.on_play) == 1
    assert len(runes.cast_trigger) == 1


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

def _write_json(tmp_path: Path, data: dict) -> Path:
    p = tmp_path / "test.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def test_duplicate_card_name_raises(tmp_path):
    data = {
        "version": 2,
        "groups": [
            {
                "group": "A",
                "defaults": {},
                "cards": {"Sol Ring": {"categories": []}},
            },
            {
                "group": "B",
                "defaults": {},
                "cards": {"Sol Ring": {"categories": []}},
            },
        ],
    }
    with pytest.raises(ValueError, match="Duplicate card name"):
        load_registry_from_json(_write_json(tmp_path, data))


def test_unknown_category_in_json_raises(tmp_path):
    data = {
        "version": 2,
        "groups": [
            {
                "group": "A",
                "defaults": {},
                "cards": {
                    "Bad Card": {
                        "categories": [{"category": "fake_cat"}]
                    }
                },
            }
        ],
    }
    with pytest.raises(ValueError, match="Unknown category"):
        load_registry_from_json(_write_json(tmp_path, data))


# ---------------------------------------------------------------------------
# EffectRegistry.copy()
# ---------------------------------------------------------------------------

def test_registry_copy_returns_new_instance(registry):
    copy = registry.copy()
    assert isinstance(copy, EffectRegistry)
    assert copy is not registry
    assert len(copy) == len(registry)


def test_registry_copy_is_independent(registry):
    copy = registry.copy()
    copy.register("Fake Card", CardEffects(ramp=True))
    assert copy.has("Fake Card")
    assert not registry.has("Fake Card")


# ---------------------------------------------------------------------------
# build_overridden_registry()
# ---------------------------------------------------------------------------

def test_build_overridden_registry_replaces_effect(registry):
    overrides = {
        "Sol Ring": {
            "categories": [{"category": "ramp", "immediate": False, "producer": {"mana_amount": 5}}],
        }
    }
    new_reg = build_overridden_registry(registry, overrides)
    sol = new_reg.get("Sol Ring")
    assert sol is not None
    assert sol.on_play[0].amount == 5
    assert sol.ramp is True
    # Original unchanged
    assert registry.get("Sol Ring").on_play[0].amount == 2


def test_build_overridden_registry_adds_new_card(registry):
    overrides = {
        "My Custom Card": {
            "categories": [{"category": "draw", "immediate": True, "amount": 3}],
        }
    }
    new_reg = build_overridden_registry(registry, overrides)
    custom = new_reg.get("My Custom Card")
    assert custom is not None
    assert len(custom.on_play) == 1
    assert isinstance(custom.on_play[0], builtin.DrawCards)
    assert custom.on_play[0].amount == 3


def test_build_overridden_registry_empty_overrides(registry):
    new_reg = build_overridden_registry(registry, {})
    assert len(new_reg) == len(registry)


def test_build_overridden_registry_preserves_metadata(registry):
    overrides = {
        "Sol Ring": {
            "categories": [{"category": "ramp", "immediate": False, "producer": {"mana_amount": 3}}],
            "tapped": True,
        }
    }
    new_reg = build_overridden_registry(registry, overrides)
    sol = new_reg.get("Sol Ring")
    assert sol.ramp is True
    assert sol.tapped is True


# ---------------------------------------------------------------------------
# get_effect_schema()
# ---------------------------------------------------------------------------

def test_get_effect_schema_contains_all_categories():
    schema = get_effect_schema()
    assert "categories" in schema
    for cat in VALID_CATEGORIES:
        assert cat in schema["categories"], f"Missing {cat} from schema"


def test_get_effect_schema_ramp_has_variants():
    schema = get_effect_schema()
    ramp = schema["categories"]["ramp"]
    assert "variants" in ramp
    assert "producer" in ramp["variants"]
    assert "land_to_battlefield" in ramp["variants"]
    assert "reducer" in ramp["variants"]


def test_get_effect_schema_draw_has_variants():
    schema = get_effect_schema()
    draw = schema["categories"]["draw"]
    assert "variants" in draw
    assert "per_turn" in draw["variants"]
    assert "per_cast" in draw["variants"]


def test_get_effect_schema_metadata():
    schema = get_effect_schema()
    assert "metadata" in schema
    assert "priority" in schema["metadata"]
    assert "override_cmc" in schema["metadata"]
