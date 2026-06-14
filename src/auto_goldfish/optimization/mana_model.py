"""Hypergeometric mana model -- closed-form land count recommendations.

Pure math functions using ``math.comb`` (no scipy needed).
Answers "how many lands should I run?" in microseconds.
"""

from __future__ import annotations

from math import comb
from typing import Any, Dict, List, Optional, Tuple

# Mulligan keep range: hands with 2-5 lands are kept, others mulliganed.
DEFAULT_KEEP_RANGE: Tuple[int, int] = (2, 5)

# Land-count search bounds for the optimization sweep.
DEFAULT_SEARCH_RANGE: Tuple[int, int] = (25, 45)

# Fraction of draw spells assumed to fire by mid-game (conservative).
# Used by adjusted_expected_mana (the expected-mana tables / what-if calculator).
DRAW_EARLY_FRACTION = 0.5

# --- Calibrated land-count recommendation -----------------------------------
#
# The recommendation is a closed-form formula fit to *simulator-optimal* land
# counts across ~100 real commander decks (goldfishing land sweeps at a 14-turn
# horizon, optimizing value-mana spent). See ADR-0003 and scripts/fit_land_model.py.
#
# The fit is ANCHORED to consensus rather than trusting the simulator's absolute
# level: a balanced avg-CMC-3.0 deck is pinned to 37 lands. The simulator is used
# only for the *relative* slopes -- how the optimum shifts with curve / ramp /
# draw -- because the goldfishing optimum itself is noisy (±~3 lands) and
# horizon-sensitive (short games want more lands, long games fewer). Average mana
# value is the dominant, robust driver; ramp and draw apply small reductions.
REC_ANCHOR_LANDS = 37.0    # consensus land count for the anchor deck
REC_ANCHOR_CMC = 3.0       # average mana value of the anchor deck
REC_LANDS_PER_CMC = 1.2    # +lands per +1 average mana value (sim-derived, dominant)
REC_LANDS_PER_RAMP = -0.10  # small reduction per ramp piece (sim-derived, gentle)
REC_LANDS_PER_DRAW = -0.05  # small reduction per draw piece (conventional; sim signal
                            # was unreliable due to floor-censoring of draw-heavy decks)
REC_CLAMP: Tuple[int, int] = (30, 43)  # sane commander land-count band


# ---------------------------------------------------------------------------
# Core hypergeometric distribution
# ---------------------------------------------------------------------------

def hypergeometric_pmf(k: int, N: int, K: int, n: int) -> float:
    """P(X = k): probability of drawing exactly *k* successes.

    Parameters
    ----------
    k : int  -- number of observed successes
    N : int  -- population size (deck size)
    K : int  -- number of success states in population (e.g. lands)
    n : int  -- number of draws (cards seen)
    """
    if k < max(0, n - (N - K)) or k > min(n, K):
        return 0.0
    return comb(K, k) * comb(N - K, n - k) / comb(N, n)


def hypergeometric_cdf(k: int, N: int, K: int, n: int) -> float:
    """P(X <= k): cumulative probability of at most *k* successes."""
    return sum(hypergeometric_pmf(i, N, K, n) for i in range(k + 1))


def prob_at_least(k: int, N: int, K: int, n: int) -> float:
    """P(X >= k) = 1 - CDF(k - 1)."""
    if k <= 0:
        return 1.0
    return 1.0 - hypergeometric_cdf(k - 1, N, K, n)


# ---------------------------------------------------------------------------
# Expected mana helpers
# ---------------------------------------------------------------------------

def expected_mana_on_turn(turn: int, N: int, K: int) -> float:
    """Expected mana available on a given turn (land-per-turn cap).

    On turn T you've seen 7 + (T - 1) = T + 6 cards.
    You can play at most T lands, so expected mana = E[min(lands_drawn, T)].
    """
    cards_seen = 7 + turn - 1  # opening hand + draws
    if cards_seen > N:
        cards_seen = N
    total = 0.0
    for lands in range(cards_seen + 1):
        p = hypergeometric_pmf(lands, N, K, cards_seen)
        total += p * min(lands, turn)
    return total


