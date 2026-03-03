#!/usr/bin/env python3
"""Debug script to test LLM labeling prompts and see raw output.

Sends the exact same prompts/schemas as the real labeler and prints everything:
system prompt, user prompt, JSON schema, raw LLM response, and validation results.

Usage:
    # Single card by name (looks up in top_cards.json)
    .venv/bin/python scripts/debug_labeler.py "Sol Ring"

    # Multiple cards (batch mode)
    .venv/bin/python scripts/debug_labeler.py "Sol Ring" "Arcane Signet" "Night's Whisper"

    # Custom model
    .venv/bin/python scripts/debug_labeler.py --model llama3:8b "Sol Ring"

    # Single-card mode even with multiple cards (one call per card)
    .venv/bin/python scripts/debug_labeler.py --single "Sol Ring" "Arcane Signet"

    # Show system prompt without calling model
    .venv/bin/python scripts/debug_labeler.py --show-prompt
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Add src to path so imports work
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from auto_goldfish.autocard.labeler import (
    BATCH_SYSTEM_PROMPT,
    JSON_SCHEMA,
    SYSTEM_PROMPT,
    batch_json_schema,
    build_batch_prompt,
    build_card_prompt,
)
from auto_goldfish.autocard.scryfall import load_cards
from auto_goldfish.autocard.validator import validate_label


SEPARATOR = "=" * 80

# Expanded schema that declares all variant fields so Ollama's constrained
# decoding allows the model to output them.
_EXPANDED_CATEGORY_ITEM = {
    "type": "object",
    "properties": {
        "category": {"type": "string"},
        "immediate": {"type": "boolean"},
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
        "tapped": {"type": "boolean"},
    },
    "required": ["category"],
}

EXPANDED_LABEL_SCHEMA = {
    "type": "object",
    "properties": {
        "reasoning": {"type": "string"},
        "categories": {
            "type": "array",
            "items": _EXPANDED_CATEGORY_ITEM,
        },
        "metadata": {"type": "object"},
    },
    "required": ["reasoning", "categories"],
}


def expanded_batch_schema(card_names: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {name: EXPANDED_LABEL_SCHEMA for name in card_names},
        "required": card_names,
    }


def find_card(name: str):
    """Look up a card by name from top_cards.json."""
    cards = load_cards()
    for card in cards:
        if card.name.lower() == name.lower():
            return card
    # Partial match fallback
    matches = [c for c in cards if name.lower() in c.name.lower()]
    if len(matches) == 1:
        return matches[0]
    if matches:
        print(f"Ambiguous name {name!r}, matches: {[c.name for c in matches[:10]]}")
        return matches[0]
    print(f"Card {name!r} not found in top_cards.json")
    sys.exit(1)


def call_ollama(messages, schema, model):
    """Call ollama and return the raw response."""
    import ollama

    response = ollama.chat(
        model=model,
        messages=messages,
        format=schema,
        options={"temperature": 0},
    )
    return response


def debug_single(card, model, use_expanded_schema=False):
    """Send a single-card prompt and print everything."""
    user_prompt = build_card_prompt(card)
    schema = EXPANDED_LABEL_SCHEMA if use_expanded_schema else JSON_SCHEMA
    schema_label = "EXPANDED" if use_expanded_schema else "ORIGINAL"

    print(SEPARATOR)
    print("MODE: single-card")
    print(f"MODEL: {model}")
    print(f"CARD: {card.name}")
    print(f"SCHEMA: {schema_label}")
    print(SEPARATOR)

    print("\n--- SYSTEM PROMPT ---")
    print(SYSTEM_PROMPT)

    print("\n--- USER PROMPT ---")
    print(user_prompt)

    print("\n--- JSON SCHEMA (format parameter) ---")
    print(json.dumps(schema, indent=2))

    print(f"\n--- CALLING OLLAMA ({model}) ---")
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    response = call_ollama(messages, schema, model)
    raw_content = response["message"]["content"]

    print("\n--- RAW RESPONSE ---")
    print(raw_content)

    print("\n--- PARSED ---")
    try:
        parsed = json.loads(raw_content)
        print(json.dumps(parsed, indent=2))

        # Show reasoning separately
        if "reasoning" in parsed:
            print(f"\n--- REASONING ---")
            print(parsed["reasoning"])

        # Validate
        normalized = {
            "categories": parsed.get("categories", []),
            "metadata": parsed.get("metadata", {}),
        }
        print(f"\n--- NORMALIZED LABEL ---")
        print(json.dumps(normalized, indent=2))

        errors = validate_label(card.name, normalized)
        if errors:
            print(f"\n--- VALIDATION ERRORS ---")
            for e in errors:
                print(f"  FAIL: {e}")
        else:
            print(f"\n--- VALIDATION: PASSED ---")

    except json.JSONDecodeError as exc:
        print(f"\n--- JSON PARSE ERROR: {exc} ---")

    print(SEPARATOR)


def debug_batch(cards, model, use_expanded_schema=False):
    """Send a batch prompt and print everything."""
    user_prompt = build_batch_prompt(cards)
    card_names = [c.name for c in cards]
    schema = expanded_batch_schema(card_names) if use_expanded_schema else batch_json_schema(card_names)
    schema_label = "EXPANDED" if use_expanded_schema else "ORIGINAL"

    print(SEPARATOR)
    print("MODE: batch")
    print(f"MODEL: {model}")
    print(f"CARDS: {card_names}")
    print(f"SCHEMA: {schema_label}")
    print(SEPARATOR)

    print("\n--- BATCH SYSTEM PROMPT ---")
    print(BATCH_SYSTEM_PROMPT)

    print("\n--- USER PROMPT ---")
    print(user_prompt)

    print("\n--- JSON SCHEMA (format parameter) ---")
    print(json.dumps(schema, indent=2))

    print(f"\n--- CALLING OLLAMA ({model}) ---")
    messages = [
        {"role": "system", "content": BATCH_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    response = call_ollama(messages, schema, model)
    raw_content = response["message"]["content"]

    print("\n--- RAW RESPONSE ---")
    print(raw_content)

    print("\n--- PARSED ---")
    try:
        parsed = json.loads(raw_content)
        print(json.dumps(parsed, indent=2))

        # Validate each card
        for name in card_names:
            print(f"\n--- {name} ---")
            if name not in parsed:
                print("  MISSING from response!")
                continue

            entry = parsed[name]
            if "reasoning" in entry:
                print(f"  Reasoning: {entry['reasoning']}")

            normalized = {
                "categories": entry.get("categories", []),
                "metadata": entry.get("metadata", {}),
            }
            print(f"  Label: {json.dumps(normalized, indent=4)}")

            errors = validate_label(name, normalized)
            if errors:
                for e in errors:
                    print(f"  FAIL: {e}")
            else:
                print(f"  VALIDATION: PASSED")

    except json.JSONDecodeError as exc:
        print(f"\n--- JSON PARSE ERROR: {exc} ---")

    print(SEPARATOR)


def main():
    parser = argparse.ArgumentParser(description="Debug autocard LLM labeling prompts")
    parser.add_argument("cards", nargs="*", help="Card names to test")
    parser.add_argument("--model", default="gemma3:12b", help="Ollama model (default: gemma3:12b)")
    parser.add_argument("--single", action="store_true", help="Force single-card mode even with multiple cards")
    parser.add_argument("--expanded-schema", action="store_true", help="Use expanded JSON schema with all variant fields")
    parser.add_argument("--show-prompt", action="store_true", help="Print system prompt and exit (no model call)")
    args = parser.parse_args()

    if args.show_prompt:
        print("--- SINGLE-CARD SYSTEM PROMPT ---")
        print(SYSTEM_PROMPT)
        print(f"\n--- SINGLE-CARD JSON SCHEMA (original) ---")
        print(json.dumps(JSON_SCHEMA, indent=2))
        print(f"\n--- SINGLE-CARD JSON SCHEMA (expanded) ---")
        print(json.dumps(EXPANDED_LABEL_SCHEMA, indent=2))
        print(f"\n{'=' * 40}\n")
        print("--- BATCH SYSTEM PROMPT ---")
        print(BATCH_SYSTEM_PROMPT)
        return

    if not args.cards:
        parser.error("Provide card names or use --show-prompt")

    cards = [find_card(name) for name in args.cards]

    if len(cards) == 1 or args.single:
        for card in cards:
            debug_single(card, args.model, use_expanded_schema=args.expanded_schema)
    else:
        debug_batch(cards, args.model, use_expanded_schema=args.expanded_schema)


if __name__ == "__main__":
    main()
