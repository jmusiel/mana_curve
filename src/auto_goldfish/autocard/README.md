# Autocard: Automatic Card Effect Labeling

Autocard fetches popular EDH cards from Scryfall and labels them with machine-interpretable effects for the mana curve simulator. Labels can be generated automatically via a local LLM (Ollama) or written by hand.

## Quick Start

```bash
# 1. Fetch cards from Scryfall
autocard fetch --count 1000 --query "(otag:draw or otag:card-advantage or otag:ramp) -t:land f:commander"

# 2. Check how many are already in the registry
autocard coverage

# 3. Label unlabeled cards with an LLM
autocard label --model gemma3:12b --batch-size 10 --concurrency 4

# 4. Validate the labels
autocard validate

# 5. Export to a registry JSON file
autocard export --merge path/to/card_effects.json
```

Or use the convenience script:

```bash
./scripts/run_labeling.sh              # batch=10, concurrency=4, gemma3:12b
./scripts/run_labeling.sh 20 4 llama3:8b  # batch=20, concurrency=4, llama3:8b
```

The labeling pipeline is **resume-safe** -- if interrupted, re-running picks up where it left off.

## How Labels Work

Every card in the simulator is described by a **label**: a JSON object with two keys:

```json
{
  "categories": [
    {"category": "ramp", "immediate": false, "producer": {"mana_amount": 2}}
  ],
  "metadata": {}
}
```

- **categories**: A list of category descriptors. Each has a `category` type and variant-specific fields.
- **metadata**: Optional fields that control how the simulator treats the card.

Cards that don't fit any category get empty categories:

```json
{"categories": [], "metadata": {}}
```

---

## The 4 Categories

### `ramp` -- Mana Acceleration

Ramp has 3 variants, selected by which sub-key is present.

#### Producer (repeatable)

Permanently increases mana production. Use for mana rocks, dorks, and land auras.

```json
// Sol Ring: taps for 2 colorless
{"category": "ramp", "immediate": false, "producer": {"mana_amount": 2}}

// Arcane Signet: taps for 1
{"category": "ramp", "immediate": false, "producer": {"mana_amount": 1}}
```

**Common cards**: Sol Ring, Arcane Signet, Fellwar Stone, signets, talismans, mana dorks, land auras.

#### Producer (immediate)

One-shot mana burst added as treasure. Use for rituals and temporary mana.

```json
// Dark Ritual: adds 3 mana
{"category": "ramp", "immediate": true, "producer": {"mana_amount": 3}}
```

**Common cards**: Dark Ritual, Culling Ritual, Jeska's Will.

#### Land to Battlefield

Fetches lands from the deck onto the battlefield.

```json
// Rampant Growth: fetch 1 land tapped
{"category": "ramp", "immediate": true, "land_to_battlefield": {"count": 1, "tempo": "tapped"}}

// Skyshroud Claim: fetch 2 lands untapped
{"category": "ramp", "immediate": true, "land_to_battlefield": {"count": 2, "tempo": "untapped"}}
```

**Common cards**: Cultivate, Kodama's Reach, Rampant Growth, Farseek, Sakura-Tribe Elder.

#### Reducer

Permanently reduces the cost of a spell type.

```json
// Jukai Naturalist: enchantments cost 1 less
{"category": "ramp", "immediate": false, "reducer": {"spell_type": "enchantment", "amount": 1}}

// Hamza: creatures cost 1 less
{"category": "ramp", "immediate": false, "reducer": {"spell_type": "creature", "amount": 1}}
```

Valid `spell_type` values: `"creature"`, `"enchantment"`, `"nonpermanent"`, `"permanent"`, `"spell"`.

**When NOT to use**: Don't use reducer for cards that reduce only their own cost (like Blasphemous Act). Those should be `{"categories": [], "metadata": {}}`.

**Common cards**: Jukai Naturalist, Hamza, Thunderclap Drake, Inquisitive Glimmer.

---

### `draw` -- Card Draw

Draw has 3 variants based on timing.

#### Immediate

Draws N cards when played.

```json
// Harmonize: draw 3
{"category": "draw", "immediate": true, "amount": 3}

// Night's Whisper: draw 2 (ignore life loss)
{"category": "draw", "immediate": true, "amount": 2}
```

**Common cards**: Harmonize, Night's Whisper, Read the Bones, Rishkar's Expertise.

#### Per Turn

Draws N cards at the start of each turn while in play.

```json
// Phyrexian Arena: draw 1 per turn
{"category": "draw", "immediate": false, "per_turn": {"amount": 1}}
```

**Common cards**: Phyrexian Arena, Black Market Connections, Esper Sentinel, Sylvan Library.

#### Per Cast

Draws cards when a matching spell type is cast.

