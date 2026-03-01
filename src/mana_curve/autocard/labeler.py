"""LLM-based card labeling using Ollama."""

from __future__ import annotations

import json
import logging
from dataclasses import fields as dc_fields
from pathlib import Path
from typing import Any

from mana_curve.effects.json_loader import METADATA_FIELDS, TYPE_MAP, VALID_SLOTS

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


SYSTEM_PROMPT = f"""\
You are a Magic: The Gathering card analyst for a mana curve simulator.
Your job is to label cards with machine-interpretable effects.

## Effect Types and Parameters
{_build_effect_docs()}

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

# JSON schema for structured output (ollama format parameter).
JSON_SCHEMA: dict[str, Any] = {
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
) -> dict[str, dict]:
    """Label multiple cards with LLM, with incremental saving and resume support.

    Args:
        cards: List of cards to label.
        model: Ollama model name.
        output_path: Path to save results (default: data/labeled_cards.json).
        resume: If True, skip cards already in the output file.
        concurrency: Number of parallel Ollama requests.

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

    def _process(card: ScryfallCard) -> tuple[str, dict | None]:
        try:
            label = label_card(card, model=model)
        except ValueError:
            logger.error("Failed to label %s, skipping", card.name)
            return card.name, None

        errors = validate_label(card.name, label)
        if errors:
            logger.warning("Validation errors for %s: %s", card.name, errors)

        return card.name, label

    with tqdm(total=len(to_label), desc="Labeling cards") as pbar:
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = {
                pool.submit(_process, card): card for card in to_label
            }
            for future in as_completed(futures):
                name, label = future.result()
                if label is not None:
                    with lock:
                        results[name] = label
                        save_labeled(results, output_path)
                pbar.update(1)

    return results
