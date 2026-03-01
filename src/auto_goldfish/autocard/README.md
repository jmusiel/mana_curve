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
  "effects": [
    {"type": "produce_mana", "slot": "on_play", "params": {"amount": 2}}
  ],
  "metadata": {"ramp": true}
}
```

- **effects**: A list of effect descriptors. Each has a `type`, a `slot` (when it triggers), and `params`.
- **metadata**: Optional fields that control how the simulator treats the card.

Cards that don't fit any effect type get empty effects:

```json
{"effects": [], "metadata": {}}
```

---

## Slots (When Effects Trigger)

Every effect must be assigned to exactly one slot:

| Slot | When it triggers | Example cards |
|------|-----------------|---------------|
| `on_play` | Once, when the card is played | Sol Ring, Cultivate, Rishkar's Expertise |
| `per_turn` | At the start of each turn after the card is in play | Phyrexian Arena, As Foretold |
| `cast_trigger` | Each time another spell is cast while this card is in play | Beast Whisperer, The Great Henge |
| `mana_function` | Evaluated dynamically each turn for mana production | Cryptolith Rite, Serra's Sanctum |

---

## Effect Types Reference

### `produce_mana` -- Fixed Mana Production

**Slot**: `on_play`

Permanently increases the player's mana production by a fixed amount when played. Use this for mana rocks, mana dorks, and land-ramp spells.

**Params**:

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `amount` | int | 1 | Mana added per turn |

**Examples**:

```json
// Sol Ring: taps for 2 colorless
{"type": "produce_mana", "slot": "on_play", "params": {"amount": 2}}

// Arcane Signet: taps for 1 mana
{"type": "produce_mana", "slot": "on_play", "params": {"amount": 1}}

// Open the Way: puts 3 lands into play
{"type": "produce_mana", "slot": "on_play", "params": {"amount": 3}}
```

**Metadata**: Almost always paired with `"ramp": true`.

**Common cards**: Sol Ring, Arcane Signet, Fellwar Stone, Cultivate, Kodama's Reach, Farseek, Sakura-Tribe Elder, signets, talismans, mana dorks, land auras (Utopia Sprawl, Wild Growth).

---

### `draw_cards` -- Immediate Card Draw

**Slot**: `on_play`

Draws N cards when the card is played. Use this for any spell or ETB effect that draws a fixed number of cards.

**Params**:

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `amount` | int | 1 | Number of cards drawn |

**Examples**:

```json
// Harmonize: draw 3 cards
{"type": "draw_cards", "slot": "on_play", "params": {"amount": 3}}

// Night's Whisper: draw 2 (ignore the life loss)
{"type": "draw_cards", "slot": "on_play", "params": {"amount": 2}}

// Rishkar's Expertise: draw 4 (approximate)
{"type": "draw_cards", "slot": "on_play", "params": {"amount": 4}}
```

**When to use vs `draw_discard`**: Use `draw_cards` when the card draws and you keep all the cards. Use `draw_discard` when there's a discard component (like Faithless Looting) or when you see some cards and pick some (like Fact or Fiction).

**Common cards**: Harmonize, Night's Whisper, Read the Bones, Concentrate, Rishkar's Expertise, Inspiring Call, Armorcraft Judge.

---

### `draw_discard` -- Draw, Discard, and Treasure Effects

**Slot**: `on_play`

Models complex card selection effects: draw some cards, discard some, optionally draw more, and optionally create treasure tokens. The steps happen in order: first_draw -> discard -> second_draw -> make_treasures.

**Params**:

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `first_draw` | int | 0 | Cards drawn in the first step |
| `discard` | int | 0 | Cards discarded after the first draw |
| `second_draw` | int | 0 | Cards drawn after discarding |
| `make_treasures` | int | 0 | Treasure tokens created |

**Examples**:

```json
// Faithless Looting: draw 2, discard 2
{"type": "draw_discard", "slot": "on_play", "params": {"first_draw": 2, "discard": 2}}

// Fact or Fiction: reveal 5, opponent splits, you pick a pile (approximate: draw 5, discard 2)
{"type": "draw_discard", "slot": "on_play", "params": {"first_draw": 5, "discard": 2}}

// Windfall: discard hand, draw 6 (approximate)
{"type": "draw_discard", "slot": "on_play", "params": {"discard": 100, "second_draw": 6}}

// Big Score / Unexpected Windfall: discard 1, draw 2, make 2 treasures
{"type": "draw_discard", "slot": "on_play", "params": {"discard": 1, "second_draw": 2, "make_treasures": 2}}

// Deadly Dispute: draw 2, make 1 treasure (no discard)
{"type": "draw_discard", "slot": "on_play", "params": {"first_draw": 2, "make_treasures": 1}}

