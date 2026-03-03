"""LLM-based card labeling using Ollama."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from auto_goldfish.effects.json_loader import METADATA_FIELDS, VALID_CATEGORIES

from .schemas import ScryfallCard
from .validator import validate_label

logger = logging.getLogger(__name__)

_DEFAULT_LABELED_PATH = Path(__file__).parent / "data" / "labeled_cards.json"

SYSTEM_PROMPT = """\
You are a Magic: The Gathering card analyst for a mana curve simulator.
Your job is to label cards with machine-interpretable categories.

## Categories
Each card gets a list of categories. A card can have multiple.

### land
For lands that enter tapped:
  {"category": "land", "tapped": true}
Normal lands need no entry (the simulator handles them automatically).

### ramp (6 variants)
Immediate mana (one-shot, like Dark Ritual):
  {"category": "ramp", "immediate": true, "producer": {"mana_amount": 3}}

Immediate land fetch (like Cultivate putting a land onto battlefield):
  {"category": "ramp", "immediate": true, "land_to_battlefield": {"count": 1, "tempo": "tapped"}}

Repeatable mana producer (like Sol Ring, mana dorks):
  {"category": "ramp", "immediate": false, "producer": {"mana_amount": 1, "producer_type": "rock", "tempo": "untapped"}}

Cost reducer (like Goblin Warchief):
  {"category": "ramp", "immediate": false, "reducer": {"spell_type": "creature", "amount": 1}}
  spell_type: "creature", "enchantment", "nonpermanent", "permanent", "spell"

### draw (3 variants)
Immediate draw (like Harmonize):
  {"category": "draw", "immediate": true, "amount": 3}

Repeatable per-turn draw (like Phyrexian Arena):
  {"category": "draw", "immediate": false, "per_turn": {"amount": 1}}

Repeatable per-cast draw (like Beast Whisperer):
  {"category": "draw", "immediate": false, "per_cast": {"amount": 1, "trigger": "creature"}}
  trigger: "spell", "creature", "enchantment", "land", "artifact", "nonpermanent"

### discard (immediate only)
  {"category": "discard", "amount": 2}

## Metadata (all optional, per-card)
  - priority (int): play priority (0 = normal, 2 = high)
  - override_cmc (int): override the mana cost for simulation purposes
  - extra_types (list[str]): additional card types, e.g. ["land", "artifact"]

## Output Schema
Return a JSON object with exactly two keys:
{
  "categories": [<category objects>],
  "metadata": {<key>: <value>}
}

## Important Rules
- Only label effects the simulator can model (the categories above)
- Cards that don't fit any category: {"categories": [], "metadata": {}}
- Mana rocks/dorks that add 1 mana: ramp, immediate=false, producer, mana_amount=1
- Sol Ring (adds 2): ramp, immediate=false, producer, mana_amount=2
- Cost reducers: ramp, immediate=false, reducer
- Card draw on ETB: draw, immediate=true
- Recurring draw each turn: draw, immediate=false, per_turn
- Draw on cast trigger: draw, immediate=false, per_cast
- Draw+discard (e.g. Faithless Looting draw 2 discard 2): use both draw and discard categories

## Examples

### Sol Ring
Input: name="Sol Ring", mana_cost="{1}", type_line="Artifact", oracle_text="{T}: Add {C}{C}."
Output: {"categories": [{"category": "ramp", "immediate": false, "producer": {"mana_amount": 2}}], "metadata": {}}

### Phyrexian Arena
Input: name="Phyrexian Arena", mana_cost="{1}{B}{B}", type_line="Enchantment", oracle_text="At the beginning of your upkeep, you draw a card and you lose 1 life."
Output: {"categories": [{"category": "draw", "immediate": false, "per_turn": {"amount": 1}}], "metadata": {}}

### The Great Henge
Input: name="The Great Henge", mana_cost="{7}{G}{G}", type_line="Legendary Artifact", oracle_text="This spell costs {X} less to cast, where X is the greatest power among creatures you control. {T}: Add {G}{G}. You gain 2 life. Whenever a nontoken creature enters the battlefield under your control, put a +1/+1 counter on it and draw a card."
Output: {"categories": [{"category": "ramp", "immediate": false, "producer": {"mana_amount": 2}}, {"category": "draw", "immediate": false, "per_cast": {"amount": 1, "trigger": "creature"}}], "metadata": {}}

### Lightning Bolt (no simulatable effect)
Input: name="Lightning Bolt", mana_cost="{R}", type_line="Instant", oracle_text="Lightning Bolt deals 3 damage to any target."
Output: {"categories": [], "metadata": {}}
"""

BATCH_SYSTEM_PROMPT = """\
You are a Magic: The Gathering card analyst for a mana curve simulator.
Your job is to label multiple cards at once with machine-interpretable categories.

