# Effects System

The effects system maps card names to composable effect objects that the simulation engine uses during goldfish runs. Effects are defined as dataclasses in `builtin.py`, registered in `card_effects.json` using a category-based format, and loaded into an `EffectRegistry` at runtime.

## JSON Format (Version 2)

Card effects live in `card_effects.json`. The file uses a grouped structure with categories:

```json
{
  "version": 2,
  "groups": [
    {
      "group": "Human-readable group name",
      "defaults": {
        "categories": [
          {"category": "ramp", "immediate": false, "producer": {"mana_amount": 1}}
        ]
      },
      "cards": {
        "Sol Ring": {},
        "Arcane Signet": {},
        "Custom Card": {
          "categories": [
            {"category": "ramp", "immediate": false, "producer": {"mana_amount": 3}}
          ],
          "priority": 1
        }
      }
    }
  ]
}
```

**Groups** organize cards by function. Each group has optional `defaults` that apply to all cards unless overridden per-card.

**Default categories** (`defaults.categories`) are inherited by cards with no `"categories"` key. A card that specifies its own `"categories"` replaces the defaults entirely.

**Metadata defaults** (`priority`, etc.) merge with per-card metadata -- per-card values win.

**Derived metadata**: `ramp` and `tapped` are automatically derived from categories (any ramp category sets `ramp=true`; tapped tempo or tapped land sets `tapped=true`). Explicit metadata overrides derived values.

## Categories

There are 4 categories. Each card gets a list of categories (can have multiple).

### Land

```json
{"category": "land", "tapped": true}
```

### Ramp (3 variants)

**Producer** -- fixed mana production (mana rocks, dorks):
```json
{"category": "ramp", "immediate": false, "producer": {"mana_amount": 2}}
```

**Immediate producer** -- one-shot mana (Dark Ritual, rituals):
```json
{"category": "ramp", "immediate": true, "producer": {"mana_amount": 3}}
```

**Land to battlefield** -- fetch lands from deck (Cultivate, Rampant Growth):
```json
{"category": "ramp", "immediate": true, "land_to_battlefield": {"count": 1, "tempo": "tapped"}}
```

**Reducer** -- reduce cost of spell types (Jukai Naturalist):
```json
{"category": "ramp", "immediate": false, "reducer": {"spell_type": "enchantment", "amount": 1}}
```

### Draw (3 variants)

**Immediate** -- draw N cards (Harmonize):
```json
{"category": "draw", "immediate": true, "amount": 3}
```

**Per turn** -- draw each turn (Phyrexian Arena):
```json
{"category": "draw", "immediate": false, "per_turn": {"amount": 1}}
```

**Per cast** -- draw on spell cast (Beast Whisperer):
```json
{"category": "draw", "immediate": false, "per_cast": {"amount": 1, "trigger": "creature"}}
```

### Discard

```json
{"category": "discard", "amount": 2}
```

## Effect Classes (builtin.py)

8 composable effect classes:

| Class | Protocol | Category source | Description |
|---|---|---|---|
| `ProduceMana(amount)` | OnPlay | ramp, repeatable producer | Adds fixed mana production |
| `ImmediateMana(amount)` | OnPlay | ramp, immediate producer | One-shot mana as treasure |
| `LandToBattlefield(count, tapped)` | OnPlay | ramp, land_to_battlefield | Fetches lands from deck |
| `ReduceCost(spell_type, amount)` | OnPlay | ramp, reducer | Reduces cost of spell type |
| `DrawCards(amount)` | OnPlay | draw, immediate | Draws N cards |
| `DiscardCards(amount)` | OnPlay | discard | Discards N random cards |
| `PerTurnDraw(amount)` | PerTurn | draw, per_turn | Draws N cards each turn |
| `PerCastDraw(amount, trigger)` | CastTrigger | draw, per_cast | Draws on matching spell cast |

## Slots

- **`on_play`** -- Fires once when the card is played.
- **`per_turn`** -- Fires at the start of each turn while in play.
- **`cast_trigger`** -- Fires whenever another spell is cast while this is in play.
- **`mana_function`** -- Called during mana calculation each turn. Returns an int.

## Card Metadata Fields

| Field | Type | Default | Description |
|---|---|---|---|
| `priority` | int | 0 | Play order priority (higher = played later within a turn) |
| `ramp` | bool | false | *Derived* from ramp categories; can be explicitly overridden |
| `tapped` | bool | false | *Derived* from tapped tempo/land categories; can be explicitly overridden |
| `extra_types` | list[str] | null | Additional types for simulation (e.g. `["sorcery"]`, `["land"]`) |
| `override_cmc` | int | null | Override the card's CMC for simulation |

## How to Add a New Card

1. Find (or create) the appropriate group in `card_effects.json`
2. Add the card name as a key under `"cards"`
3. If the card matches the group's default categories, use `{}`
4. If the card needs custom categories, specify its own `"categories"` list

Example -- adding a new mana rock that produces 1 mana:

```json
"cards": {
  "My New Signet": {}
}
```

Example -- adding a card with custom categories:

```json
"cards": {
  "My Custom Card": {
    "categories": [
      {"category": "draw", "immediate": true, "amount": 2},
      {"category": "ramp", "immediate": false, "producer": {"mana_amount": 1}}
    ],
    "priority": 1
  }
}
```

## Otag Registry

`otag_registry.json` maps card names to their Scryfall otags (e.g. `ramp`, `card-advantage`, `cheaper-than-mv`). This file is populated by the `autocard fetch-otags` CLI command and used by the web wizard to filter which cards need labeling.

- **`otag_loader.py`** provides `load_otag_registry()`, `get_matching_cards()`, and `has_cheaper_than_mv()` for querying the registry.
- The registry is committed reference data (not gitignored).

## How to Add a New Effect Type

1. Create a new `@dataclass` class in `builtin.py` implementing one of the protocols from `types.py`
2. Add a translation case in `_translate_category()` in `json_loader.py`
3. Add the corresponding category variant to `get_effect_schema()` and `VALID_CATEGORIES`
