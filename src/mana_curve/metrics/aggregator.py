"""Percentile bucketing and aggregation for game records."""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List

import numpy as np

from .collector import GameRecord


def aggregate_bucket(records: List[GameRecord]) -> Dict[str, Any]:
    """Compute summary stats for a bucket of game records."""
    if not records:
        return {}

    result: Dict[str, Any] = {
        "count": len(records),
        "mana": float(np.mean([r.total_mana_spent for r in records])),
        "lands": float(np.mean([r.lands_played for r in records])),
        "mulls": float(np.mean([r.mulligans for r in records])),
        "draws": float(np.mean([r.draws for r in records])),
        "bad_turns": float(np.mean([r.bad_turns for r in records])),
        "mid_turns": float(np.mean([r.mid_turns for r in records])),
        "starting_hand_land_count": float(np.mean([r.starting_hand_land_count for r in records])),
    }

    # Most common cards
    all_played = []
    all_starting = []
    for r in records:
        all_played.extend(r.cards_played)
        all_starting.extend(r.starting_hand)

    result["top_played_cards"] = Counter(all_played).most_common(10)
    result["top_starting_hand"] = Counter(all_starting).most_common(10)

    return result
