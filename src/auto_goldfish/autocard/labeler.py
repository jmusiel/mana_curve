"""LLM-based card labeling using Ollama."""

from __future__ import annotations

import json
import logging
from dataclasses import fields as dc_fields
from pathlib import Path
from typing import Any

from auto_goldfish.effects.json_loader import METADATA_FIELDS, TYPE_MAP, VALID_SLOTS

from .schemas import ScryfallCard
from .validator import validate_label

logger = logging.getLogger(__name__)

_DEFAULT_LABELED_PATH = Path(__file__).parent / "data" / "labeled_cards.json"


def _build_effect_docs() -> str:
    """Build documentation of all effect types and their params."""
    lines = []
    for type_name, cls in TYPE_MAP.items():
        params = {f.name: f.type for f in dc_fields(cls)}
        if params:
            param_str = ", ".join(f"{k}: {v}" for k, v in params.items())
            lines.append(f"  - {type_name}: params({param_str})")
        else:
            lines.append(f"  - {type_name}: no params")
    return "\n".join(lines)


_EFFECT_DOCS = _build_effect_docs()

SYSTEM_PROMPT = f"""\
You are a Magic: The Gathering card analyst for a mana curve simulator.
Your job is to label cards with machine-interpretable effects.

## Effect Types and Parameters
{_EFFECT_DOCS}

## Valid Slots
Each effect must be assigned to exactly one slot:
  - on_play: triggers once when the card is played
  - per_turn: triggers at the start of each turn after the card is in play
  - cast_trigger: triggers when another spell is cast while this card is in play
  - mana_function: provides a dynamic mana ability evaluated each turn

## Metadata Fields (all optional)
  - priority (int): play priority (0 = normal, 2 = high). Use 2 for scaling effects.
  - ramp (bool): true if this card produces or increases mana
  - is_land_tutor (bool): true if this card searches for land cards
  - tapped (bool): true if this card enters tapped or has a significant tempo cost
  - extra_types (list[str]): additional card types for simulation, e.g. ["land", "artifact"]
  - override_cmc (int): override the mana cost for simulation purposes

## Output Schema
Return a JSON object with exactly two keys:
{{
  "effects": [
    {{"type": "<effect_type>", "slot": "<slot>", "params": {{<key>: <value>}}}}
  ],
  "metadata": {{<key>: <value>}}
}}

## Important Rules
- Only label effects that the simulator can model (the types listed above)
- Cards that don't fit any effect type should get empty effects: {{"effects": [], "metadata": {{}}}}
- Mana rocks/dorks/ramp spells that add 1 mana: produce_mana amount=1, slot=on_play, ramp=true
- Mana rocks that add 2 mana: produce_mana amount=2 (e.g. Sol Ring)
- Cost reducers: use reduce_cost with the appropriate category param
- Card draw on ETB: draw_cards with amount, slot=on_play
- Recurring draw: per_turn_draw, slot=per_turn
- Draw on cast trigger: per_cast_draw with creature/spell/etc category, slot=cast_trigger
- Scaling mana (gains mana over time): scaling_mana, slot=per_turn, priority=2

## Examples

### Sol Ring
Input: name="Sol Ring", mana_cost="{{1}}", type_line="Artifact", oracle_text="{{T}}: Add {{C}}{{C}}."
Output: {{"effects": [{{"type": "produce_mana", "slot": "on_play", "params": {{"amount": 2}}}}], "metadata": {{"ramp": true}}}}

### Phyrexian Arena
Input: name="Phyrexian Arena", mana_cost="{{1}}{{B}}{{B}}", type_line="Enchantment", oracle_text="At the beginning of your upkeep, you draw a card and you lose 1 life."
Output: {{"effects": [{{"type": "per_turn_draw", "slot": "per_turn", "params": {{"amount": 1}}}}], "metadata": {{}}}}

### The Great Henge
Input: name="The Great Henge", mana_cost="{{7}}{{G}}{{G}}", type_line="Legendary Artifact", oracle_text="This spell costs {{X}} less to cast, where X is the greatest power among creatures you control. {{T}}: Add {{G}}{{G}}. You gain 2 life. Whenever a nontoken creature enters the battlefield under your control, put a +1/+1 counter on it and draw a card."
Output: {{"effects": [{{"type": "produce_mana", "slot": "on_play", "params": {{"amount": 2}}}}, {{"type": "per_cast_draw", "slot": "cast_trigger", "params": {{"creature": 1}}}}], "metadata": {{"ramp": true}}}}

### Lightning Bolt (no simulatable effect)
Input: name="Lightning Bolt", mana_cost="{{R}}", type_line="Instant", oracle_text="Lightning Bolt deals 3 damage to any target."
Output: {{"effects": [], "metadata": {{}}}}
"""

BATCH_SYSTEM_PROMPT = f"""\
You are a Magic: The Gathering card analyst for a mana curve simulator.
Your job is to label multiple cards at once with machine-interpretable effects.

## Effect Types and Parameters
{_EFFECT_DOCS}

## Valid Slots
Each effect must be assigned to exactly one slot:
  - on_play: triggers once when the card is played
  - per_turn: triggers at the start of each turn after the card is in play
  - cast_trigger: triggers when another spell is cast while this card is in play
  - mana_function: provides a dynamic mana ability evaluated each turn

## Metadata Fields (all optional)
  - priority (int): play priority (0 = normal, 2 = high). Use 2 for scaling effects.
  - ramp (bool): true if this card produces or increases mana
  - is_land_tutor (bool): true if this card searches for land cards
  - tapped (bool): true if this card enters tapped or has a significant tempo cost
  - extra_types (list[str]): additional card types for simulation, e.g. ["land", "artifact"]
  - override_cmc (int): override the mana cost for simulation purposes

## Important Rules
- Only label effects that the simulator can model (the types listed above)
- Cards that don't fit any effect type should get empty effects: {{"effects": [], "metadata": {{}}}}
- Mana rocks/dorks/ramp spells that add 1 mana: produce_mana amount=1, slot=on_play, ramp=true
- Mana rocks that add 2 mana: produce_mana amount=2 (e.g. Sol Ring)
- Cost reducers: use reduce_cost with the appropriate category param
- Card draw on ETB: draw_cards with amount, slot=on_play
- Recurring draw: per_turn_draw, slot=per_turn
- Draw on cast trigger: per_cast_draw with creature/spell/etc category, slot=cast_trigger
- Scaling mana (gains mana over time): scaling_mana, slot=per_turn, priority=2

## Output Schema
Return a JSON object keyed by card name. Each value has "effects" and "metadata":
{{
  "Card Name": {{
    "effects": [{{"type": "<type>", "slot": "<slot>", "params": {{...}}}}],
    "metadata": {{...}}
  }},
  ...
}}

You MUST include an entry for every card listed in the prompt, using the exact card name.
"""

_LABEL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "effects": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string"},
                    "slot": {"type": "string"},
                    "params": {"type": "object"},
                },
                "required": ["type", "slot", "params"],
            },
        },
        "metadata": {"type": "object"},
    },
    "required": ["effects", "metadata"],
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

    Returns the parsed label dict with 'effects' and 'metadata' keys.
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