// Brainstorm: draw 1 (net cards; approximate)
{"type": "draw_discard", "slot": "on_play", "params": {"first_draw": 1}}

// Consider: look at 2, keep 1 (approximate: draw 2, discard 1)
{"type": "draw_discard", "slot": "on_play", "params": {"first_draw": 2, "discard": 1}}
```

**Modeling tip**: The simulator discards randomly, so the params model the *net card advantage*, not the exact mechanic. For "look at N, keep M" effects, use `first_draw: N, discard: N - M`.

**Common cards**: Faithless Looting, Brainstorm, Fact or Fiction, Windfall, Big Score, Deadly Dispute, Prismari Command, Frantic Search.

---

### `reduce_cost` -- Spell Cost Reduction

**Slot**: `on_play`

Permanently reduces the cost of spells of a certain type by a fixed amount. The reduction applies to all future spells cast while this card is in play. Multiple reductions stack. A card's cost is never reduced below 1.

**Params**:

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `nonpermanent` | int | 0 | Reduction for instants and sorceries |
| `permanent` | int | 0 | Reduction for all permanents |
| `spell` | int | 0 | Reduction for all spells |
| `creature` | int | 0 | Reduction for creature spells |
| `enchantment` | int | 0 | Reduction for enchantment spells |

Only set the param(s) relevant to the card. Leave the rest at 0 (or omit them).

**Examples**:

```json
// Jukai Naturalist: enchantments cost 1 less
{"type": "reduce_cost", "slot": "on_play", "params": {"enchantment": 1}}

// Hamza, Guardian of Arashin: creatures cost 1 less
{"type": "reduce_cost", "slot": "on_play", "params": {"creature": 1}}

// Thunderclap Drake: instants and sorceries cost 1 less
{"type": "reduce_cost", "slot": "on_play", "params": {"nonpermanent": 1}}

// Archmage of Runes: instants/sorceries cost 1 less AND draws on cast (multi-effect)
// (see "Cards with Multiple Effects" below)
```

**When NOT to use**: Don't use `reduce_cost` for cards that conditionally reduce their own cost (like Blasphemous Act or Ghalta). Those are self-cost-reduction, not a persistent effect on future spells. Label them as no-effect: `{"effects": [], "metadata": {}}`.

**Common cards**: Jukai Naturalist, Hamza, Umori, Thunderclap Drake, Inquisitive Glimmer, Archmage of Runes.

---

### `tutor_to_hand` -- Search Library for a Card

**Slot**: `on_play`

Searches the deck for the first available card from a priority-ordered target list and puts it into hand. The simulator tries each target name in order and takes the first one found in the deck.

**Params**:

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `targets` | list[str] | *(required)* | Ordered list of card names to search for |

**Examples**:

```json
// Green Sun's Zenith: tutor for key creatures (priority ordered)
{"type": "tutor_to_hand", "slot": "on_play", "params": {"targets": [
  "Gemhide Sliver", "Sanctum Weaver", "Argothian Enchantress"
]}}

// Tolaria West (transmute): find Serra's Sanctum
{"type": "tutor_to_hand", "slot": "on_play", "params": {"targets": ["Serra's Sanctum"]}}
```

**Modeling tip**: The target list should contain card names that actually exist in the registry/deck, ordered by priority (most impactful first). This is deck-specific -- the LLM can't know your exact decklist, so LLM-generated tutor labels will need manual correction.

**Common cards**: Green Sun's Zenith, Finale of Devastation, Tolaria West, Urza's Cave.

---

### `per_turn_draw` -- Recurring Card Draw

**Slot**: `per_turn`

Draws N cards at the start of each turn after the card is in play. Use this for enchantments and creatures that draw every turn.

**Params**:

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `amount` | int | 1 | Cards drawn each turn |

**Examples**:

```json
// Phyrexian Arena: draw 1 per turn (ignore life loss)
{"type": "per_turn_draw", "slot": "per_turn", "params": {"amount": 1}}

// Toski, Bearer of Secrets: draw ~1 per turn (approximate)
{"type": "per_turn_draw", "slot": "per_turn", "params": {"amount": 1}}
```

**Common cards**: Phyrexian Arena, Black Market Connections, Esper Sentinel, Mystic Remora, Toski, Sylvan Library, Welcoming Vampire.

---

### `scaling_mana` -- Mana That Grows Each Turn

**Slot**: `per_turn`

Adds additional mana production each turn. On turn 1 after playing it: +1 mana. Turn 2: +2 mana. And so on. This models cards that accumulate counters or generate increasing amounts of mana/treasures.

**Params**:

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `amount` | int | 1 | Additional mana gained per turn |

**Examples**:

```json
// As Foretold: gains a counter each turn, can cast a spell for free
{"type": "scaling_mana", "slot": "per_turn", "params": {"amount": 1}}