def expected_mana_table(
    N: int, K: int, max_turn: int = 10
) -> List[Dict[str, Any]]:
    """Turn-by-turn table with expected mana, on-curve probability, and screw probability.

    Returns a list of dicts, one per turn (1..max_turn).
    """
    rows = []
    for t in range(1, max_turn + 1):
        cards_seen = min(7 + t - 1, N)
        e_mana = expected_mana_on_turn(t, N, K)
        p_on_curve = prob_at_least(t, N, K, cards_seen)
        # Screw = fewer than ceil(t/2) lands (missing half your drops)
        screw_threshold = max(1, (t + 1) // 2)
        p_screw = hypergeometric_cdf(screw_threshold - 1, N, K, cards_seen)
        rows.append({
            "turn": t,
            "cards_seen": cards_seen,
            "expected_mana": round(e_mana, 3),
            "prob_on_curve": round(p_on_curve, 4),
            "prob_screw": round(p_screw, 4),
        })
    return rows


# ---------------------------------------------------------------------------
# Mulligan model (London mulligan approximation)
# ---------------------------------------------------------------------------

def mulligan_probability(
    N: int, K: int, keep_range: Tuple[int, int] = DEFAULT_KEEP_RANGE
) -> float:
    """Probability of mulliganing a 7-card hand.

    Keeps hands with *keep_range[0]* to *keep_range[1]* lands (inclusive).
    """
    p_keep = sum(
        hypergeometric_pmf(lands, N, K, 7)
        for lands in range(keep_range[0], keep_range[1] + 1)
    )
    return 1.0 - p_keep


# ---------------------------------------------------------------------------
# Ramp and draw adjustments
# ---------------------------------------------------------------------------

def adjusted_expected_mana(
    turn: int,
    N: int,
    K: int,
    ramp_cards: int = 0,
    draw_cards: int = 0,
    avg_ramp_cmc: float = 2.0,
    avg_ramp_amount: float = 1.0,
    avg_draw_amount: float = 1.0,
) -> float:
    """Expected mana with ramp and draw effects factored in.

    Ramp model: Each ramp card adds *avg_ramp_amount* mana for turns after
    it can be cast (turn > avg_ramp_cmc). Probability of having it in hand
    is approximated as ramp_cards / (N - K) * cards_seen / N.

    Draw model: Extra draws increase effective cards seen for subsequent turns.
    """
    base_mana = expected_mana_on_turn(turn, N, K)

    # Ramp contribution
    ramp_bonus = 0.0
    if ramp_cards > 0 and turn > avg_ramp_cmc:
        cards_seen = 7 + turn - 1
        non_lands = N - K
        if non_lands > 0:
            # P(at least one ramp card in hand by the cast turn)
            ramp_cast_turn = int(avg_ramp_cmc)
            cards_at_cast = min(7 + ramp_cast_turn - 1, N)
            p_ramp_in_hand = 1.0 - hypergeometric_cdf(
                0, N, ramp_cards, cards_at_cast
            )
            # P(enough mana to cast it)
            p_castable = prob_at_least(ramp_cast_turn, N, K, cards_at_cast)
            ramp_bonus = p_ramp_in_hand * p_castable * avg_ramp_amount

    # Draw contribution: extra cards seen improve land probability
    draw_bonus = 0.0
    if draw_cards > 0 and turn > 1:
        extra_cards = draw_cards * avg_draw_amount * DRAW_EARLY_FRACTION
        augmented_seen = min(7 + turn - 1 + extra_cards, N)
        e_augmented = 0.0
        # Approximate with fractional cards_seen via interpolation
        lo = int(augmented_seen)
        hi = lo + 1
        frac = augmented_seen - lo
        e_lo = expected_mana_on_turn(turn, N, K) if lo == 7 + turn - 1 else _expected_mana_seen(turn, N, K, lo)
        e_hi = _expected_mana_seen(turn, N, K, min(hi, N))
        e_augmented = e_lo * (1 - frac) + e_hi * frac
        draw_bonus = max(0, e_augmented - base_mana)

    return base_mana + ramp_bonus + draw_bonus


def _expected_mana_seen(turn: int, N: int, K: int, cards_seen: int) -> float:
    """Expected mana given a specific number of cards seen (helper)."""
    cards_seen = min(cards_seen, N)
    total = 0.0
    for lands in range(cards_seen + 1):
        p = hypergeometric_pmf(lands, N, K, cards_seen)
        total += p * min(lands, turn)
    return total


# ---------------------------------------------------------------------------
# Partner commanders -- joint castable probability
# ---------------------------------------------------------------------------

def prob_both_partners_castable(N: int, K: int, cmc_a: int, cmc_b: int) -> float:
    """P(cast cheaper partner on its CMC turn AND second partner on its CMC turn).

    Sequential model: cast partner with cmc_a on turn cmc_a, then partner
    with cmc_b on turn cmc_b. The events are not independent (lands persist
    across turns), so this iterates over the joint distribution of land
    draws at turn A and the additional draws between turns A and B.
    """
    if cmc_a <= 0 or cmc_b <= 0:
        return 0.0
    if cmc_a > cmc_b:
        cmc_a, cmc_b = cmc_b, cmc_a

    cards_at_a = min(7 + cmc_a - 1, N)
    cards_at_b = min(7 + cmc_b - 1, N)
    extra = cards_at_b - cards_at_a

    total = 0.0
    for lands_a in range(cmc_a, min(cards_at_a, K) + 1):
        p_a = hypergeometric_pmf(lands_a, N, K, cards_at_a)
        if p_a == 0.0:
            continue
        needed = max(0, cmc_b - lands_a)
        remaining_pop = N - cards_at_a
        remaining_lands = K - lands_a
        if needed > extra or needed > remaining_lands:
            continue
        p_more = prob_at_least(needed, remaining_pop, remaining_lands, extra)
        total += p_a * p_more
    return total


# ---------------------------------------------------------------------------
# Optimal land count
# ---------------------------------------------------------------------------

def optimal_land_count(
    deck_size: int = 99,
    cmc_distribution: Optional[Dict[int, int]] = None,
    ramp_cards: int = 0,
    draw_cards: int = 0,
    commander_cmc: int = 0,
    commander_cmcs: Optional[List[int]] = None,
    search_range: Tuple[int, int] = DEFAULT_SEARCH_RANGE,
) -> Dict[str, Any]:
    """Recommend a land count from a closed-form formula fit to the simulator.

    The recommendation is ``REC_ANCHOR_LANDS`` adjusted by the deck's average
    mana value (dominant), ramp count, and draw count, clamped to ``REC_CLAMP``.
    The coefficients are fit to simulator-optimal land counts across ~100 real
    decks but anchored to consensus (avg-CMC-3.0 -> 37); see the calibration
    notes above and ADR-0003.

    Also returns a ``scores`` curve (one entry per land count in *search_range*)
    that peaks at the recommendation, for the comparison display, plus
    ``partner_castable_prob`` when 2+ partner commanders are given.

    *commander_cmc* (legacy, single int) and *commander_cmcs* (list) are
    both accepted; the list takes precedence when given.
    """
    if cmc_distribution is None:
        cmc_distribution = {}
    if commander_cmcs is None:
        commander_cmcs = [commander_cmc] if commander_cmc > 0 else []

    avg_cmc = _weighted_avg_cmc(cmc_distribution) if cmc_distribution else REC_ANCHOR_CMC

    rec_continuous = (
        REC_ANCHOR_LANDS
        + REC_LANDS_PER_CMC * (avg_cmc - REC_ANCHOR_CMC)
        + REC_LANDS_PER_RAMP * ramp_cards
        + REC_LANDS_PER_DRAW * draw_cards
    )
    lo, hi = REC_CLAMP
    rec_continuous = min(float(hi), max(float(lo), rec_continuous))
    best_k = int(round(rec_continuous))

    # Per-land-count curve for the comparison display: a normalized closeness to
    # the (continuous) recommendation, so the curve peaks at best_k. Kept for the
    # comparison table; the recommendation itself comes from the formula above.
    span = max(1.0, (search_range[1] - search_range[0]) / 2.0)
    scores = [
        {"land_count": k, "score": round(max(0.0, 1.0 - abs(k - rec_continuous) / span), 4)}
        for k in range(search_range[0], search_range[1] + 1)
    ]

    result = {
        "recommended_lands": best_k,
        "deck_size": deck_size,
        "avg_cmc": round(avg_cmc, 2),
        "commander_cmcs": list(commander_cmcs),
        "scores": scores,
    }
    if len(commander_cmcs) >= 2:
        sorted_cmcs = sorted(c for c in commander_cmcs if c > 0)
        result["partner_castable_prob"] = round(
            prob_both_partners_castable(
                deck_size, best_k, sorted_cmcs[0], sorted_cmcs[1]
            ),
            4,
        )
    return result


def _weighted_avg_cmc(cmc_distribution: Dict[int, int]) -> float:
    """Weighted average CMC from a distribution {cmc: count}."""
    total_cards = sum(cmc_distribution.values())
    if total_cards == 0:
        return REC_ANCHOR_CMC
    return sum(cmc * count for cmc, count in cmc_distribution.items()) / total_cards


# ---------------------------------------------------------------------------
# Land count comparison
# ---------------------------------------------------------------------------

def land_count_comparison(
    deck_size: int,
    land_counts: List[int],
    max_turn: int = 10,
) -> List[Dict[str, Any]]:
    """Side-by-side comparison of multiple land counts.

    Returns a list of dicts, one per land count, each containing
    the mana table and summary stats.
    """
    results = []
    for k in land_counts:
        table = expected_mana_table(deck_size, k, max_turn)
        p_mull = mulligan_probability(deck_size, k)
        results.append({
            "land_count": k,
            "land_ratio": round(k / deck_size, 3),
            "mulligan_rate": round(p_mull, 4),
            "mana_table": table,
        })
    return results
