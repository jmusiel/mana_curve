"""Built-in metric functions."""

from __future__ import annotations

from typing import List

import numpy as np

from .collector import GameRecord


def mean_mana_spent(records: List[GameRecord]) -> float:
    return float(np.mean([r.total_mana_spent for r in records]))


def mean_lands_played(records: List[GameRecord]) -> float:
    return float(np.mean([r.lands_played for r in records]))


def mean_mulligans(records: List[GameRecord]) -> float:
    return float(np.mean([r.mulligans for r in records]))


def mean_draws(records: List[GameRecord]) -> float:
    return float(np.mean([r.draws for r in records]))


def mean_bad_turns(records: List[GameRecord]) -> float:
    return float(np.mean([r.bad_turns for r in records]))


def mean_mid_turns(records: List[GameRecord]) -> float:
    return float(np.mean([r.mid_turns for r in records]))


def consistency(records: List[GameRecord], threshold: float = 0.25) -> float:
    """Consistency metric: how uniformly is mana distributed across games."""
    import bisect

    mana_list = [r.total_mana_spent for r in records]
    total = float(np.sum(mana_list))
    sorted_mana = sorted(mana_list)
    cumulative = np.cumsum(sorted_mana)
    idx = bisect.bisect_left(cumulative, total * threshold)
    frac = idx / len(mana_list)
    return (1 - frac) / (1 - threshold)
