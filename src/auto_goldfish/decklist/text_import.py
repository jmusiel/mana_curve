"""Parse pasted decklist text into structured card entries."""

from __future__ import annotations

import re
from typing import List, Tuple

# Matches lines like "1 Sol Ring", "1x Sol Ring", "2X Lightning Bolt", or just "Sol Ring"
_LINE_RE = re.compile(
    r"^\s*(?:(\d+)\s*[xX]?\s+)?(.+?)\s*(?:\*CMDR\*)?$"
)

# Section headers like "// Commander", "// Lands", "//Sideboard"
_SECTION_RE = re.compile(r"^\s*//\s*(.*?)\s*$")

_COMMANDER_SECTIONS = {"commander", "commanders", "command zone"}


def parse_decklist(text: str) -> List[Tuple[int, str, bool]]:
    """Parse decklist text into (quantity, card_name, is_commander) tuples.

    Supports common formats:
    - ``1 Sol Ring`` or ``1x Sol Ring``
    - ``Sol Ring`` (defaults to quantity 1)
    - ``Sol Ring *CMDR*`` (marks as commander)
    - Lines after ``// Commander`` section header are commanders
    - Blank lines and ``//`` headers act as section separators
    """
    results: List[Tuple[int, str, bool]] = []
    current_section = ""

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        section_match = _SECTION_RE.match(line)
        if section_match:
            current_section = section_match.group(1).lower()
            continue

        match = _LINE_RE.match(line)
        if not match:
            continue

        qty_str, name = match.group(1), match.group(2)
        qty = int(qty_str) if qty_str else 1
        name = name.strip()

        if not name:
            continue

        is_cmdr = (
            current_section in _COMMANDER_SECTIONS
            or "*CMDR*" in line
        )
        # Strip *CMDR* from the name if present
        name = name.replace("*CMDR*", "").strip()

        results.append((qty, name, is_cmdr))

    return results
