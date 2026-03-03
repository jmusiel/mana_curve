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

## How to respond
First, write a brief "reasoning" analyzing the card, then fill in "categories".
Each category is a SELF-CONTAINED object — all variant fields go INSIDE it.

## Category Types

### ramp
Repeatable mana producer (mana rocks, signets, dorks):
  {"category": "ramp", "immediate": false, "producer": {"mana_amount": 1}}
Immediate mana (rituals, one-shot):
  {"category": "ramp", "immediate": true, "producer": {"mana_amount": 3}}
Land fetch (Cultivate, Rampant Growth):
  {"category": "ramp", "immediate": true, "land_to_battlefield": {"count": 1, "tempo": "tapped"}}
Cost reducer (Goblin Warchief):
  {"category": "ramp", "immediate": false, "reducer": {"spell_type": "creature", "amount": 1}}
  Valid spell_type: "creature", "enchantment", "nonpermanent", "permanent", "spell"

### draw
Immediate (Harmonize):
  {"category": "draw", "immediate": true, "amount": 3}
Per-turn (Phyrexian Arena):
  {"category": "draw", "immediate": false, "per_turn": {"amount": 1}}
Per-cast (Beast Whisperer):
  {"category": "draw", "immediate": false, "per_cast": {"amount": 1, "trigger": "creature"}}
  Valid trigger: "spell", "creature", "enchantment", "land", "artifact", "nonpermanent"

### discard
  {"category": "discard", "amount": 2}

### land
  {"category": "land", "tapped": true}
  (only for lands that enter tapped; normal lands need no entry)

## Rules
- Cards that don't fit any category: {"categories": []}
- Draw+discard (e.g. Faithless Looting): use BOTH draw and discard categories
- IMPORTANT: "producer", "per_turn", "per_cast", etc. go INSIDE the category object, NEVER in metadata

## Examples

Rakdos Signet (mana rock, {T}: Add {B}{R}):
{
  "reasoning": "Rakdos Signet is a mana rock that taps for 1 mana. Repeatable producer.",
  "categories": [
    {"category": "ramp", "immediate": false, "producer": {"mana_amount": 1}}
  ]
}

Sol Ring ({T}: Add {C}{C}):
{
  "reasoning": "Sol Ring taps for 2 colorless mana. Repeatable producer with amount 2.",
  "categories": [
    {"category": "ramp", "immediate": false, "producer": {"mana_amount": 2}}
  ]
}

Cultivate (search for two lands, one to battlefield tapped, one to hand):
{
  "reasoning": "Cultivate puts 1 land onto the battlefield tapped. Land fetch ramp.",
  "categories": [
    {"category": "ramp", "immediate": true, "land_to_battlefield": {"count": 1, "tempo": "tapped"}}
  ]
}

Phyrexian Arena (draw a card and lose 1 life each upkeep):
{
  "reasoning": "Draws 1 card per turn. Repeatable per-turn draw. Life loss is irrelevant.",
  "categories": [
    {"category": "draw", "immediate": false, "per_turn": {"amount": 1}}
  ]
}

The Great Henge ({T}: Add {G}{G}; draw on creature ETB):
{
  "reasoning": "Taps for 2 mana (repeatable producer) and draws on each creature cast.",
  "categories": [
    {"category": "ramp", "immediate": false, "producer": {"mana_amount": 2}},
    {"category": "draw", "immediate": false, "per_cast": {"amount": 1, "trigger": "creature"}}
  ]
}

Path to Exile (exile target creature, its controller searches for a land):
{
  "reasoning": "Removal spell. The land goes to the opponent, not us. No simulatable effect.",
  "categories": []
}
"""

BATCH_SYSTEM_PROMPT = """\
You are a Magic: The Gathering card analyst for a mana curve simulator.
Your job is to label multiple cards at once with machine-interpretable categories.

## How to respond
For each card, write a brief "reasoning" analyzing the card, then fill in "categories".
Each category is a SELF-CONTAINED object — all variant fields go INSIDE it.

## Category Types

### ramp
Repeatable mana producer (mana rocks, signets, dorks):
  {"category": "ramp", "immediate": false, "producer": {"mana_amount": 1}}
Immediate mana (rituals, one-shot):
  {"category": "ramp", "immediate": true, "producer": {"mana_amount": 3}}
Land fetch (Cultivate, Rampant Growth):
  {"category": "ramp", "immediate": true, "land_to_battlefield": {"count": 1, "tempo": "tapped"}}
Cost reducer (Goblin Warchief):
  {"category": "ramp", "immediate": false, "reducer": {"spell_type": "creature", "amount": 1}}
  Valid spell_type: "creature", "enchantment", "nonpermanent", "permanent", "spell"

### draw
Immediate (Harmonize):
  {"category": "draw", "immediate": true, "amount": 3}
Per-turn (Phyrexian Arena):
  {"category": "draw", "immediate": false, "per_turn": {"amount": 1}}