## Categories
Each card gets a list of categories (land, ramp, draw, discard). A card can have multiple.

### land
  {"category": "land", "tapped": true}  (only for tapped lands)

### ramp
  Immediate producer: {"category": "ramp", "immediate": true, "producer": {"mana_amount": 3}}
  Land fetch: {"category": "ramp", "immediate": true, "land_to_battlefield": {"count": 1, "tempo": "tapped"}}
  Repeatable producer: {"category": "ramp", "immediate": false, "producer": {"mana_amount": 1}}
  Cost reducer: {"category": "ramp", "immediate": false, "reducer": {"spell_type": "creature", "amount": 1}}

### draw
  Immediate: {"category": "draw", "immediate": true, "amount": 3}
  Per-turn: {"category": "draw", "immediate": false, "per_turn": {"amount": 1}}
  Per-cast: {"category": "draw", "immediate": false, "per_cast": {"amount": 1, "trigger": "creature"}}

### discard
  {"category": "discard", "amount": 2}

## Metadata (all optional)
  priority (int), override_cmc (int), extra_types (list[str])

## Output Schema
Return a JSON object keyed by card name. Each value has "categories" and "metadata":
{
  "Card Name": {
    "categories": [<category objects>],
    "metadata": {...}
  },
  ...
}

You MUST include an entry for every card listed in the prompt, using the exact card name.
Cards with no simulatable effects: {"categories": [], "metadata": {}}
"""

_LABEL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "categories": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {"type": "string"},
                },
                "required": ["category"],
            },
        },
        "metadata": {"type": "object"},
    },
    "required": ["categories", "metadata"],
}

# JSON schema for single-card structured output (ollama format parameter).
JSON_SCHEMA: dict[str, Any] = _LABEL_SCHEMA


def batch_json_schema(card_names: list[str]) -> dict[str, Any]:
    """Build a JSON schema for a batch response keyed by card name."""
    return {
        "type": "object",
        "properties": {name: _LABEL_SCHEMA for name in card_names},
        "required": card_names,
    }


def build_card_prompt(card: ScryfallCard) -> str:
    """Format a ScryfallCard into a user-message prompt for the LLM."""
    parts = [
        f"name=\"{card.name}\"",
        f"mana_cost=\"{card.mana_cost}\"",
        f"cmc={card.cmc}",
        f"type_line=\"{card.type_line}\"",
        f"oracle_text=\"{card.oracle_text}\"",
    ]
    if card.keywords:
        parts.append(f"keywords={card.keywords}")
    if card.produced_mana:
        parts.append(f"produced_mana={card.produced_mana}")
    return "Label this card:\n" + ", ".join(parts)


def build_batch_prompt(cards: list[ScryfallCard]) -> str:
    """Format multiple ScryfallCards into a single user-message prompt."""
    sections = []
    for i, card in enumerate(cards, 1):
        parts = [
            f"name=\"{card.name}\"",
            f"mana_cost=\"{card.mana_cost}\"",
            f"cmc={card.cmc}",
            f"type_line=\"{card.type_line}\"",
            f"oracle_text=\"{card.oracle_text}\"",
        ]
        if card.keywords:
            parts.append(f"keywords={card.keywords}")
        if card.produced_mana:
            parts.append(f"produced_mana={card.produced_mana}")
        sections.append(f"Card {i}:\n" + ", ".join(parts))
    return "Label these cards:\n\n" + "\n\n".join(sections)


def label_card_batch(
    cards: list[ScryfallCard],
    model: str = "llama4:16x17b",
    max_retries: int = 3,
) -> dict[str, dict]:
    """Label a batch of cards in a single Ollama call.

    Returns a dict mapping card name to label dict.
    Retries up to max_retries times on JSON parse failure.
    """
    import ollama

    card_names = [c.name for c in cards]
    schema = batch_json_schema(card_names)

    messages = [
        {"role": "system", "content": BATCH_SYSTEM_PROMPT},
        {"role": "user", "content": build_batch_prompt(cards)},
    ]

    for attempt in range(max_retries):
        try:
            response = ollama.chat(
                model=model,
                messages=messages,
                format=schema,
                options={"temperature": 0},
            )
            content = response["message"]["content"]
            parsed = json.loads(content)
            # Verify all card names are present
            missing = set(card_names) - set(parsed.keys())
            if missing:
                logger.warning(
                    "Attempt %d/%d batch missing cards: %s",
                    attempt + 1, max_retries, missing,
                )
                if attempt == max_retries - 1:
                    # Return what we got — caller will handle missing cards
                    return parsed
                continue
            return parsed
        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning(
                "Attempt %d/%d batch failed: %s",
                attempt + 1, max_retries, exc,
            )
            if attempt == max_retries - 1:
                raise ValueError(
                    f"Failed to get valid JSON for batch after {max_retries} attempts"
                ) from exc

    raise ValueError("Failed to label batch")  # pragma: no cover


def label_card(
    card: ScryfallCard,
    model: str = "llama4:16x17b",
    max_retries: int = 3,
) -> dict:
    """Label a single card using an Ollama LLM.

    Returns the parsed label dict with 'categories' and 'metadata' keys.
    Retries up to max_retries times on JSON parse failure.
    """
    import ollama

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_card_prompt(card)},
    ]

    for attempt in range(max_retries):
        try:
            response = ollama.chat(
                model=model,
                messages=messages,
                format=JSON_SCHEMA,
                options={"temperature": 0},
            )
            content = response["message"]["content"]
            return json.loads(content)
        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning(
                "Attempt %d/%d for %s failed: %s",
                attempt + 1, max_retries, card.name, exc,
            )
            if attempt == max_retries - 1:
                raise ValueError(
                    f"Failed to get valid JSON for {card.name} after {max_retries} attempts"
                ) from exc

    # Unreachable but satisfies type checker
    raise ValueError(f"Failed to label {card.name}")  # pragma: no cover


def load_labeled(path: Path | None = None) -> dict[str, dict]:
    """Load previously labeled cards from disk."""
    if path is None:
        path = _DEFAULT_LABELED_PATH
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_labeled(labeled: dict[str, dict], path: Path | None = None) -> Path:
    """Save labeled cards to disk."""
    if path is None:
        path = _DEFAULT_LABELED_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(labeled, f, indent=2)
    return path


def label_cards(
    cards: list[ScryfallCard],
    model: str = "llama4:16x17b",
    output_path: Path | None = None,
    resume: bool = True,
    concurrency: int = 1,
    batch_size: int = 1,
) -> dict[str, dict]:
    """Label multiple cards with LLM, with incremental saving and resume support.

    Args:
        cards: List of cards to label.
        model: Ollama model name.
        output_path: Path to save results (default: data/labeled_cards.json).
        resume: If True, skip cards already in the output file.
        concurrency: Number of parallel Ollama requests.
        batch_size: Number of cards per LLM call (>1 uses batch mode).

    Returns:
        Dict mapping card name to label dict.
    """
    import threading
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from tqdm import tqdm

    if output_path is None:
        output_path = _DEFAULT_LABELED_PATH

    # Load existing results for resume
    results = load_labeled(output_path) if resume else {}
    lock = threading.Lock()

    # Filter to cards that still need labeling
    to_label = [c for c in cards if c.name not in results]

    # Chunk into batches
    batches: list[list[ScryfallCard]] = []
    for i in range(0, len(to_label), batch_size):
        batches.append(to_label[i : i + batch_size])

    def _process_batch(batch: list[ScryfallCard]) -> dict[str, dict]:
        batch_results: dict[str, dict] = {}

        if len(batch) == 1:
            # Single card — use single-card path
            card = batch[0]
            try:
                label = label_card(card, model=model)
            except ValueError:
                logger.error("Failed to label %s, skipping", card.name)
                return batch_results
            errors = validate_label(card.name, label)
            if errors:
                logger.warning("Validation errors for %s: %s", card.name, errors)
            batch_results[card.name] = label
            return batch_results

        # Multi-card batch
        try:
            batch_labels = label_card_batch(batch, model=model)
        except ValueError:
            # Batch failed — fall back to single-card for each
            logger.warning("Batch failed, falling back to single-card labeling")
            for card in batch:
                try:
                    label = label_card(card, model=model)
                except ValueError:
                    logger.error("Failed to label %s, skipping", card.name)
                    continue
                errors = validate_label(card.name, label)
                if errors:
                    logger.warning("Validation errors for %s: %s", card.name, errors)
                batch_results[card.name] = label
            return batch_results

        # Validate each card in batch results
        for card in batch:
            if card.name in batch_labels:
                label = batch_labels[card.name]
                errors = validate_label(card.name, label)
                if errors:
                    logger.warning("Validation errors for %s: %s", card.name, errors)
                batch_results[card.name] = label
            else:
                # Card missing from batch — fall back to single
                logger.warning("%s missing from batch, trying single-card", card.name)
                try:
                    label = label_card(card, model=model)
                except ValueError:
                    logger.error("Failed to label %s, skipping", card.name)
                    continue
                errors = validate_label(card.name, label)
                if errors:
                    logger.warning("Validation errors for %s: %s", card.name, errors)
                batch_results[card.name] = label

        return batch_results

    with tqdm(total=len(to_label), desc="Labeling cards") as pbar:
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = {
                pool.submit(_process_batch, batch): batch for batch in batches
            }
            for future in as_completed(futures):
                batch_results = future.result()
                with lock:
                    results.update(batch_results)
                    save_labeled(results, output_path)
                pbar.update(len(futures[future]))

    return results