// Smothering Tithe: generates roughly 1 treasure/turn (approximate)
{"type": "scaling_mana", "slot": "per_turn", "params": {"amount": 1}}
```

**Metadata**: Usually paired with `"ramp": true` and `"priority": 2`.

**Common cards**: As Foretold, Smothering Tithe, Gyre Sage, Kodama of the West Tree.

---

### `per_cast_draw` -- Draw on Casting Spells

**Slot**: `cast_trigger`

Draws cards whenever a spell of the matching type is cast while this card is in play. Multiple categories can trigger on the same card.

**Params**:

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `nonpermanent` | int | 0 | Cards drawn per instant/sorcery cast |
| `spell` | int | 0 | Cards drawn per any spell cast |
| `creature` | int | 0 | Cards drawn per creature cast |
| `enchantment` | int | 0 | Cards drawn per enchantment cast |

**Examples**:

```json
// Beast Whisperer: draw 1 per creature cast
{"type": "per_cast_draw", "slot": "cast_trigger", "params": {"creature": 1}}

// Argothian Enchantress: draw 1 per enchantment cast
{"type": "per_cast_draw", "slot": "cast_trigger", "params": {"enchantment": 1}}

// Archmage Emeritus: draw 1 per instant/sorcery cast
{"type": "per_cast_draw", "slot": "cast_trigger", "params": {"nonpermanent": 1}}

// Bolas's Citadel: draw 1 per any spell cast (approximate)
{"type": "per_cast_draw", "slot": "cast_trigger", "params": {"spell": 1}}
```

**Common cards**: Beast Whisperer, Guardian Project, Skullclamp, Enchantress's Presence, Sythis, Argothian Enchantress, Archmage Emeritus, The Great Henge.

---

### `cryptolith_rites_mana` -- Tap Creatures for Mana

**Slot**: `mana_function`

Each untapped creature you control can tap for one mana. The simulator tracks how many creatures you've played and taps them for mana each turn. No params.

**Examples**:

```json
// Cryptolith Rite: your creatures tap for mana
{"type": "cryptolith_rites_mana", "slot": "mana_function"}
```

**Common cards**: Cryptolith Rite, Gemhide Sliver, Manaweft Sliver, Enduring Vitality.

---

### `enchantment_sanctum_mana` -- Mana from Enchantments

**Slot**: `mana_function`

Produces mana equal to the number of enchantments you have in play. No params.

**Examples**:

```json
// Serra's Sanctum: tap for mana equal to enchantments in play
{"type": "enchantment_sanctum_mana", "slot": "mana_function"}
```

**Common cards**: Serra's Sanctum, Sanctum Weaver.

---

## Metadata Fields

Metadata controls how the simulator handles the card beyond its effects.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `priority` | int | 0 | Play priority. Higher = played earlier. Use `2` for scaling/engine cards, `3` for tutors, `1` for card draw. |
| `ramp` | bool | false | `true` if this card produces or increases mana. Affects how the simulator values it. |
| `is_land_tutor` | bool | false | `true` if this card searches for land cards specifically. |
| `tapped` | bool | false | `true` if this card enters tapped or has a significant tempo cost (e.g. taplands). |
| `extra_types` | list[str] | null | Additional card types for the simulator, e.g. `["land"]` for MDFCs or `["artifact"]` for special lands. |
| `override_cmc` | int | null | Override the mana cost for simulation. Used when the actual CMC doesn't reflect how you cast it. |

---

## Cards with Multiple Effects

Some cards have more than one simulatable effect. List all of them in the `effects` array:

```json
// The Great Henge: produces 2 mana AND draws on creature cast
{
  "effects": [
    {"type": "produce_mana", "slot": "on_play", "params": {"amount": 2}},
    {"type": "per_cast_draw", "slot": "cast_trigger", "params": {"creature": 1}}
  ],
  "metadata": {"ramp": true}
}

// Archmage of Runes: reduces instants/sorceries AND draws on cast
{
  "effects": [
    {"type": "per_cast_draw", "slot": "cast_trigger", "params": {"nonpermanent": 1}},
    {"type": "reduce_cost", "slot": "on_play", "params": {"nonpermanent": 1}}
  ],
  "metadata": {}
}

