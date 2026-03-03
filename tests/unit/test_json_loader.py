"""Tests for the JSON card effects loader."""

from __future__ import annotations

import dataclasses
import json
import tempfile
from pathlib import Path

import pytest

from auto_goldfish.effects import builtin
from auto_goldfish.effects.json_loader import (
    METADATA_FIELDS,
    TYPE_MAP,
    VALID_SLOTS,
    _hydrate_effect,
    _merge_metadata,
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
    assert json_data["version"] == 1


def test_all_type_strings_in_type_map(json_data):
    """Every effect 'type' string in the JSON must exist in TYPE_MAP."""
    for group in json_data["groups"]:
        defaults = group.get("defaults", {})
        for effect in defaults.get("effects", []):
            assert effect["type"] in TYPE_MAP, (
                f"Unknown type {effect['type']!r} in defaults of group {group['group']!r}"
            )
        for card_name, card_data in group["cards"].items():
            for effect in card_data.get("effects", []):
                assert effect["type"] in TYPE_MAP, (
                    f"Unknown type {effect['type']!r} in card {card_name!r}"
                )


def test_all_slots_valid(json_data):
    """Every effect 'slot' string must be a valid slot."""
    for group in json_data["groups"]:
        defaults = group.get("defaults", {})
        for effect in defaults.get("effects", []):
            assert effect["slot"] in VALID_SLOTS, (
                f"Invalid slot {effect['slot']!r} in defaults of group {group['group']!r}"
            )
        for card_name, card_data in group["cards"].items():
            for effect in card_data.get("effects", []):
                assert effect["slot"] in VALID_SLOTS, (
                    f"Invalid slot {effect['slot']!r} in card {card_name!r}"
                )


def test_all_params_match_dataclass_fields(json_data):
    """All params keys in the JSON must be valid constructor args for their effect class."""
    for group in json_data["groups"]:
        all_effects = []
        defaults = group.get("defaults", {})
        for effect in defaults.get("effects", []):
            all_effects.append((f"defaults of {group['group']}", effect))
        for card_name, card_data in group["cards"].items():
            for effect in card_data.get("effects", []):
                all_effects.append((card_name, effect))

        for source, effect in all_effects:
            cls = TYPE_MAP[effect["type"]]
            params = effect.get("params", {})
            if dataclasses.is_dataclass(cls):
                valid_fields = {f.name for f in dataclasses.fields(cls)}
                for key in params:
                    assert key in valid_fields, (
                        f"Param {key!r} not a field of {cls.__name__} (card: {source})"
                    )


def test_no_duplicate_card_names(json_data):
    """Card names must be unique across all groups."""
    seen = set()
    for group in json_data["groups"]:
        for name in group["cards"]:
            assert name not in seen, f"Duplicate card name: {name!r}"
            seen.add(name)


def test_type_map_covers_all_builtin_classes():
    """TYPE_MAP should have an entry for every effect dataclass in builtin.py."""
    builtin_classes = {
        obj
        for name in dir(builtin)
        if not name.startswith("_")
        for obj in [getattr(builtin, name)]
        if isinstance(obj, type) and dataclasses.is_dataclass(obj)
    }
    mapped_classes = set(TYPE_MAP.values())
    missing = builtin_classes - mapped_classes
    assert not missing, f"Builtin classes not in TYPE_MAP: {missing}"


def test_card_count(registry):
    """Registry should contain 118 cards."""
    assert len(registry) == 118


def test_metadata_fields_match_card_effects():
    """METADATA_FIELDS should match the non-slot fields of CardEffects."""
    slot_fields = {"on_play", "per_turn", "cast_trigger", "mana_function"}
    card_effects_fields = {f.name for f in dataclasses.fields(CardEffects)}
    expected_metadata = card_effects_fields - slot_fields
    assert METADATA_FIELDS == expected_metadata


# ---------------------------------------------------------------------------
# Hydration
# ---------------------------------------------------------------------------

def test_hydrate_produce_mana():
    effect = _hydrate_effect({"type": "produce_mana", "slot": "on_play", "params": {"amount": 2}})
    assert isinstance(effect, builtin.ProduceMana)
    assert effect.amount == 2


def test_hydrate_no_params():
    """Effects with no params (CryptolithRitesMana) should hydrate correctly."""
    effect = _hydrate_effect({"type": "cryptolith_rites_mana", "slot": "mana_function"})
    assert isinstance(effect, builtin.CryptolithRitesMana)


def test_hydrate_tutor_with_targets():
    targets = ["Serra's Sanctum"]
    effect = _hydrate_effect({
        "type": "tutor_to_hand",
        "slot": "on_play",
        "params": {"targets": targets},
    })
    assert isinstance(effect, builtin.TutorToHand)
    assert effect.targets == targets


def test_hydrate_unknown_type_raises():
    with pytest.raises(ValueError, match="Unknown effect type"):
        _hydrate_effect({"type": "nonexistent_effect", "slot": "on_play"})


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
    assert effects.cast_trigger[0].creature == 1
    assert len(effects.on_play) == 1
    assert isinstance(effects.on_play[0], builtin.ProduceMana)
    assert effects.on_play[0].amount == 2


def test_tolaria_west(registry):
    effects = registry.get("Tolaria West")
    assert effects is not None
    assert effects.ramp is True
    assert effects.priority == 3
    assert effects.is_land_tutor is True
    assert effects.extra_types == ["sorcery"]
    assert effects.override_cmc == 3
    assert effects.tapped is True
    assert len(effects.on_play) == 1
    assert isinstance(effects.on_play[0], builtin.TutorToHand)
    assert effects.on_play[0].targets == ["Serra's Sanctum"]


def test_archmage_of_runes_consolidated(registry):
    """Archmage of Runes should have both cast_trigger and on_play effects."""
    effects = registry.get("Archmage of Runes")
    assert effects is not None
    assert len(effects.cast_trigger) == 1
    assert isinstance(effects.cast_trigger[0], builtin.PerCastDraw)
    assert effects.cast_trigger[0].nonpermanent == 1
    assert len(effects.on_play) == 1
    assert isinstance(effects.on_play[0], builtin.ReduceCost)
    assert effects.on_play[0].nonpermanent == 1


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
    """Cards in 'Mana Producers (1 mana)' should inherit ramp=True from defaults."""
    effects = registry.get("Arcane Signet")
    assert effects is not None
    assert effects.ramp is True
    assert len(effects.on_play) == 1
    assert isinstance(effects.on_play[0], builtin.ProduceMana)
    assert effects.on_play[0].amount == 1


def test_card_effects_override_default_effects(registry):
    """Archmage of Runes overrides group default effects with its own list."""
    # Archmage Emeritus uses group defaults (cast_trigger only)
    emeritus = registry.get("Archmage Emeritus")
    assert emeritus is not None
    assert len(emeritus.on_play) == 0
    assert len(emeritus.cast_trigger) == 1

    # Archmage of Runes overrides with both cast_trigger and on_play
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
        "version": 1,
        "groups": [
            {
                "group": "A",
                "defaults": {},
                "cards": {"Sol Ring": {"effects": []}},
            },
            {
                "group": "B",
                "defaults": {},
                "cards": {"Sol Ring": {"effects": []}},
            },
        ],
    }
    with pytest.raises(ValueError, match="Duplicate card name"):
        load_registry_from_json(_write_json(tmp_path, data))