```json
// Beast Whisperer: draw 1 per creature
{"category": "draw", "immediate": false, "per_cast": {"amount": 1, "trigger": "creature"}}

// Archmage Emeritus: draw 1 per instant/sorcery
{"category": "draw", "immediate": false, "per_cast": {"amount": 1, "trigger": "nonpermanent"}}
```

Valid `trigger` values: `"spell"`, `"creature"`, `"enchantment"`, `"land"`, `"artifact"`, `"nonpermanent"`.

**Common cards**: Beast Whisperer, Guardian Project, Enchantress's Presence, Sythis, The Great Henge.

---

### `discard` -- Discard Cards

Discards N random cards from hand.

```json
// Faithless Looting discard component
{"category": "discard", "amount": 2}
```

---

### `land` -- Land Properties

Describes special land behavior.

```json
// Enters tapped
{"category": "land", "tapped": true}
```

---

## Cards with Multiple Categories

Some cards have multiple effects. List all categories:

```json
// The Great Henge: produces 2 mana AND draws on creature cast
{
  "categories": [
    {"category": "ramp", "immediate": false, "producer": {"mana_amount": 2}},
    {"category": "draw", "immediate": false, "per_cast": {"amount": 1, "trigger": "creature"}}
  ],
  "metadata": {}
}

// Faithless Looting: draw 2, discard 2
{
  "categories": [
    {"category": "draw", "immediate": true, "amount": 2},
    {"category": "discard", "amount": 2}
  ],
  "metadata": {}
}
```

---

## Metadata Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `priority` | int | 0 | Play priority. Higher = played earlier. Use `2` for engine cards, `1` for card draw. |
| `override_cmc` | int | null | Override the mana cost for simulation. |
| `extra_types` | list[str] | null | Additional card types (e.g. `["land"]` for MDFCs). |

Note: `ramp` and `tapped` are **derived** from categories automatically. Any ramp category sets `ramp=true`. Tapped tempo or tapped land sets `tapped=true`. These can be explicitly overridden in metadata if needed.

---

## Registry Format (`card_effects.json`)

The registry groups cards with identical categories together:

```json
{
  "version": 2,
  "groups": [
    {
      "group": "Repeatable Mana Producers (1 mana)",
      "defaults": {
        "categories": [
          {"category": "ramp", "immediate": false, "producer": {"mana_amount": 1}}
        ]
      },
      "cards": {
        "Arcane Signet": {},
        "Fellwar Stone": {}
      }
    }
  ]
}
```

- An empty `{}` for a card means it inherits all defaults from its group.
- Per-card `categories` completely replace the group default categories.
- Per-card metadata fields (like `priority`) override the group defaults for that field only.

---

## Reviewing LLM Labels

After running `autocard label`, the results are saved to `autocard/data/labeled_cards.json`. To review:

```bash
# Validate all labels against the schema
autocard validate

# Export and check the grouped output
autocard export
```

### Common LLM Mistakes to Watch For

1. **Life loss modeled as effects**: The LLM sometimes tries to model "you lose N life". Life loss should be ignored -- it doesn't affect the mana curve simulation.

2. **Self-cost-reduction modeled as reducer**: Cards like Blasphemous Act or Ghalta that reduce their own cost should be `{"categories": [], "metadata": {}}`. Reducer is for permanent effects that reduce the cost of *future* spells.

3. **Conditional draw modeled as guaranteed draw**: Cards like "draw a card if you control a creature" should be labeled conservatively. If the condition is almost always true, label it as draw. If unreliable, use `{"categories": [], "metadata": {}}`.

4. **Lands labeled as ramp**: Basic and utility lands don't need to be in the effect registry -- the simulator handles land mana separately. Only label lands with *additional* effects.

### Correcting a Label

Edit `labeled_cards.json` directly, then re-export:

```bash
vim src/auto_goldfish/autocard/data/labeled_cards.json
autocard validate
autocard export
```

---

## CLI Reference

### `autocard fetch`

Download top cards from Scryfall.

```
autocard fetch [--count N] [--query QUERY] [--output PATH]
```

### `autocard coverage`

Report how many fetched cards are already in the effect registry.

```
autocard coverage [--cards PATH] [--registry PATH]
```

### `autocard label`

Run LLM labeling on unlabeled cards.

```
autocard label [--count N] [--model MODEL] [--batch-size N] [--concurrency N]
               [--resume] [--cards PATH] [--output PATH]
```

### `autocard validate`

Validate all labels against the category schema.

```
autocard validate [--cards PATH]
```

### `autocard export`

Export labeled cards to a registry JSON file.

```
autocard export [--output PATH] [--merge PATH] [--cards PATH]
```

---

## Dependencies

The labeling pipeline requires [Ollama](https://ollama.ai) running locally with a model pulled:

```bash
pip install auto_goldfish[autocard]
ollama pull gemma3:12b
```

All other autocard commands (fetch, coverage, validate, export) work without Ollama.
