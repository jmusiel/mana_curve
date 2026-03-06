"""Resolve card names into full card dicts via the Scryfall API."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

import requests

from . import rate_limiter

_COLLECTION_URL = "https://api.scryfall.com/cards/collection"
_BATCH_SIZE = 75  # Scryfall max per request


def _parse_type_line(type_line: str) -> tuple[list[str], list[str], list[str]]:
    """Parse a Scryfall type_line into (super_types, types, sub_types)."""
    known_supers = {"Basic", "Legendary", "Snow", "World", "Ongoing"}
    known_types = {
        "Land", "Creature", "Artifact", "Enchantment", "Instant",
        "Sorcery", "Planeswalker", "Battle", "Kindred", "Tribal",
    }

    # Split on " // " for DFCs, only use front face for type classification
    front = type_line.split(" // ")[0]

    # Split on em-dash to separate types from subtypes
    if "\u2014" in front:
        main_part, sub_part = front.split("\u2014", 1)
        sub_types = [s.strip() for s in sub_part.split() if s.strip()]
    elif "-" in front and " - " in front:
        main_part, sub_part = front.split(" - ", 1)
        sub_types = [s.strip() for s in sub_part.split() if s.strip()]
    else:
        main_part = front
        sub_types = []

    words = [w.strip() for w in main_part.split() if w.strip()]
    super_types = [w for w in words if w in known_supers]
    types = [w for w in words if w in known_types]

    return super_types, types, sub_types


def _scryfall_to_card_dict(
    raw: dict,
    quantity: int,
    is_commander: bool,
    user_category: str | None = None,
) -> Dict[str, Any]:
    """Convert a Scryfall card JSON object to our internal card dict format."""
    super_types, types, sub_types = _parse_type_line(raw.get("type_line", ""))

    card_dict: Dict[str, Any] = {
        "name": raw["name"],
        "quantity": quantity,
        "oracle_cmc": raw.get("cmc", 0),
        "cmc": raw.get("cmc", 0),
        "cost": raw.get("mana_cost", ""),
        "text": raw.get("oracle_text", ""),
        "sub_types": sub_types,
        "super_types": super_types,
        "types": types,
        "identity": raw.get("color_identity", []),
        "default_category": None,
        "user_category": user_category or (_infer_category(types)),
        "tag": None,
        "commander": is_commander,
    }

    # Handle double-faced / modal cards
    faces = raw.get("card_faces")
    if faces:
        cost_parts = []
        text_parts = []
        all_sub = []
        all_super = []
        all_types = []
        for face in faces:
            cost_parts.append(face.get("mana_cost", ""))
            text_parts.append(face.get("oracle_text", ""))
            ft = face.get("type_line", "")
            fs, ft_types, fsub = _parse_type_line(ft)
            all_super.extend(fs)
            all_types.extend(ft_types)
            all_sub.extend(fsub)
        card_dict["cost"] = "//".join(cost_parts)
        card_dict["text"] = "//".join(text_parts)
        card_dict["sub_types"] = all_sub
        card_dict["super_types"] = all_super
        card_dict["types"] = all_types

    return card_dict


def _infer_category(types: list[str]) -> str:
    """Infer a user_category from card types."""
    if "Land" in types:
        return "Land"
    if "Creature" in types:
        return "Creature"
    if "Planeswalker" in types:
        return "Planeswalker"
    if "Instant" in types or "Sorcery" in types:
        return "Instant/Sorcery"
    if "Artifact" in types:
        return "Artifact"
    if "Enchantment" in types:
        return "Enchantment"
    return "Other"


def resolve_cards(
    entries: List[Tuple[int, str, bool]],
) -> List[Dict[str, Any]]:
    """Resolve a list of (quantity, card_name, is_commander) into card dicts.

    Uses Scryfall's ``/cards/collection`` endpoint in batches of 75.
    Respects rate limits via the shared rate_limiter.
    """
    if not entries:
        return []

    # Build lookup: name -> (quantity, is_commander)
    # Also track front_face_name -> original_name for DFC matching.
    lookup: dict[str, tuple[int, bool]] = {}
    front_to_original: dict[str, str] = {}
    for qty, name, is_cmdr in entries:
        if name in lookup:
            prev_qty, prev_cmdr = lookup[name]
            lookup[name] = (prev_qty + qty, prev_cmdr or is_cmdr)
        else:
            lookup[name] = (qty, is_cmdr)
        # Map front face name back to the original entry name
        front = name.split(" // ")[0].strip()
        if front != name:
            front_to_original[front] = name

    # Build identifier list for Scryfall using front face names only
    # (Scryfall's /cards/collection does not accept "A // B" format)
    identifiers = [{"name": name.split(" // ")[0].strip()} for name in lookup]

    cards: List[Dict[str, Any]] = []
    not_found: List[str] = []

    for i in range(0, len(identifiers), _BATCH_SIZE):
        batch = identifiers[i : i + _BATCH_SIZE]
        rate_limiter.wait("scryfall")

        resp = requests.post(
            _COLLECTION_URL,
            json={"identifiers": batch},
            headers={"Accept": "application/json"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        for raw in data.get("data", []):
            scryfall_name = raw["name"]
            # Match back to the original lookup key: try full name first,
            # then front face, then the reverse mapping from front face.
            front = scryfall_name.split(" // ")[0].strip()
            if scryfall_name in lookup:
                orig_name = scryfall_name
            elif front in lookup:
                orig_name = front
            elif front in front_to_original:
                orig_name = front_to_original[front]
            else:
                orig_name = scryfall_name
            qty, is_cmdr = lookup.get(orig_name, (1, False))
            card_dict = _scryfall_to_card_dict(raw, 1, is_cmdr)
            # Expand quantity into individual card entries (matches archidekt behavior)
            for _ in range(qty):
                cards.append(dict(card_dict))

        for nf in data.get("not_found", []):
            not_found.append(nf.get("name", str(nf)))

    if not_found:
        raise CardResolutionError(
            f"Could not find {len(not_found)} card(s): {', '.join(not_found[:10])}"
        )

    return cards


class CardResolutionError(Exception):
    """Raised when one or more cards cannot be found via Scryfall."""