def test_invalid_slot_raises(tmp_path):
    data = {
        "version": 1,
        "groups": [
            {
                "group": "A",
                "defaults": {},
                "cards": {
                    "Bad Card": {
                        "effects": [{"type": "produce_mana", "slot": "bad_slot", "params": {"amount": 1}}]
                    }
                },
            }
        ],
    }
    with pytest.raises(ValueError, match="Invalid slot"):
        load_registry_from_json(_write_json(tmp_path, data))


def test_unknown_type_in_json_raises(tmp_path):
    data = {
        "version": 1,
        "groups": [
            {
                "group": "A",
                "defaults": {},
                "cards": {
                    "Bad Card": {
                        "effects": [{"type": "fake_type", "slot": "on_play"}]
                    }
                },
            }
        ],
    }
    with pytest.raises(ValueError, match="Unknown effect type"):
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
            "effects": [{"type": "produce_mana", "slot": "on_play", "params": {"amount": 5}}],
            "ramp": True,
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
            "effects": [{"type": "draw_cards", "slot": "on_play", "params": {"amount": 3}}],
        }
    }
    new_reg = build_overridden_registry(registry, overrides)
    custom = new_reg.get("My Custom Card")
    assert custom is not None
    assert len(custom.on_play) == 1
    assert isinstance(custom.on_play[0], builtin.DrawCards)
    assert custom.on_play[0].amount == 3


def test_build_overridden_registry_invalid_slot_raises(registry):
    overrides = {
        "Bad Card": {
            "effects": [{"type": "produce_mana", "slot": "bad_slot", "params": {"amount": 1}}],
        }
    }
    with pytest.raises(ValueError, match="Invalid slot"):
        build_overridden_registry(registry, overrides)


def test_build_overridden_registry_empty_overrides(registry):
    new_reg = build_overridden_registry(registry, {})
    assert len(new_reg) == len(registry)


def test_build_overridden_registry_preserves_metadata(registry):
    overrides = {
        "Sol Ring": {
            "effects": [{"type": "produce_mana", "slot": "on_play", "params": {"amount": 3}}],
            "ramp": True,
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

def test_get_effect_schema_contains_all_types():
    schema = get_effect_schema()
    for type_str in TYPE_MAP:
        assert type_str in schema, f"Missing {type_str} from schema"


def test_get_effect_schema_structure():
    schema = get_effect_schema()
    produce = schema["produce_mana"]
    assert produce["label"] == "ProduceMana"
    assert produce["slot"] == "on_play"
    assert "amount" in produce["params"]
    assert produce["params"]["amount"]["type"] == "int"
    assert produce["params"]["amount"]["default"] == 1


def test_get_effect_schema_slots_are_valid():
    schema = get_effect_schema()
    for type_str, info in schema.items():
        assert info["slot"] in VALID_SLOTS, f"{type_str} has invalid slot {info['slot']}"


def test_get_effect_schema_per_turn_draw():
    schema = get_effect_schema()
    ptd = schema["per_turn_draw"]
    assert ptd["slot"] == "per_turn"
    assert ptd["label"] == "PerTurnDraw"


def test_get_effect_schema_mana_function():
    schema = get_effect_schema()
    crm = schema["cryptolith_rites_mana"]
    assert crm["slot"] == "mana_function"
