"""Mana-ramp analysis: how the rock count interacts with the deck's curve.

The single-number Implied Ramp verdict (R\\*) collapses two distinct effects
into one scalar:

  1. *Probability* of seeing a useful number of rocks early in the game.
  2. *Quality* of play conditional on each rock-draw outcome.

This module decomposes those axes. For a given ramp variant (current rock
count plus a what-if delta) we compute:

  - ``ramp_draw_probabilities``: hypergeometric probability of drawing
    k in {0, 1, 2, 3+} rocks among the first 11 cards (turns 1-5 on the
    play -- past turn 5, a freshly drawn 2-mana rock barely pays back its
    cost over the remaining T=8 turns).

  - ``simulate_ramp_conditional``: a fractional-expectation simulator
    conditioned on a specific rock count being drawn in phase 1. Tracks
    land mana and rock mana separately and spends land mana strictly
    before rock mana on each turn (so ``rock_util > 0`` implies that
    turn's land mana was fully spent).

  - ``redistribute_curve``: rebuilds the spendable-spell curve when N rocks are
    added or removed, distributing the slot change *proportionally* across
    existing CMC buckets (so the curve shape is preserved rather than the
    delta being dumped onto a single bucket).

The intended consumer is a per-deck panel that sweeps the rock count over
the deck's current R +/- 3 and shows how both axes move together.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from auto_goldfish.optimization.curve_value import (
    CommanderSpec,
    RampCardSpec,
    ROCK_CMC,
    cards_seen_by_turn,
    classify_for_curve_value,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PHASE1_TURN = 5  # cards_seen_by_turn(5, on_the_play=True) == 11
RAMP_DRAW_BUCKETS = (0, 1, 2, 3)  # last is "3 or more"
DEFAULT_TURNS = 8

DEFAULT_MC_TRIALS = 10000
DEFAULT_TRADEOFF_TRIALS = 1000
DEFAULT_MC_SEED = 17


def combined_mana_util(
    land_avail: float, land_spent: float,
    rock_avail: float, rock_spent: float,
) -> float:
    """Signed utilization score in [-1, 1]. See ``RampOutcome.mana_util``
    for the interpretation. Standalone so the Monte Carlo path can call it
    on per-trial totals without constructing a ``RampOutcome``."""
    if land_avail > 0:
        land_util = land_spent / land_avail
        if land_util < 1.0 - 1e-9:
            return -(1.0 - land_util)
    if rock_avail <= 0:
        return 0.0
    return rock_spent / rock_avail


# ---------------------------------------------------------------------------
# Datamodels
# ---------------------------------------------------------------------------

@dataclass
class RampOutcome:
    """Quality of play conditional on a fixed rock-draw scenario."""

    k_eff: float  # rock count used in the simulator (E[K|bucket] for "3+")
    p_scenario: float
    land_mana_available: float
    land_mana_spent: float
    rock_mana_available: float
    rock_mana_spent: float
    unspent_mana: float
    stuck_cards: float

    @property
    def land_util(self) -> float:
        if self.land_mana_available <= 0:
            return 0.0
        return self.land_mana_spent / self.land_mana_available

    @property
    def rock_util(self) -> float:
        if self.rock_mana_available <= 0:
            return 0.0
        return self.rock_mana_spent / self.rock_mana_available

    @property
    def mana_util(self) -> float:
        """Combined signed utilization score in [-1, 1].

        Negative magnitude = fraction of land mana left unspent (the deck
        is failing to use its base mana). Positive magnitude = fraction of
        rock mana spent (the deck is putting its surplus to work).

        Sign convention: land-priority spending means rock mana is only
        consumed once that turn's land mana is exhausted. But over T turns
        the aggregate can show *both* unspent land mana (one turn) and
        spent rock mana (another turn). When that happens the score reports
        the *land* deficit — wasted core mana is the more fundamental
        signal than rock surplus utilization.
        """
        return combined_mana_util(
            self.land_mana_available, self.land_mana_spent,
            self.rock_mana_available, self.rock_mana_spent,
        )


@dataclass
class RampVariant:
    label: str         # "current", "-2 rocks", "+3 rocks"
    delta_rocks: int   # signed: +1 means add a rock & cut a spendable spell
    R: int             # rock count after applying delta
    spendable_curve: Dict[int, float]


@dataclass
class RampPanel:
    """All ramp-scenario outcomes for one deck variant."""

    variant: RampVariant
    scenario_probs: Dict[int, float]
    outcomes: Dict[int, RampOutcome]

    @property
    def expected_unspent_mana(self) -> float:
        return sum(
            self.scenario_probs.get(b, 0.0) * o.unspent_mana
            for b, o in self.outcomes.items()
        )

    @property
    def expected_stuck_cards(self) -> float:
        return sum(
            self.scenario_probs.get(b, 0.0) * o.stuck_cards
            for b, o in self.outcomes.items()
        )


# ---------------------------------------------------------------------------
# Probability model
# ---------------------------------------------------------------------------

def _comb(n: int, k: int) -> int:
    if k < 0 or k > n:
        return 0
    return math.comb(n, k)


def hypergeo_pmf(D: int, R: int, n_draws: int, k: int) -> float:
    """P(K=k) when drawing n_draws cards without replacement from a deck of
    D cards containing R successes."""
    if D <= 0 or n_draws <= 0:
        return 1.0 if k == 0 else 0.0
    denom = _comb(D, n_draws)
    if denom == 0:
        return 0.0
    return _comb(R, k) * _comb(D - R, n_draws - k) / denom


def ramp_draw_probabilities(
    D: int, R: int, n_draws: int = 11, k_max_bucket: int = 3
) -> Dict[int, float]:
    """Bucketed P(K=k) with k_max_bucket as the "or more" bucket."""
    probs: Dict[int, float] = {b: 0.0 for b in range(k_max_bucket + 1)}
    upper = min(R, n_draws)
    for k in range(0, upper + 1):
        bucket = min(k, k_max_bucket)
        probs[bucket] += hypergeo_pmf(D, R, n_draws, k)
    return probs


def expected_rocks_in_bucket(
    D: int, R: int, n_draws: int, bucket: int, k_max_bucket: int = 3
) -> float:
    """E[K | K lands in this bucket]. For bucket < k_max_bucket this is just
    the bucket index; for bucket == k_max_bucket it's the conditional
    expectation over {k_max_bucket .. min(R, n_draws)}."""
    if bucket < k_max_bucket:
        return float(bucket)
    upper = min(R, n_draws)
    if upper < k_max_bucket:
        return float(k_max_bucket)
    total_p = 0.0
    weighted = 0.0
    for k in range(k_max_bucket, upper + 1):
        p = hypergeo_pmf(D, R, n_draws, k)
        total_p += p
        weighted += k * p
    return weighted / total_p if total_p > 0 else float(k_max_bucket)


# ---------------------------------------------------------------------------
# Curve redistribution
# ---------------------------------------------------------------------------

def redistribute_curve(
    spendable_curve: Dict[int, float], n_swap: int
) -> Dict[int, float]:
    """Add or remove ``n_swap`` spendable-spell slots proportionally across the
    existing curve. Positive ``n_swap`` means add slots; negative means
    remove. Returns a new dict; bucket counts may be fractional.

    Edge cases:
      - Empty curve with n_swap > 0: return {} (no shape to follow).
      - n_swap < -total_slots: floor at zero in every bucket.
    """
    total = sum(spendable_curve.values())
    out = {int(c): float(n) for c, n in spendable_curve.items()}
    if not out or total <= 0:
        return out
    factor = n_swap / total
    for c in list(out.keys()):
        out[c] = max(0.0, out[c] + out[c] * factor)
    return out


def build_ramp_variants(
    base_R: int,
    spendable_curve: Dict[int, float],
    delta_range: Tuple[int, int] = (-3, 3),
    include_no_ramp: bool = False,
) -> List[RampVariant]:
    """Build ramp variants spanning delta in [lo, hi] including 0 (current).

    A delta of +1 means "add 1 rock, remove 1 spendable spell" -- the slot pool
    is conserved. Variants that would push R below 0 are clipped at 0.

    When ``include_no_ramp`` is True and the leftmost delta step does not
    already cut all rocks (``base_R + lo > 0``), prepend a "no_ramp"
    variant at delta=-base_R. Useful as a far-left reference column
    showing the deck with all rocks redistributed into the spendable curve.
    """
    variants: List[RampVariant] = []
    seen_R: set[int] = set()
    lo, hi = delta_range
    lo = max(lo, -base_R)
    if include_no_ramp and base_R + lo > 0:
        no_ramp_curve = redistribute_curve(spendable_curve, base_R)
        variants.append(RampVariant(
            label="no_ramp", delta_rocks=-base_R, R=0, spendable_curve=no_ramp_curve,
        ))
        seen_R.add(0)

    for delta in range(lo, hi + 1):
        new_R = max(0, base_R + delta)
        if new_R in seen_R:
            continue
        # delta_rocks > 0 means we added rocks -> removed spendable slots.
        n_value_swap = -(new_R - base_R)
        new_curve = redistribute_curve(spendable_curve, n_value_swap)
        # Clip to nonneg integer-ish (preserved as floats for the simulator).
        if delta == 0:
            label = "current"
        else:
            unit = "Signet" if abs(delta) == 1 else "Signets"
            sign = "+" if delta > 0 else ""
            label = f"{sign}{delta} {unit}"
        variants.append(RampVariant(
            label=label, delta_rocks=delta, R=new_R, spendable_curve=new_curve
        ))
        seen_R.add(new_R)
    return variants


# ---------------------------------------------------------------------------
# Conditional simulator
# ---------------------------------------------------------------------------

def _draw_rates(
    L: int, R: int, spendable_curve: Dict[int, float], D: int,
    k_phase1: float, phase: int, phase1_cards: int,
) -> Tuple[float, float, Dict[int, float]]:
    """Per-card draw rates (rocks, lands, spendable-by-cmc) in phase 1 or 2.

    Phase 1: among the first ``phase1_cards`` cards we know exactly
    ``k_phase1`` rocks appear (in expectation). Per-card rock rate =
    k_phase1 / phase1_cards. The remaining (1 - k_phase1/phase1_cards)
    probability mass is split among non-rock cards proportional to their
    share of the (D - R) non-rock pool.

    Phase 2: the remaining pool is (D - phase1_cards) cards containing
    (R - k_phase1) rocks. The lands/value mix among non-rocks is the same
    ratio as in the full non-rock pool (conditioning on rock count doesn't
    change the relative lands/value distribution among non-rocks drawn).
    """
    non_rock = D - R
    if non_rock <= 0:
        # Pathological: deck is all rocks. Lands & value contribute 0.
        rate = (k_phase1 / phase1_cards) if (phase == 1 and phase1_cards > 0) else 0.0
        return rate, 0.0, {int(c): 0.0 for c in spendable_curve}

    if phase == 1:
        rock_rate = (k_phase1 / phase1_cards) if phase1_cards > 0 else 0.0
        non_rock_rate = 1.0 - rock_rate
    else:
        d2 = D - phase1_cards
        if d2 <= 0:
            return 0.0, 0.0, {int(c): 0.0 for c in spendable_curve}
        rock_rate = max(0.0, (R - k_phase1)) / d2
        non_rock_rate = 1.0 - rock_rate

    land_rate = non_rock_rate * L / non_rock
    value_rates = {
        int(c): non_rock_rate * float(n) / non_rock for c, n in spendable_curve.items()
    }
    return rock_rate, land_rate, value_rates


def simulate_ramp_conditional(
    L: int,
    R: int,
    spendable_curve: Dict[int, float],
    k_phase1: float,
    commanders: List[CommanderSpec],
    D: int,
    T: int = DEFAULT_TURNS,
    per_turn_cumulative_draws: Optional[List[float]] = None,
    phase1_cards: int = 11,
) -> RampOutcome:
    """Simulate one game conditioned on ``k_phase1`` rocks being drawn in
    the first ``phase1_cards`` cards (phase 1 = turns 1..PHASE1_TURN).

    When ``per_turn_cumulative_draws`` is provided (length T), it replaces
    the natural draw schedule (``cards_seen_by_turn``) -- this is how the
    deck's measured cantrip/draw signature gets folded in without
    simulating the effects themselves.

    Land-mana priority is enforced per turn: when mana is spent, lands are
    consumed first, then rocks. So ``rock_util > 0`` for any turn implies
    that turn's lands_in_play were entirely spent.

    Returns a ``RampOutcome`` aggregating over all T turns.
    """
    if T <= 0:
        return RampOutcome(
            k_eff=k_phase1, p_scenario=0.0,
            land_mana_available=0.0, land_mana_spent=0.0,
            rock_mana_available=0.0, rock_mana_spent=0.0,
            unspent_mana=0.0, stuck_cards=0.0,
        )

    hand_curve: Dict[int, float] = {int(c): 0.0 for c in spendable_curve}
    hand_rocks = 0.0
    hand_lands = 0.0
    lands_in_play = 0.0
    rocks_in_play = 0.0
    cmd_to_cast: List[int] = sorted([c.cmc for c in commanders if 0 < c.cmc <= T])

    land_mana_available = 0.0
    rock_mana_available = 0.0
    land_mana_spent = 0.0
    rock_mana_spent = 0.0
    unspent_mana = 0.0

    cards_seen_prev = 0.0
    for t in range(1, T + 1):
        if per_turn_cumulative_draws is not None and t - 1 < len(per_turn_cumulative_draws):
            seen = float(per_turn_cumulative_draws[t - 1])
        else:
            seen = float(cards_seen_by_turn(t))
        new_cards = max(0.0, seen - cards_seen_prev)
        cards_seen_prev = seen
        phase = 1 if seen <= phase1_cards else 2

        if D > 0:
            rock_rate, land_rate, value_rates = _draw_rates(
                L, R, spendable_curve, D, k_phase1, phase, phase1_cards,
            )
            hand_rocks += new_cards * rock_rate
            hand_lands += new_cards * land_rate
            for c, rate in value_rates.items():
                hand_curve[c] = hand_curve.get(c, 0.0) + new_cards * rate

        # One land drop per turn, capped by hand + turn budget.
        land_drop = min(hand_lands, max(0.0, t - lands_in_play), 1.0)
        hand_lands -= land_drop
        lands_in_play += land_drop

        # Today's mana (rocks already in play). Rocks cast this turn enter
        # tapped and will produce starting next turn.
        m_land = lands_in_play
        m_rock = rocks_in_play
        land_mana_available += m_land
        rock_mana_available += m_rock

        def spend(cost: float) -> Tuple[float, float]:
            """Pay ``cost`` mana, land first then rock. Returns (paid_land,
            paid_rock). Mutates m_land/m_rock via the closure."""
            nonlocal m_land, m_rock
            from_land = min(m_land, cost)
            m_land -= from_land
            remaining = cost - from_land
            from_rock = min(m_rock, remaining)
            m_rock -= from_rock
            return from_land, from_rock

        # Commander (if affordable).
        if cmd_to_cast and cmd_to_cast[0] <= (m_land + m_rock):
            cost = cmd_to_cast.pop(0)
            paid_l, paid_r = spend(float(cost))
            land_mana_spent += paid_l
            rock_mana_spent += paid_r

        # Play rocks if affordable. Rocks enter tapped.
        if hand_rocks > 0 and (m_land + m_rock) >= ROCK_CMC:
            avail = m_land + m_rock
            rocks_can_play = min(hand_rocks, avail / ROCK_CMC)
            if rocks_can_play > 0:
                paid_l, paid_r = spend(rocks_can_play * ROCK_CMC)
                land_mana_spent += paid_l
                rock_mana_spent += paid_r
                hand_rocks -= rocks_can_play
                rocks_in_play += rocks_can_play

        # Greedy value casting: highest castable CMC first.
        for c in sorted(hand_curve.keys(), reverse=True):
            if c <= 0 or hand_curve[c] <= 0:
                continue
            avail = m_land + m_rock
            if avail < c:
                continue
            n_cast = min(hand_curve[c], avail / c)
            if n_cast <= 0:
                continue
            paid_l, paid_r = spend(n_cast * c)
            land_mana_spent += paid_l
            rock_mana_spent += paid_r
            hand_curve[c] -= n_cast
            if (m_land + m_rock) <= 0:
                break

        unspent_mana += max(0.0, m_land + m_rock)

    # Stuck cards: count of cards still in hand whose cmc exceeds the final
    # mana base. Reported as a count (not mana-weighted) per spec.
    max_cast = lands_in_play + rocks_in_play
    stuck_cards = 0.0
    for c, n in hand_curve.items():
        if c > max_cast and n > 0:
            stuck_cards += n

    return RampOutcome(
        k_eff=k_phase1,
        p_scenario=0.0,  # filled in by caller
        land_mana_available=land_mana_available,
        land_mana_spent=land_mana_spent,
        rock_mana_available=rock_mana_available,
        rock_mana_spent=rock_mana_spent,
        unspent_mana=unspent_mana,
        stuck_cards=stuck_cards,
    )


# ---------------------------------------------------------------------------
# Panel builder
# ---------------------------------------------------------------------------

def compute_ramp_panel(
    variant: RampVariant,
    L: int,
    commanders: List[CommanderSpec],
    D: int,
    T: int = DEFAULT_TURNS,
    n_draws: int = 11,
    k_max_bucket: int = 3,
    per_turn_cumulative_draws: Optional[List[float]] = None,
) -> RampPanel:
    """Build the scenario probabilities + per-scenario outcomes for one
    ramp variant. ``D`` is the *original* effective deck size (commanders
    excluded); variants preserve D by trading rock slots for spendable slots.

    When ``per_turn_cumulative_draws`` is provided (length T from the main
    simulator), ``n_draws`` is overridden by
    ``round(per_turn_cumulative_draws[PHASE1_TURN - 1])`` and the signature
    is forwarded to ``simulate_ramp_conditional`` so the per-turn draw
    schedule matches the deck's measured card-draw rate.
    """
    if per_turn_cumulative_draws is not None and len(per_turn_cumulative_draws) >= PHASE1_TURN:
        n_draws = max(1, round(per_turn_cumulative_draws[PHASE1_TURN - 1]))
    probs = ramp_draw_probabilities(D, variant.R, n_draws=n_draws, k_max_bucket=k_max_bucket)
    outcomes: Dict[int, RampOutcome] = {}
    for bucket in range(k_max_bucket + 1):
        k_eff = expected_rocks_in_bucket(D, variant.R, n_draws, bucket, k_max_bucket)
        outcome = simulate_ramp_conditional(
            L=L, R=variant.R, spendable_curve=variant.spendable_curve,
            k_phase1=k_eff, commanders=commanders, D=D, T=T,
            per_turn_cumulative_draws=per_turn_cumulative_draws,
            phase1_cards=n_draws,
        )
        outcome.p_scenario = probs[bucket]
        outcomes[bucket] = outcome
    return RampPanel(
        variant=variant, scenario_probs=probs, outcomes=outcomes,
    )


# ---------------------------------------------------------------------------
# Monte Carlo simulator (for variance estimation)
# ---------------------------------------------------------------------------

# Card-type tags used internally by the MC simulator.
_LAND = "L"
_ROCK = "R"
_FILLER = "F"  # commanders / draws / anything we don't model in hand


def _build_deck_list(
    L: int, R: int, spendable_curve: Dict[int, float], D: int,
) -> List[Tuple[str, int]]:
    """Build a literal list of (kind, cmc) tuples summing to D cards.

    Rounds the spendable_curve floats to nearest int and pads/truncates with filler
    so the total equals D. Commanders are tracked separately and not in
    this list (they enter from the command zone, not the library).
    """
    cards: List[Tuple[str, int]] = []
    cards.extend((_LAND, 0) for _ in range(L))
    cards.extend((_ROCK, 2) for _ in range(R))
    for c, n in spendable_curve.items():
        n_int = int(round(float(n)))
        if n_int < 0:
            n_int = 0
        cards.extend(("V", int(c)) for _ in range(n_int))
    # Pad or truncate to D.
    while len(cards) < D:
        cards.append((_FILLER, 0))
    if len(cards) > D:
        cards = cards[:D]
    return cards


@dataclass
class _GameResult:
    k_phase1: int
    land_mana_available: float
    land_mana_spent: float
    rock_mana_available: float
    rock_mana_spent: float
    unspent_mana: float
    stuck_cards: int


def _simulate_one_game(
    deck: List[Tuple[str, int]],
    commanders: List[CommanderSpec],
    T: int,
    rng: random.Random,
    phase1_cards: int = 11,
    per_turn_cumulative_draws: Optional[List[float]] = None,
) -> _GameResult:
    """Stochastic single-game simulator. Shuffles ``deck``, deals opening 7,
    draws per turn, plays land + commander + rocks + spendable spells with
    land-priority mana spending. Returns aggregate per-game statistics
    including ``k_phase1`` = rocks drawn in the first ``phase1_cards`` cards.

    When ``per_turn_cumulative_draws`` is provided (length T), the per-turn
    draw count comes from that schedule instead of the default 1/turn:
    turn t draws ``cumulative[t-1] - cumulative[t-2]`` cards (with the
    pre-opener value treated as 7). Fractional rates are realized as
    ``floor(rate) + Bernoulli(rate - floor)`` so the long-run average
    matches the schedule exactly.
    """
    library = list(deck)
    rng.shuffle(library)

    hand_lands = 0
    hand_rocks = 0
    hand_value: Dict[int, int] = {}
    lands_in_play = 0
    rocks_in_play = 0
    cmd_to_cast = sorted([c.cmc for c in commanders if 0 < c.cmc <= T])

    land_mana_available = 0.0
    rock_mana_available = 0.0
    land_mana_spent = 0.0
    rock_mana_spent = 0.0
    unspent_mana = 0.0

    drawn = 0
    k_phase1 = 0

    def draw(n: int) -> None:
        nonlocal drawn, k_phase1, hand_lands, hand_rocks
        for _ in range(n):
            if not library:
                return
            card = library.pop()
            drawn += 1
            in_phase1 = drawn <= phase1_cards
            kind, cmc = card
            if kind == _LAND:
                hand_lands += 1
            elif kind == _ROCK:
                hand_rocks += 1
                if in_phase1:
                    k_phase1 += 1
            elif kind == "V":
                hand_value[cmc] = hand_value.get(cmc, 0) + 1
            # _FILLER: drawn but unmodeled.

    def draw_fractional(rate: float) -> None:
        """Draw floor(rate) cards plus one more with prob (rate - floor)."""
        if rate <= 0:
            return
        n = int(rate)
        residual = rate - n
        if residual > 0 and rng.random() < residual:
            n += 1
        if n > 0:
            draw(n)

    draw(7)
    prev_cum = 7.0
    for t in range(1, T + 1):
        if per_turn_cumulative_draws is not None and t - 1 < len(per_turn_cumulative_draws):
            target = float(per_turn_cumulative_draws[t - 1])
            extra = max(0.0, target - prev_cum)
            draw_fractional(extra)
            prev_cum = target
        elif t > 1:
            draw(1)

        if hand_lands > 0 and lands_in_play < t:
            hand_lands -= 1
            lands_in_play += 1

        m_land = float(lands_in_play)
        m_rock = float(rocks_in_play)
        land_mana_available += m_land
        rock_mana_available += m_rock

        def spend(cost: float) -> None:
            nonlocal m_land, m_rock, land_mana_spent, rock_mana_spent
            from_land = min(m_land, cost)
            m_land -= from_land
            land_mana_spent += from_land
            remaining = cost - from_land
            from_rock = min(m_rock, remaining)
            m_rock -= from_rock
            rock_mana_spent += from_rock

        if cmd_to_cast and cmd_to_cast[0] <= (m_land + m_rock):
            spend(float(cmd_to_cast.pop(0)))

        while hand_rocks > 0 and (m_land + m_rock) >= ROCK_CMC:
            spend(float(ROCK_CMC))
            hand_rocks -= 1
            rocks_in_play += 1

        # Greedy: highest castable CMC first.
        while True:
            avail = m_land + m_rock
            castable_cmcs = [
                c for c, n in hand_value.items() if n > 0 and c <= avail and c > 0
            ]
            if not castable_cmcs:
                break
            c = max(castable_cmcs)
            spend(float(c))
            hand_value[c] -= 1

        unspent_mana += max(0.0, m_land + m_rock)

    max_cast = lands_in_play + rocks_in_play
    stuck = 0
    for c, n in hand_value.items():
        if c > max_cast and n > 0:
            stuck += n

    return _GameResult(
        k_phase1=k_phase1,
        land_mana_available=land_mana_available,
        land_mana_spent=land_mana_spent,
        rock_mana_available=rock_mana_available,
        rock_mana_spent=rock_mana_spent,
        unspent_mana=unspent_mana,
        stuck_cards=stuck,
    )


@dataclass
class RampBucketStats:
    """Monte Carlo aggregated statistics for one (variant, scenario) pair."""

    n_samples: int
    mana_util_mean: float
    mana_util_sd: float
    unspent_mana_mean: float
    unspent_mana_sd: float
    stuck_cards_mean: float
    stuck_cards_sd: float


@dataclass
class RampMCPanel:
    """Monte Carlo version of ``RampPanel``."""

    variant: RampVariant
    n_trials: int
    scenario_probs: Dict[int, float]  # analytical hypergeometric
    bucket_stats: Dict[int, RampBucketStats]

    @property
    def expected_unspent_mana(self) -> float:
        total = 0.0
        for b, s in self.bucket_stats.items():
            p = self.scenario_probs.get(b, 0.0)
            if p <= 0 or math.isnan(s.unspent_mana_mean):
                continue
            total += p * s.unspent_mana_mean
        return total

    @property
    def expected_stuck_cards(self) -> float:
        total = 0.0
        for b, s in self.bucket_stats.items():
            p = self.scenario_probs.get(b, 0.0)
            if p <= 0 or math.isnan(s.stuck_cards_mean):
                continue
            total += p * s.stuck_cards_mean
        return total

    @property
    def expected_mana_util(self) -> float:
        total = 0.0
        for b, s in self.bucket_stats.items():
            p = self.scenario_probs.get(b, 0.0)
            if p <= 0 or math.isnan(s.mana_util_mean):
                continue
            total += p * s.mana_util_mean
        return total


def _mean_sd(values: List[float]) -> Tuple[float, float]:
    if not values:
        return float("nan"), float("nan")
    n = len(values)
    mean = sum(values) / n
    if n < 2:
        return mean, 0.0
    var = sum((v - mean) ** 2 for v in values) / (n - 1)
    return mean, math.sqrt(var)


def _spend_rate(
    land_avail: float,
    land_spent: float,
    rock_avail: float,
    rock_spent: float,
) -> float:
    available = land_avail + rock_avail
    if available <= 0:
        return 0.0
    return max(0.0, min(1.0, (land_spent + rock_spent) / available))


def compute_ramp_mc_panel(
    variant: RampVariant,
    L: int,
    commanders: List[CommanderSpec],
    D: int,
    T: int = DEFAULT_TURNS,
    n_trials: int = DEFAULT_MC_TRIALS,
    seed: int = DEFAULT_MC_SEED,
    k_max_bucket: int = 3,
    phase1_cards: int = 11,
    per_turn_cumulative_draws: Optional[List[float]] = None,
) -> RampMCPanel:
    """Monte Carlo panel for one ramp variant. Per-trial stats are bucketed
    by ``min(k_phase1, k_max_bucket)``. Scenario probabilities are kept
    analytical (hypergeometric) since the closed form is exact; the MC
    samples drive mean/SD of the outcome metrics.

    When ``per_turn_cumulative_draws`` is provided (length T from the main
    simulator's ``mean_cumulative_draws_per_turn``), ``phase1_cards`` is
    overridden by ``round(per_turn_cumulative_draws[PHASE1_TURN - 1])`` and
    each MC trial's per-turn draw count is taken from the schedule rather
    than the default 1/turn.
    """
    if per_turn_cumulative_draws is not None and len(per_turn_cumulative_draws) >= PHASE1_TURN:
        phase1_cards = max(1, round(per_turn_cumulative_draws[PHASE1_TURN - 1]))
    deck = _build_deck_list(L, variant.R, variant.spendable_curve, D)
    rng = random.Random(seed)

    by_bucket: Dict[int, List[Tuple[float, float, int]]] = {
        b: [] for b in range(k_max_bucket + 1)
    }
    for _ in range(n_trials):
        result = _simulate_one_game(
            deck=deck, commanders=commanders, T=T, rng=rng,
            phase1_cards=phase1_cards,
            per_turn_cumulative_draws=per_turn_cumulative_draws,
        )
        bucket = min(result.k_phase1, k_max_bucket)
        util = _spend_rate(
            result.land_mana_available, result.land_mana_spent,
            result.rock_mana_available, result.rock_mana_spent,
        )
        by_bucket[bucket].append((util, result.unspent_mana, result.stuck_cards))

    probs = ramp_draw_probabilities(
        D, variant.R, n_draws=phase1_cards, k_max_bucket=k_max_bucket
    )

    bucket_stats: Dict[int, RampBucketStats] = {}
    for b, rows in by_bucket.items():
        utils = [r[0] for r in rows]
        unspents = [r[1] for r in rows]
        stucks = [float(r[2]) for r in rows]
        u_mean, u_sd = _mean_sd(utils)
        m_mean, m_sd = _mean_sd(unspents)
        s_mean, s_sd = _mean_sd(stucks)
        bucket_stats[b] = RampBucketStats(
            n_samples=len(rows),
            mana_util_mean=u_mean, mana_util_sd=u_sd,
            unspent_mana_mean=m_mean, unspent_mana_sd=m_sd,
            stuck_cards_mean=s_mean, stuck_cards_sd=s_sd,
        )

    return RampMCPanel(
        variant=variant, n_trials=n_trials,
        scenario_probs=probs, bucket_stats=bucket_stats,
    )


# ---------------------------------------------------------------------------
# Web-panel JSON orchestration
# ---------------------------------------------------------------------------

def _metric_standard_error(panel: RampMCPanel, metric: str) -> float:
    variance = 0.0
    saw_sample = False
    for bucket, stats in panel.bucket_stats.items():
        p = panel.scenario_probs.get(bucket, 0.0)
        n = stats.n_samples
        if p <= 0 or n <= 1:
            continue
        sd = getattr(stats, f"{metric}_sd")
        if math.isnan(sd):
            continue
        saw_sample = True
        variance += (p * sd) ** 2 / n
    if not saw_sample:
        return float("inf")
    return math.sqrt(variance)


def _delta_exceeds_noise(a: RampMCPanel, b: RampMCPanel, metric: str) -> bool:
    a_mean = getattr(a, f"expected_{metric}")
    b_mean = getattr(b, f"expected_{metric}")
    noise = math.sqrt(_metric_standard_error(a, metric) ** 2 + _metric_standard_error(b, metric) ** 2)
    return abs(b_mean - a_mean) > noise


def _panel_to_dict(panel: RampMCPanel) -> Dict[str, Any]:
    return {
        "label": panel.variant.label,
        "delta_rocks": panel.variant.delta_rocks,
        "R": panel.variant.R,
        "spendable_slots": sum(panel.variant.spendable_curve.values()),
        "unspent_mana": panel.expected_unspent_mana,
        "unspent_mana_se": _metric_standard_error(panel, "unspent_mana"),
        "stuck_cards": panel.expected_stuck_cards,
        "stuck_cards_se": _metric_standard_error(panel, "stuck_cards"),
        "spend_rate": panel.expected_mana_util,
        "scenario_probs": {str(k): panel.scenario_probs.get(k, 0.0) for k in RAMP_DRAW_BUCKETS},
    }


def _build_callouts(panels: List[RampMCPanel]) -> List[str]:
    current = next((p for p in panels if p.variant.delta_rocks == 0), None)
    if current is None:
        return []

    callouts: List[Tuple[int, str]] = []
    plus_panels = sorted(
        [p for p in panels if p.variant.R > current.variant.R],
        key=lambda p: p.variant.R,
    )
    cut_panels = sorted(
        [p for p in panels if p.variant.R < current.variant.R],
        key=lambda p: current.variant.R - p.variant.R,
    )

    for panel in plus_panels:
        stuck_drop = current.expected_stuck_cards - panel.expected_stuck_cards
        if stuck_drop > 0 and _delta_exceeds_noise(current, panel, "stuck_cards"):
            callouts.append((
                0,
                f"Adding ramp appears to reduce stuck cards here ({current.variant.R} -> {panel.variant.R} Signets).",
            ))
            break

    for panel in plus_panels:
        unspent_rise = panel.expected_unspent_mana - current.expected_unspent_mana
        stuck_drop = current.expected_stuck_cards - panel.expected_stuck_cards
        stuck_noise = math.sqrt(
            _metric_standard_error(current, "stuck_cards") ** 2
            + _metric_standard_error(panel, "stuck_cards") ** 2
        )
        if (
            unspent_rise > 0
            and _delta_exceeds_noise(current, panel, "unspent_mana")
            and stuck_drop <= max(stuck_noise, 0.10)
        ):
            callouts.append((
                1,
                f"Adding ramp mostly increases surplus mana here ({current.variant.R} -> {panel.variant.R} Signets).",
            ))
            break

    for panel in cut_panels:
        unspent_drop = current.expected_unspent_mana - panel.expected_unspent_mana
        p0_rise = panel.scenario_probs.get(0, 0.0) - current.scenario_probs.get(0, 0.0)
        if (
            unspent_drop > 0
            and p0_rise > 0.05
            and _delta_exceeds_noise(current, panel, "unspent_mana")
        ):
            callouts.append((
                2,
                f"Cutting ramp trades surplus mana for more zero-Signet early games ({current.variant.R} -> {panel.variant.R} Signets).",
            ))
            break

    callouts.sort(key=lambda item: item[0])
    out: List[str] = []
    seen: set[str] = set()
    for _, text in callouts:
        if text in seen:
            continue
        out.append(text)
        seen.add(text)
        if len(out) >= 2:
            break
    return out


def compute_ramp_tradeoff(
    deck_list: List[Dict[str, Any]],
    per_turn_cumulative_draws: Optional[List[float]],
    registry=None,
    overrides: Optional[Dict[str, Any]] = None,
    turns: int = DEFAULT_TURNS,
    n_trials: int = DEFAULT_TRADEOFF_TRIALS,
    seed: int = DEFAULT_MC_SEED,
) -> Dict[str, Any]:
    """Compute the JSON-ready Ramp Tradeoff panel for one result.

    The shared classifier keeps its historical ``V_curve`` keys; this function
    translates them into Ramp Tradeoff's spendable terminology at the boundary.
    """
    return compute_ramp_tradeoff_from_input(
        ramp_tradeoff_input=classify_ramp_tradeoff_input(deck_list, registry, overrides),
        per_turn_cumulative_draws=per_turn_cumulative_draws,
        turns=turns,
        n_trials=n_trials,
        seed=seed,
    )


def classify_ramp_tradeoff_input(
    deck_list: List[Dict[str, Any]],
    registry=None,
    overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    cls = classify_for_curve_value(deck_list, registry=registry, overrides=overrides)
    raw_spendable_curve = cls.get("spendable_curve", cls["V_curve"])
    spendable_curve = {int(c): float(n) for c, n in raw_spendable_curve.items()}
    return {
        "D": cls["D"],
        "L": cls["L"],
        "current_rocks": len(cls["ramp_specs"]),
        "spendable_curve": spendable_curve,
        "commanders": [{"name": c.name, "cmc": c.cmc} for c in cls["commanders"]],
        "draw_spells_included": cls["draw_count"],
    }


def compute_ramp_tradeoff_from_input(
    ramp_tradeoff_input: Dict[str, Any],
    per_turn_cumulative_draws: Optional[List[float]],
    turns: int = DEFAULT_TURNS,
    n_trials: int = DEFAULT_TRADEOFF_TRIALS,
    seed: int = DEFAULT_MC_SEED,
) -> Dict[str, Any]:
    spendable_curve = {
        int(c): float(n)
        for c, n in (ramp_tradeoff_input.get("spendable_curve") or {}).items()
    }
    spendable_slots = sum(spendable_curve.values())
    current_R = int(ramp_tradeoff_input.get("current_rocks", 0))
    commanders = [
        c if isinstance(c, CommanderSpec) else CommanderSpec(name=str(c.get("name", "")), cmc=int(c.get("cmc", 0)))
        for c in (ramp_tradeoff_input.get("commanders") or [])
    ]
    signature = list(per_turn_cumulative_draws or [])
    phase1_cards = (
        max(1, round(signature[PHASE1_TURN - 1]))
        if len(signature) >= PHASE1_TURN
        else cards_seen_by_turn(PHASE1_TURN)
    )

    base = {
        "suppressed": False,
        "reason": None,
        "phase1_turn": PHASE1_TURN,
        "cards_seen_by_phase1": phase1_cards,
        "n_trials": n_trials,
        "current_rocks": current_R,
        "spendable_slots": spendable_slots,
        "draw_spells_included": int(ramp_tradeoff_input.get("draw_spells_included", 0)),
        "variants": [],
        "callouts": [],
    }

    if spendable_slots <= 0:
        return {
            **base,
            "suppressed": True,
            "reason": "No spendable spells to absorb mana.",
        }

    variants = build_ramp_variants(
        base_R=current_R,
        spendable_curve=spendable_curve,
        delta_range=(-3, 3),
        include_no_ramp=True,
    )

    panels = [
        compute_ramp_mc_panel(
            variant=variant,
            L=int(ramp_tradeoff_input.get("L", 0)),
            commanders=commanders,
            D=int(ramp_tradeoff_input.get("D", 0)),
            T=turns,
            n_trials=n_trials,
            seed=seed,
            per_turn_cumulative_draws=signature or None,
        )
        for variant in variants
    ]

    return {
        **base,
        "variants": [_panel_to_dict(panel) for panel in panels],
        "callouts": _build_callouts(panels),
    }