// Solemn Simulacrum: produces 1 mana (ramp)
// (the death-draw is too conditional to model, so just label the ramp)
{
  "effects": [
    {"type": "produce_mana", "slot": "on_play", "params": {"amount": 1}}
  ],
  "metadata": {"ramp": true}
}
```

---

## Registry Format (`card_effects.json`)

The registry groups cards with identical effects together. Each group has `defaults` that apply to all cards unless overridden:

```json
{
  "version": 1,
  "groups": [
    {
      "group": "Mana Producers (1 mana)",
      "defaults": {
        "ramp": true,
        "effects": [{"type": "produce_mana", "slot": "on_play", "params": {"amount": 1}}]
      },
      "cards": {
        "Arcane Signet": {},
        "Fellwar Stone": {},
        "Cultivate": {}
      }
    },
    {
      "group": "Special Cards",
      "defaults": {},
      "cards": {
        "The Great Henge": {
          "effects": [
            {"type": "produce_mana", "slot": "on_play", "params": {"amount": 2}},
            {"type": "per_cast_draw", "slot": "cast_trigger", "params": {"creature": 1}}
          ],
          "ramp": true
        }
      }
    }
  ]
}
```

- An empty `{}` for a card means it inherits all defaults from its group.
- Per-card `effects` completely replace the group default effects.
- Per-card metadata fields (like `ramp`, `tapped`) override the group defaults for that field only.

---

## Adding Cards Manually

To add a card to the existing registry (`src/auto_goldfish/effects/card_effects.json`):

1. Find the right group (or create a new one).
2. Add the card name as a key. Use `{}` if it matches the group defaults, or specify overrides.

**Example -- adding Llanowar Elves to the 1-mana producers group**:

```json
{
  "group": "Mana Producers (1 mana)",
  "defaults": {
    "ramp": true,
    "effects": [{"type": "produce_mana", "slot": "on_play", "params": {"amount": 1}}]
  },
  "cards": {
    "Arcane Signet": {},
    "Llanowar Elves": {}
  }
}
```

**Example -- adding a card with unique effects**:

```json
{
  "group": "Special Cards",
  "defaults": {},
  "cards": {
    "Selvala, Heart of the Wilds": {
      "effects": [
        {"type": "produce_mana", "slot": "on_play", "params": {"amount": 2}},
        {"type": "per_cast_draw", "slot": "cast_trigger", "params": {"creature": 1}}
      ],
      "ramp": true,
      "priority": 2
    }
  }
}
```

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

1. **Life loss modeled as cost reduction**: The LLM sometimes tries to model "you lose N life" as a `reduce_cost` effect. Life loss should be ignored -- it doesn't affect the mana curve simulation.

2. **Self-cost-reduction modeled as `reduce_cost`**: Cards like Blasphemous Act or Ghalta that reduce their own cost should be `{"effects": [], "metadata": {}}`. `reduce_cost` is for permanent effects that reduce the cost of *future* spells.

3. **Conditional draw modeled as guaranteed draw**: Cards like "draw a card if you control a creature" should be labeled conservatively. If the condition is almost always true in practice, label it as draw. If it's unreliable, consider `{"effects": [], "metadata": {}}`.

4. **Tutor targets**: The LLM doesn't know your decklist, so `tutor_to_hand` targets will be generic (basic land names, etc). Replace them with the actual card names from your deck.

5. **Lands labeled as `produce_mana`**: Basic and utility lands don't need to be in the effect registry at all -- the simulator handles land mana production separately. Only label lands that have *additional* effects (like Cabal Coffers or Lrien Revealed).

### Correcting a Label

Edit `labeled_cards.json` directly, then re-export:

```bash
# Edit the file
vim src/auto_goldfish/autocard/data/labeled_cards.json

# Validate your changes
autocard validate

# Re-export
autocard export
```

---

## CLI Reference

### `autocard fetch`

Download top cards from Scryfall.

```
autocard fetch [--count N] [--query QUERY] [--output PATH]
```

- `--count`: Number of cards (default: 1000)
- `--query`: Scryfall search query (default: `f:commander`)
- `--output`: Output path (default: `autocard/data/top_cards.json`)

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

- `--model`: Ollama model (default: `llama4:16x17b`)
- `--batch-size`: Cards per LLM call (default: 1, try 10 for speed)
- `--concurrency`: Parallel Ollama requests (default: 1, try 4)
- `--resume`: Skip already-labeled cards (default: on)

### `autocard validate`

Validate all labels in `labeled_cards.json` against the effect schema.

```
autocard validate [--cards PATH]
```

### `autocard export`

Export labeled cards to a registry JSON file.

```
autocard export [--output PATH] [--merge PATH] [--cards PATH]
```

- `--merge`: Path to existing `card_effects.json` to merge with (preserves existing entries)
- `--output`: Output path (default: `autocard/data/card_effects_expanded.json`)

---

## Dependencies

The labeling pipeline requires [Ollama](https://ollama.ai) running locally with a model pulled:

```bash
# Install the Python package
pip install auto_goldfish[autocard]

# Pull a model
ollama pull gemma3:12b
```

All other autocard commands (fetch, coverage, validate, export) work without Ollama.