Per-cast (Beast Whisperer):
  {"category": "draw", "immediate": false, "per_cast": {"amount": 1, "trigger": "creature"}}
  Valid trigger: "spell", "creature", "enchantment", "land", "artifact", "nonpermanent"

### discard
  {"category": "discard", "amount": 2}

### land
  {"category": "land", "tapped": true}
  (only for lands that enter tapped; normal lands need no entry)

## Rules
- Cards that don't fit any category: {"categories": []}
- Draw+discard (e.g. Faithless Looting): use BOTH draw and discard categories
- IMPORTANT: "producer", "per_turn", "per_cast", etc. go INSIDE the category object, NEVER in metadata

## Output Schema
Return a JSON object keyed by card name. Each entry has "reasoning" and "categories":
{
  "Sol Ring": {
    "reasoning": "Sol Ring taps for 2 colorless mana. Repeatable producer with amount 2.",
    "categories": [
      {"category": "ramp", "immediate": false, "producer": {"mana_amount": 2}}
    ]
  },
  "Lightning Bolt": {
    "reasoning": "Damage only. No mana, draw, or discard effect for the simulator.",
    "categories": []
  }
}

You MUST include an entry for every card listed in the prompt, using the exact card name.
"""

# Expanded category item schema — Ollama uses this for constrained decoding,
# so all possible variant fields must be declared or the model cannot output them.
_CATEGORY_ITEM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "category": {"type": "string"},
        "immediate": {"type": "boolean"},
        # ramp variants
        "producer": {
            "type": "object",
            "properties": {
                "mana_amount": {"type": "integer"},
            },
        },
        "land_to_battlefield": {
            "type": "object",
            "properties": {
                "count": {"type": "integer"},
                "tempo": {"type": "string"},
            },
        },
        "reducer": {
            "type": "object",
            "properties": {
                "spell_type": {"type": "string"},
                "amount": {"type": "integer"},
            },
        },
        # draw variants
        "amount": {"type": "integer"},
        "per_turn": {
            "type": "object",
            "properties": {
                "amount": {"type": "integer"},
            },
        },
        "per_cast": {
            "type": "object",
            "properties": {
                "amount": {"type": "integer"},
                "trigger": {"type": "string"},
            },
        },
        # land
        "tapped": {"type": "boolean"},
    },
    "required": ["category"],
}

_LABEL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "reasoning": {"type": "string"},
        "categories": {
            "type": "array",
            "items": _CATEGORY_ITEM_SCHEMA,
        },
        "metadata": {"type": "object"},
    },
    "required": ["reasoning", "categories"],
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
            # Normalize each card's label
            parsed = {name: _normalize_label(lbl) for name, lbl in parsed.items()}
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


def _normalize_label(raw: dict) -> dict:
    """Strip reasoning and ensure metadata defaults to {}."""
    result = {
        "categories": raw.get("categories", []),
        "metadata": raw.get("metadata", {}),
    }
    return result


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
            parsed = json.loads(content)
            return _normalize_label(parsed)
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

    skipped = 0

    def _label_and_validate(card: ScryfallCard) -> dict | None:
        """Label a single card, returning None if it fails validation."""
        try:
            label = label_card(card, model=model)
        except ValueError:
            logger.error("Failed to label %s, skipping", card.name)
            return None
        errors = validate_label(card.name, label)
        if errors:
            logger.warning("Skipping %s (validation errors): %s", card.name, errors)
            return None
        return label

    def _process_batch(batch: list[ScryfallCard]) -> dict[str, dict]:
        nonlocal skipped
        batch_results: dict[str, dict] = {}

        if len(batch) == 1:
            card = batch[0]
            label = _label_and_validate(card)
            if label is not None:
                batch_results[card.name] = label
            else:
                skipped += 1
            return batch_results

        # Multi-card batch
        try:
            batch_labels = label_card_batch(batch, model=model)
        except ValueError:
            # Batch failed — fall back to single-card for each
            logger.warning("Batch failed, falling back to single-card labeling")
            for card in batch:
                label = _label_and_validate(card)
                if label is not None:
                    batch_results[card.name] = label
                else:
                    skipped += 1
            return batch_results

        # Validate each card in batch results
        for card in batch:
            if card.name in batch_labels:
                label = batch_labels[card.name]
                errors = validate_label(card.name, label)
                if errors:
                    logger.warning(
                        "Skipping %s (validation errors): %s", card.name, errors,
                    )
                    skipped += 1
                else:
                    batch_results[card.name] = label
            else:
                # Card missing from batch — fall back to single
                logger.warning("%s missing from batch, trying single-card", card.name)
                label = _label_and_validate(card)
                if label is not None:
                    batch_results[card.name] = label
                else:
                    skipped += 1

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

    if skipped:
        logger.warning(
            "%d cards skipped due to errors (re-run to retry them)", skipped,
        )

    return results
