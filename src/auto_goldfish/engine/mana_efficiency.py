"""Mana efficiency modes for the card play algorithm.

Controls how cards are selected from the playable set each turn:
- greedy: Play highest-priority affordable card (current default)
- mana_efficient: Maximize total mana spent per turn (knapsack)
- spell_count: Maximize number of spells cast per turn
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Tuple

if TYPE_CHECKING:
    from auto_goldfish.models.card import Card
    from auto_goldfish.models.game_state import GameState

VALID_MANA_EFFICIENCY_MODES = ("greedy", "mana_efficient", "spell_count")


def select_cards_to_play(
    mode: str,
    playables: list[Card],
    available_mana: int,
    state: GameState,
) -> list[Card]:
    """Select which cards to play from the playable set.

    Returns a list of cards to play in order (first element played first).
    The caller is responsible for sorting *playables* by priority beforehand.
    """
    if mode == "greedy":
        return _greedy_select(playables, available_mana, state)
    elif mode == "mana_efficient":
        return _knapsack_select(playables, available_mana, state, maximize="mana")
    elif mode == "spell_count":
        return _knapsack_select(playables, available_mana, state, maximize="count")
    else:
        raise ValueError(
            f"Invalid mana_efficiency: {mode!r}. "
            f"Must be one of {VALID_MANA_EFFICIENCY_MODES}"
        )


def _greedy_select(
    playables: list[Card],
    available_mana: int,
    state: GameState,
) -> list[Card]:
    """Original greedy algorithm: iterate reversed, play first affordable."""
    selected = []
    mana_left = available_mana
    for card in reversed(playables):
        cost = card.get_current_cost(state)
        if cost <= mana_left:
            selected.append(card)
            mana_left -= cost
    return selected


def _knapsack_select(
    playables: list[Card],
    available_mana: int,
    state: GameState,
    maximize: str,
) -> list[Card]:
    """Knapsack selection to maximize mana spent or spell count.

    With typical hand sizes (<10 playable cards) and mana values (<20),
    the DP table is tiny and runs in microseconds.
    """
    n = len(playables)
    if n == 0:
        return []

    capacity = available_mana
    costs = [card.get_current_cost(state) for card in playables]

    if maximize == "mana":
        values = costs  # value = cost (maximize mana spent)
    else:
        values = [1] * n  # value = 1 per card (maximize count)

    # DP: dp[w] = best value achievable with capacity w
    dp = [0] * (capacity + 1)
    # Track which items are in the solution
    chosen: list[list[bool]] = [[False] * (capacity + 1) for _ in range(n)]

    for i in range(n):
        cost_i = costs[i]
        val_i = values[i]
        # Iterate backwards to avoid using an item twice (0-1 knapsack)
        for w in range(capacity, cost_i - 1, -1):
            new_val = dp[w - cost_i] + val_i
            if new_val > dp[w]:
                dp[w] = new_val
                chosen[i][w] = True

    # Backtrack to find selected items
    selected_indices = []
    w = capacity
    for i in range(n - 1, -1, -1):
        if chosen[i][w]:
            selected_indices.append(i)
            w -= costs[i]

    # Return in priority order (reversed playables order = highest priority first)
    selected_indices.sort(reverse=True)
    return [playables[i] for i in selected_indices]
