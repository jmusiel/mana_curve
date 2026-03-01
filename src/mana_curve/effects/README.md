# Effects System

The effects system maps card names to composable effect objects that the simulation engine uses during goldfish runs. Effects are defined as dataclasses in `builtin.py`, registered in `card_effects.json`, and loaded into an `EffectRegistry` at runtime.

## JSON Format

Card effects live in `card_effects.json`. The file uses a grouped structure:

```json
{
  "version": 1,
  "groups": [
    {
      "group": "Human-readable group name",
      "defaults": {
        "ramp": true,
        "priority": 2,
        "effects": [{"type": "produce_mana", "slot": "on_play", "params": {"amount": 1}}]
      },
      "cards": {
        "Sol Ring": {},
        "Arcane Signet": {},
        "Custom Card": {
          "effects": [{"type": "produce_mana", "slot": "on_play", "params": {"amount": 3}}],
          "priority": 1
        }
      }
    }
  ]
}
```

**Groups** organize cards by function. Each group has optional `defaults` that apply to all cards unless overridden per-card.

**Default effects** (`defaults.effects`) are inherited by cards with no `"effects"` key. A card that specifies its own `"effects"` replaces the defaults entirely.

**Metadata defaults** (`ramp`, `priority`, etc.) merge with per-card metadata -- per-card values win.

## Effect Types Reference

| Type string | Class | Valid slots | Params | Example |
|---|---|---|---|---|
| `produce_mana` | `ProduceMana` | `on_play` | `amount` (int) | Sol Ring: amount=2 |
| `draw_cards` | `DrawCards` | `on_play` | `amount` (int) | Rishkar's Expertise: amount=4 |
| `draw_discard` | `DrawDiscard` | `on_play` | `first_draw`, `discard`, `second_draw`, `make_treasures` (all int) | Faithless Looting: first_draw=2, discard=2 |
| `reduce_cost` | `ReduceCost` | `on_play` | `nonpermanent`, `permanent`, `spell`, `creature`, `enchantment` (all int) | Jukai Naturalist: enchantment=1 |
| `tutor_to_hand` | `TutorToHand` | `on_play` | `targets` (list of str) | Green Sun's Zenith |
| `per_turn_draw` | `PerTurnDraw` | `per_turn` | `amount` (int) | Phyrexian Arena: amount=1 |
| `scaling_mana` | `ScalingMana` | `per_turn` | `amount` (int) | As Foretold: amount=1 |
| `per_cast_draw` | `PerCastDraw` | `cast_trigger` | `nonpermanent`, `spell`, `creature`, `enchantment` (all int) | Beast Whisperer: creature=1 |
| `cryptolith_rites_mana` | `CryptolithRitesMana` | `mana_function` | *(none)* | Cryptolith Rite |
| `enchantment_sanctum_mana` | `EnchantmentSanctumMana` | `mana_function` | *(none)* | Serra's Sanctum |

## Slots

- **`on_play`** -- Fires once when the card is played. Used for ramp, draw, cost reduction, tutors.
- **`per_turn`** -- Fires at the start of each turn while in play. Used for scaling mana and repeatable draw.
- **`cast_trigger`** -- Fires whenever another spell is cast while this is in play. Used for draw-on-cast effects.
- **`mana_function`** -- Called during mana calculation each turn. Returns an int. Used for dynamic mana (creatures, enchantments).

## Card Metadata Fields

| Field | Type | Default | Description |
|---|---|---|---|
| `priority` | int | 0 | Play order priority (higher = played later within a turn) |
| `ramp` | bool | false | Whether the card counts as ramp for mulligan/metrics |
| `is_land_tutor` | bool | false | Whether the card searches for a land |
| `extra_types` | list[str] | null | Additional types for simulation (e.g. `["sorcery"]`, `["land"]`) |
| `override_cmc` | int | null | Override the card's CMC for simulation |
| `tapped` | bool | false | Whether the card enters tapped |

## How to Add a New Card

1. Find (or create) the appropriate group in `card_effects.json`
2. Add the card name as a key under `"cards"`
3. If the card matches the group's default effects, use `{}`
4. If the card needs custom effects, specify its own `"effects"` list

Example -- adding a new mana rock that produces 1 mana:

```json
"cards": {
  "My New Signet": {}
}
```

Example -- adding a card with custom effects:

```json
"cards": {
  "My Custom Card": {
    "effects": [
      {"type": "draw_cards", "slot": "on_play", "params": {"amount": 2}},
      {"type": "produce_mana", "slot": "on_play", "params": {"amount": 1}}
    ],
    "ramp": true,
    "priority": 1
  }
}
```

## How to Add a New Effect Type

1. Create a new `@dataclass` class in `builtin.py` implementing one of the protocols from `types.py`
2. Add a `"type_string": ClassName` entry to `TYPE_MAP` in `json_loader.py`
3. Use the new type string in `card_effects.json`

## Future: SQLite Migration Path

When the card database grows beyond what JSON handles well (10k+ cards, complex queries), the plan is:

1. Create `sqlite_loader.py` parallel to `json_loader.py`
2. Schema: `cards(name, group_name)`, `card_effects(card_name, type, slot, params_json)`, `card_metadata(card_name, key, value)`
3. `load_registry_from_sqlite(path)` returns the same `EffectRegistry` -- engine code unchanged
4. `card_database.py` switches the import, everything else stays the same
