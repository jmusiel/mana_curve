"""Curve value analytical metrics: Implied Draw + Implied Spell Value.

Two analytical metrics that complement the Monte Carlo simulator:

- **Implied Draw**: how many cards the deck needs to see during the game to
  spend all the mana it generates (lands + ramp), accounting for commanders
  cast on curve. Compared against the simulator's measured draws gives the
  draw-package adequacy.

- **Implied Spell Value**: per-card IRR of the ramp investment, aggregated
  to a deck-level discount factor delta, used to derive the required
  intrinsic-power multiplier per CMC bucket relative to a 2-drop baseline.

Both metrics are pure analytic — no simulation needed. Math cross-validated
against MC simulation on three real Commander decks (within ~6%).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from auto_goldfish.effects.builtin import (
    LandToBattlefield,
    ProduceMana,
    ReduceCost,
)
from auto_goldfish.effects.registry import EffectRegistry


OPENING_HAND = 7
ON_THE_PLAY = True
BASELINE_CMC = 2

# Per-turn IRR bisection bounds.
IRR_LO = -0.99
IRR_HI = 10.0
IRR_TOL = 1e-6
IRR_MAX_ITER = 200

# Legacy IRR-aggregation cap, kept for backwards-compatible tests. The
# production verdict no longer derives delta from per-piece IRRs.
DEFAULT_IRR_CAP = 1.0

# Legacy loan-size threshold (B3). Kept for backwards-compatible tests; the
# production verdict no longer uses loan-based alpha.
DEFAULT_LOAN_THRESHOLD = 15.0

# Anchor for the verdict's discount factor. delta is fixed (not derived from
# per-piece IRRs) so cuts to ramp can never accidentally raise A by shifting
# the median or mean of the IRR distribution. 0.85 calibrated against a mix
# of real and synthetic decks so well-built decks read mostly coherent/slack
# while deliberately misbuilt decks (over-ramped + low curve) still flag
# ramp_over_aggressive at the obvious slot.
DEFAULT_FIXED_DELTA = 0.85

# Stuck-cost aggregation modes for the Implied Ramp sweep. See
# ``_simulate_float_stuck`` for the per-mode math. ``uniform`` is the
# original prototype objective (linear accumulation per stuck turn). The
# other three are smoothing variants explored to fix the bimodal-cliff
# behaviour identified during evaluation.
STUCK_MODE_UNIFORM = "uniform"
STUCK_MODE_TURN_DECAY = "turn_decay"
STUCK_MODE_PER_CARD_CAP = "per_card_cap"
STUCK_MODE_MANA_GAP = "mana_gap"
STUCK_MODES = (
    STUCK_MODE_UNIFORM,
    STUCK_MODE_TURN_DECAY,
    STUCK_MODE_PER_CARD_CAP,
    STUCK_MODE_MANA_GAP,
)
DEFAULT_STUCK_MODE = STUCK_MODE_UNIFORM

# Sigmoid scale for the excess-based commitment factor. alpha = 1 - exp(-X/k)
# where X is the deck's idealized ramp excess (sum of M*(T-c) - c across ramp
# pieces). k=50 puts heavy decks (rr_connection X~62) near 0.71, low-ramp
# decks (Edgar X~13) near 0.23, and saturates smoothly -- every ramp cut
# reduces excess and therefore alpha, monotonically.
DEFAULT_EXCESS_K = 50.0


# ---------------------------------------------------------------------------
# Datamodels
# ---------------------------------------------------------------------------

@dataclass
class RampCardSpec:
    """A ramp card's relevant properties for IRR / contribution analysis."""

    name: str
    cmc: int
    mana_per_turn: float = 0.0


@dataclass
class CommanderSpec:
    """Lightweight commander record (we only need name + cmc)."""

    name: str
    cmc: int


@dataclass
class ImpliedDrawResult:
    """Result of the Implied Draw analysis for a single deck variant."""

    L: int
    R: int
    V: int
    D: int
    V_avg_cmc: float
    land_mana: float
    ramp_excess: float
    total_mana: float
    commander_mana: float
    value_mana: float
    N_natural: int
    N_max: float
    deficit_max: float
    # Per-turn cumulative cards required (analytical, max of bottlenecks)
    # and natural draw line.
    per_turn_required: List[float] = field(default_factory=list)
    per_turn_natural: List[int] = field(default_factory=list)
    # Bottleneck breakdown -- which constraint is driving cards-required at
    # each turn. Each element is total cards drawn needed to satisfy that
    # specific bottleneck on its own. ``per_turn_required[t]`` is their max.
    per_turn_lands_required: List[float] = field(default_factory=list)
    per_turn_value_required: List[float] = field(default_factory=list)
    # Optional MC-measured per-turn cumulative draws.
    per_turn_actual: Optional[List[float]] = None
    actual_total_draws: Optional[float] = None
    actual_deficit: Optional[float] = None


@dataclass
class PerCardIRR:
    name: str
    cmc: int
    mana_per_turn: float
    irr_per_turn: float


@dataclass
class ImpliedSpellValueResult:
    """Result of the Implied Spell Value (IRR-based) analysis."""

    median_irr: float
    delta: float
    baseline_cmc: int
    power_multipliers: Dict[int, float]
    per_card_irrs: List[PerCardIRR]
    # When True, the deck has no permanent ramp and we fell back to delta=1.0.
    no_ramp: bool = False


@dataclass
class CurveVerdictRow:
    """Per-CMC reading of A vs. B for a single curve slot."""

    cmc: int
    n_cards: float
    mt_per_slot: float
    a_required: float
    # b_implicit is None for CMCs with no slots in the deck. Otherwise it is
    # the deck's implicit valuation: mt_per_slot(baseline) / mt_per_slot(c).
    b_implicit: Optional[float]
    # kind is the structured tag the UI translates into prose:
    #   "baseline"             -> c == baseline_cmc
    #   "below_baseline"       -> c < baseline_cmc (ratio reported, no verdict)
    #   "coherent"             -> |a - b| within tolerance
    #   "ramp_over_aggressive" -> b < a; ramp demands more than the deck implies
    #   "over_allocated"       -> b > a; deck implies more than the ramp demands
    #   "no_slots"             -> N(c) == 0; A reported, B undefined
    kind: str
    # gap = a / b when ramp_over_aggressive (>1.0); else None.
    gap: Optional[float] = None
    # slack = b / a when over_allocated (>1.0); else None.
    slack: Optional[float] = None


@dataclass
class CurveVerdict:
    """A vs. B per-CMC reading: required power demand vs. implicit allocation.

    A combines a fixed discount factor (delta = DEFAULT_FIXED_DELTA) with the
    deck's idealized ramp excess via a sigmoid commitment factor:
    ``a_eff = 1 + alpha * (a_raw - 1)`` where ``alpha = 1 - exp(-excess/k)``.
    Because alpha is monotonic in cuts to ramp (every ramp piece has positive
    excess contribution), cutting any ramp piece always softens A_eff.

    B is the curve-aware play-to-curve simulator's per-slot mana-turn delivery.

    `net_flat` is the total per-CMC delta between with-ramp and no-ramp
    play-to-curve simulations: positive means ramp net-helps even at flat
    power; negative means ramp net-loses.
    """

    delta: float
    median_irr: float
    baseline_cmc: int
    no_ramp: bool
    T: int
    net_flat: float
    # Commitment factor in [0, 1]. Production: excess-based sigmoid (Option C).
    ramp_share: float = 1.0
    # Gross mana sunk into ramp pieces (sum of cmc). Informational; not used
    # in the verdict math under Option C.
    loan_size: float = 0.0
    # Net mana the deck's ramp produces over T turns (idealized: each piece
    # cast on its CMC turn). Drives `ramp_share`/alpha under Option C.
    idealized_excess: float = 0.0
    loss_breakdown: Dict[int, float] = field(default_factory=dict)
    gain_breakdown: Dict[int, float] = field(default_factory=dict)
    rows: List[CurveVerdictRow] = field(default_factory=list)


@dataclass
class ImpliedRampResult:
    """Result of the Implied Ramp analysis.

    Sweeps a counterfactual ramp count R (in 2-mana-rock equivalents) over
    ``[0, R_max]``. For each R, builds a deck with the original value-curve
    shape scaled to the remaining value slots and computes:

      - ``float_cost(R)``: mana available but unspent (mana-units over T turns)
      - ``stuck_cost(R)``: mana value of hand cards exceeding available mana,
        accumulated each turn

    Both are in mana-units; their sum is the deck's total "friction" cost at
    that ramp level. ``R_star`` minimizes total. ``R_actual`` is the deck's
    current ramp expressed in rock-equivalents (each piece's idealized excess
    over T turns divided by one 2-mana-rock's idealized excess).
    """

    T: int
    R_actual: float
    R_star: int
    R_grid: List[int]
    float_curve: List[float]
    stuck_curve: List[float]
    total_curve: List[float]
    verdict: str  # "under_ramped" | "right_sized" | "over_ramped"
    delta_rocks: float  # R_star - R_actual
    stuck_mode: str = DEFAULT_STUCK_MODE


@dataclass
class CurveValueResult:
    """Top-level wrapper: both metrics + the inputs used."""

    turns: int
    deck_size_effective: int
    implied_draw: ImpliedDrawResult
    implied_spell_value: ImpliedSpellValueResult
    curve_verdict: Optional[CurveVerdict] = None
    turn_structure: Optional["TurnStructureResult"] = None
    implied_ramp: Optional[ImpliedRampResult] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def cards_seen_by_turn(t: int, on_the_play: bool = ON_THE_PLAY) -> int:
    """Cards seen by end of turn t with no draw spells (opener + draw steps)."""
    extra = (t - 1) if on_the_play else t
    return OPENING_HAND + max(0, extra)


def _ramp_card_mana_per_turn(name: str, registry: EffectRegistry) -> float:
    """Extract mana_per_turn from a ramp card's registry entry.

    Counts ProduceMana, LandToBattlefield (treated as +N permanent mana/turn),
    and ReduceCost (treated as +amount mana/turn -- a -1 spell-cost reducer is
    modeled as a 1 mana/turn rock; justified over a long enough game).
    """
    entry = registry.get(name) if registry is not None else None
    if entry is None:
        return 0.0
    total = 0.0
    for eff in entry.on_play:
        if isinstance(eff, ProduceMana):
            total += float(eff.amount)
        elif isinstance(eff, LandToBattlefield):
            total += float(eff.count)
        elif isinstance(eff, ReduceCost):
            total += float(eff.amount)
    for eff in entry.per_turn:
        if isinstance(eff, ProduceMana):
            total += float(eff.amount)
    return total


def classify_for_curve_value(
    deck_list: List[Dict[str, Any]],
    registry: Optional[EffectRegistry] = None,
    overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Classify cards into curve_value's buckets.

    Returns a dict with:
      - D (effective deck size, commanders excluded)
      - L (land count)
      - V (value-pool count: non-land non-ramp non-draw, commanders excluded)
      - V_avg_cmc, V_curve
      - spendable_curve: non-land non-ramp main-deck spells, including draw
      - commander_spendable_curve: commanders, available outside the deck
      - ramp_specs: list[RampCardSpec] (only those with mana_per_turn > 0)
      - commanders: list[CommanderSpec]
      - draw_count
    """
    overrides = overrides or {}
    commanders: List[CommanderSpec] = []
    lands = 0
    ramp_specs: List[RampCardSpec] = []
    draw_count = 0
    value_cmcs: List[int] = []
    curve_counter: Dict[int, int] = {}
    spendable_counter: Dict[int, int] = {}
    commander_spendable_counter: Dict[int, int] = {}
    in_deck = 0

    for card in deck_list:
        name = card.get("name", "")
        cmc = int(card.get("cmc") or 0)
        types = card.get("types") or []
        qty = int(card.get("quantity", 1))
        is_land = "Land" in types
        is_commander = bool(card.get("commander"))

        if is_commander:
            for _ in range(qty):
                commanders.append(CommanderSpec(name=name, cmc=cmc))
                if not is_land and cmc > 0:
                    commander_spendable_counter[cmc] = (
                        commander_spendable_counter.get(cmc, 0) + 1
                    )
            continue

        for _ in range(qty):
            in_deck += 1
            if is_land:
                lands += 1
                continue

            override = overrides.get(name, {}) if overrides else {}
            override_cats = {
                cat.get("category")
                for cat in (override.get("categories") or [])
                if isinstance(cat, dict)
            }
            entry = registry.get(name) if registry is not None else None

            is_ramp_flag = "ramp" in override_cats or bool(entry and entry.ramp)
            is_draw_flag = "draw" in override_cats or bool(entry and entry.draw)

            mana_per_turn = _ramp_card_mana_per_turn(name, registry) if registry else 0.0

            # Promote to ramp only if we modeled non-zero mana/turn.
            if is_ramp_flag and mana_per_turn > 0:
                ramp_specs.append(RampCardSpec(name=name, cmc=cmc, mana_per_turn=mana_per_turn))
                continue

            if cmc > 0:
                spendable_counter[cmc] = spendable_counter.get(cmc, 0) + 1

            if is_draw_flag:
                draw_count += 1
                continue

            if cmc > 0:
                value_cmcs.append(cmc)
                curve_counter[cmc] = curve_counter.get(cmc, 0) + 1

    V_avg_cmc = float(sum(value_cmcs) / len(value_cmcs)) if value_cmcs else 0.0

    return {
        "D": in_deck,
        "L": lands,
        "V": len(value_cmcs),
        "V_avg_cmc": V_avg_cmc,
        "V_curve": curve_counter,
        "spendable_curve": spendable_counter,
        "commander_spendable_curve": commander_spendable_counter,
        "ramp_specs": ramp_specs,
        "commanders": commanders,
        "draw_count": draw_count,
    }


# ---------------------------------------------------------------------------
# Implied Draw
# ---------------------------------------------------------------------------

def ramp_contribution(c: float, M: float, T: int, D: int) -> float:
    """Expected per-slot mana contribution of a ramp card with cost c, M/turn.

    Sums over each deck position 1..D the contribution if drawn in that slot.
    Cards drawn after turn T contribute 0. Per spec we always cast when drawn,
    so a late-drawn ramp card can produce a negative net contribution.
    """
    total = 0.0
    for _ in range(min(OPENING_HAND, D)):
        cast = c
        if cast <= T:
            total += M * (T - cast) - c
    last_drawn_pos = OPENING_HAND + (T - 1) if ON_THE_PLAY else OPENING_HAND + T
    for p in range(OPENING_HAND + 1, last_drawn_pos + 1):
        if p > D:
            break
        t_draw = p - (OPENING_HAND - 1) if ON_THE_PLAY else p - OPENING_HAND
        cast = max(c, t_draw)
        if cast <= T:
            total += M * (T - cast) - c
    return total / D


def land_mana_over_T(L: int, D: int, T: int) -> float:
    """Expected total mana from lands across turns 1..T (one drop/turn cap)."""
    total = 0.0
    for t in range(1, T + 1):
        seen = cards_seen_by_turn(t)
        expected_lands = seen * L / D if D > 0 else 0.0
        total += min(t, expected_lands)
    return total


def cards_to_spend(target_mana: float, V: int, V_avg_cmc: float, D: int) -> float:
    """Expected total cards drawn to cover target_mana of value-pool spell
    costs.

    Drawing N total cards yields N * V/D value-pool cards in expectation,
    each at average CMC ``V_avg_cmc``, so for those to cover X mana we need
    N * V * V_avg_cmc / D >= X, i.e., N >= X * D / (V * V_avg_cmc).

    Note this is the *value-pool bottleneck* on N. The land bottleneck
    (``cards_for_land_drops``) is independent and the actual cards-required
    per turn is the max of the two -- see ``compute_implied_draw``.
    """
    if V <= 0 or V_avg_cmc <= 0 or target_mana <= 0 or D <= 0:
        return 0.0
    return target_mana * D / (V * V_avg_cmc)


def cards_for_land_drops(t: int, L: int, D: int) -> float:
    """Expected total cards drawn by turn t to have hit t land drops.

    Drawing N cards yields N * L/D lands in expectation; for that to be at
    least t we need N >= t * D / L. Returns 0 when L <= 0.

    This is the *land bottleneck* on cards-required: the deck must have drawn
    enough cards to find its t lands by turn t, regardless of how much mana
    it wants to spend on value spells. For most decks this dominates the
    early- and mid-game; the value bottleneck catches up by turn T.
    """
    if L <= 0 or D <= 0 or t <= 0:
        return 0.0
    return t * D / L


def ramp_excess_total(ramp_specs: List[RampCardSpec], T: int, D: int) -> float:
    return sum(ramp_contribution(r.cmc, r.mana_per_turn, T, D) for r in ramp_specs)


def compute_implied_draw(
    L: int,
    V: int,
    V_avg_cmc: float,
    ramp_specs: List[RampCardSpec],
    commanders: List[CommanderSpec],
    D: int,
    T: int,
    actual_per_turn_cumulative_draws: Optional[List[float]] = None,
    actual_total_draws: Optional[float] = None,
) -> ImpliedDrawResult:
    """Compute Implied Draw for a deck variant.

    `actual_per_turn_cumulative_draws[i]` is the MC-measured cumulative cards
    drawn by end of turn i+1 (length T). Optional; used for the comparison plot.
    """
    land_mana = land_mana_over_T(L, D, T)
    ramp_excess = ramp_excess_total(ramp_specs, T, D)
    total_mana = land_mana + ramp_excess
    commander_mana = float(sum(c.cmc for c in commanders if c.cmc <= T))
    value_mana = max(0.0, total_mana - commander_mana)

    # Per-turn cumulative cards required = max of two bottlenecks:
    #   1. Land bottleneck: enough cards drawn so that the L/D fraction
    #      yields >= t lands by turn t (you have to play your land drops).
    #   2. Value bottleneck: enough cards drawn so that the V/D fraction
    #      times average CMC covers cumulative value mana through turn t
    #      (you have to find spells to spend the leftover mana).
    # The ramp "bottleneck" is tautological under the natural draw rate
    # (the ramp_contribution math already weights by cards-seen probability),
    # so adding it as a separate constraint provides no information.
    # Running more ramp DOES inflate the value bottleneck though, because
    # ramp slots are taken from V (so V shrinks and n_for_value rises).
    per_turn_required: List[float] = []
    per_turn_natural: List[int] = []
    per_turn_lands_required: List[float] = []
    per_turn_value_required: List[float] = []
    for t in range(1, T + 1):
        land_t_mana = land_mana_over_T(L, D, t)
        ramp_t = sum(ramp_contribution(r.cmc, r.mana_per_turn, t, D) for r in ramp_specs)
        mana_t = land_t_mana + ramp_t
        cmd_t = float(sum(c.cmc for c in commanders if c.cmc <= t))
        value_mana_t = max(0.0, mana_t - cmd_t)
        n_for_lands = cards_for_land_drops(t, L, D)
        n_for_value = cards_to_spend(value_mana_t, V, V_avg_cmc, D)
        per_turn_lands_required.append(n_for_lands)
        per_turn_value_required.append(n_for_value)
        per_turn_required.append(max(n_for_lands, n_for_value))
        per_turn_natural.append(cards_seen_by_turn(t))

    # Headline N_max is the last-turn requirement.
    N_max = per_turn_required[-1] if per_turn_required else 0.0
    N_nat = cards_seen_by_turn(T)

    actual_deficit: Optional[float] = None
    if actual_total_draws is not None:
        actual_deficit = max(0.0, N_max - actual_total_draws)

    return ImpliedDrawResult(
        L=L, R=len(ramp_specs), V=V, D=D, V_avg_cmc=V_avg_cmc,
        land_mana=land_mana, ramp_excess=ramp_excess, total_mana=total_mana,
        commander_mana=commander_mana, value_mana=value_mana,
        N_natural=N_nat, N_max=N_max,
        deficit_max=max(0.0, N_max - N_nat),
        per_turn_required=per_turn_required,
        per_turn_natural=per_turn_natural,
        per_turn_lands_required=per_turn_lands_required,
        per_turn_value_required=per_turn_value_required,
        per_turn_actual=actual_per_turn_cumulative_draws,
        actual_total_draws=actual_total_draws,
        actual_deficit=actual_deficit,
    )


# ---------------------------------------------------------------------------
# Implied Spell Value (IRR)
# ---------------------------------------------------------------------------

def solve_irr(
    cash_flows: Dict[int, float],
    lo: float = IRR_LO,
    hi: float = IRR_HI,
    tol: float = IRR_TOL,
    max_iter: int = IRR_MAX_ITER,
) -> float:
    """Bisection root-finder for per-turn IRR. cash_flows: {turn: signed mana}."""

    def npv(r: float) -> float:
        return sum(amt / (1 + r) ** t for t, amt in cash_flows.items())

    f_lo, f_hi = npv(lo), npv(hi)
    if f_lo * f_hi > 0:
        return float("inf") if f_lo > 0 else float("-inf")
    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        f_mid = npv(mid)
        if abs(f_mid) < tol or (hi - lo) < tol:
            return mid
        if f_lo * f_mid < 0:
            hi, f_hi = mid, f_mid
        else:
            lo, f_lo = mid, f_mid
    return 0.5 * (lo + hi)


def ramp_irr(c: int, M: float, T: int) -> float:
    """Per-turn IRR of a ramp card cast on its CMC turn (idealized).

    Cash flow: -c on turn c, +M on turns c+1..T.
    Returns NaN if uncastable, -inf for pure loss, +inf for pure profit.
    """
    if c <= 0 or M <= 0 or c > T:
        return float("nan")
    cf: Dict[int, float] = {int(c): -float(c)}
    for t in range(int(c) + 1, T + 1):
        cf[t] = float(M)
    return solve_irr(cf)


def aggregate_deck_irr(
    ramp_specs: List[RampCardSpec],
    T: int,
    irr_cap: Optional[float] = None,
) -> Dict[str, float]:
    """Median IRR across the deck's permanent-ramp pieces.

    `irr_cap` clamps each individual piece's IRR before aggregation, defending
    against single-piece decks where one outlier (e.g. Sol Ring alone) drives
    the median to a saturated value. Default `None` preserves prior behavior;
    pass `DEFAULT_IRR_CAP` for the production tuning.
    """
    irrs: List[float] = []
    for r in ramp_specs:
        if r.mana_per_turn <= 0:
            continue
        rate = ramp_irr(r.cmc, r.mana_per_turn, T)
        if math.isnan(rate) or math.isinf(rate):
            # Treat unbounded-positive (always profitable) as IRR_HI; ignore inf-loss.
            if rate == float("inf"):
                rate = IRR_HI
            else:
                continue
        if irr_cap is not None:
            rate = min(rate, irr_cap)
        irrs.append(rate)
    if not irrs:
        return {"median_irr": float("nan"), "n_valid": 0}
    s = sorted(irrs)
    median = s[len(s) // 2] if len(s) % 2 == 1 else 0.5 * (s[len(s) // 2 - 1] + s[len(s) // 2])
    return {"median_irr": median, "n_valid": len(irrs), "min_irr": min(irrs), "max_irr": max(irrs)}


def implied_power_multipliers(
    delta: float,
    baseline_cmc: int = BASELINE_CMC,
    max_cmc: int = 8,
) -> Dict[int, float]:
    """Required intrinsic power per CMC c, normalized so multiplier(baseline)=1.

    multiplier(c) = (baseline * delta^baseline) / (c * delta^c)

    Higher delta (patient deck) flattens or inverts the curve. Lower delta
    (impatient deck) makes high-CMC slots demand more intrinsic power.
    """
    base_v = baseline_cmc * (delta ** baseline_cmc) if baseline_cmc > 0 else 1.0
    out: Dict[int, float] = {}
    for c in range(1, max_cmc + 1):
        v_c = c * (delta ** c)
        out[c] = base_v / v_c if v_c > 0 else float("inf")
    return out


def compute_implied_spell_value(
    ramp_specs: List[RampCardSpec],
    T: int,
    max_cmc: int = 8,
    baseline_cmc: int = BASELINE_CMC,
    irr_cap: Optional[float] = DEFAULT_IRR_CAP,
) -> ImpliedSpellValueResult:
    """Aggregate to deck-level IRR and derive per-CMC multipliers.

    Decks with no permanent ramp fall back to delta=1.0 (no time preference);
    the resulting multipliers reflect per-slot mana efficiency only.
    """
    per_card: List[PerCardIRR] = []
    for r in ramp_specs:
        if r.mana_per_turn <= 0:
            continue
        per_card.append(PerCardIRR(
            name=r.name, cmc=r.cmc, mana_per_turn=r.mana_per_turn,
            irr_per_turn=ramp_irr(r.cmc, r.mana_per_turn, T),
        ))

    agg = aggregate_deck_irr(ramp_specs, T, irr_cap=irr_cap)
    median_r = agg.get("median_irr", float("nan"))
    if math.isnan(median_r):
        delta = 1.0
        no_ramp = True
    else:
        delta = 1.0 / (1.0 + median_r)
        no_ramp = False

    mults = implied_power_multipliers(delta, baseline_cmc=baseline_cmc, max_cmc=max_cmc)

    return ImpliedSpellValueResult(
        median_irr=median_r,
        delta=delta,
        baseline_cmc=baseline_cmc,
        power_multipliers=mults,
        per_card_irrs=per_card,
        no_ramp=no_ramp,
    )


# ---------------------------------------------------------------------------
# Curve Verdict: Option A (duration-aware) + Option B (curve-aware) combined
# ---------------------------------------------------------------------------

def power_mults_option_a(
    delta: float,
    T: int,
    baseline_cmc: int = BASELINE_CMC,
    max_cmc: int = 8,
) -> Dict[int, float]:
    """Duration-aware required-power multiplier per CMC.

    v_A(c) = c * (T - c + 1) * delta^c  -- discounted mana-turns of board
    presence a c-drop cast on turn c provides over the remaining game.
    Returns multiplier(c) = v_A(baseline) / v_A(c), normalized to 1 at the
    baseline CMC. Curve-independent (no deck composition input).
    """

    def v(c: int) -> float:
        dur = max(0, T - c + 1)
        return c * dur * (delta ** c)

    base = v(baseline_cmc)
    out: Dict[int, float] = {}
    for c in range(1, max_cmc + 1):
        v_c = v(c)
        if v_c <= 0:
            out[c] = float("inf")
        else:
            out[c] = base / v_c
    return out


def schedule_ramp(
    ramp_pieces: List[tuple], T: int
) -> List[tuple]:
    """Schedule each ramp piece onto its CMC turn; push conflicts later.

    Inputs: (cmc, mana_per_turn) tuples. Output: (turn, cmc, mana_per_turn)
    tuples ordered by ramp cmc (and then by scheduled turn). Uncastable
    pieces (cmc > T or pushed past T) are dropped.
    """
    sched: List[tuple] = []
    used: set = set()
    for cmc, M in sorted(ramp_pieces, key=lambda x: x[0]):
        t = int(cmc)
        while t in used and t <= T:
            t += 1
        if t > T:
            continue
        sched.append((t, int(cmc), float(M)))
        used.add(t)
    return sched


def _scheduled_amount(item: tuple) -> float:
    return float(item[3]) if len(item) > 3 else 1.0


def value_mana_per_turn(ramp_schedule: List[tuple], T: int) -> List[float]:
    """Mana available for value spells at each turn 1..T.

    Lands contribute one drop per turn (idealized). Ramp already in play
    (cast on a prior turn) contributes its mana_per_turn. Ramp cast this
    turn deducts its CMC from the value-spell budget.
    """
    out: List[float] = []
    for t in range(1, T + 1):
        m = float(t)  # idealized one land drop per turn
        for item in ramp_schedule:
            sched_t, _c, M = item[:3]
            if sched_t < t:
                m += float(M) * _scheduled_amount(item)
        for item in ramp_schedule:
            sched_t, c, _M = item[:3]
            if sched_t == t:
                m -= float(c) * _scheduled_amount(item)
        out.append(max(0.0, m))
    return out


def _allocate_count_proportional(
    m_t: float, t: int, T: int, counts: Dict[int, float]
) -> Dict[str, Dict[int, float]]:
    """Split this turn's value mana proportional to remaining counts at each
    castable CMC. Returns ``{"cast": {c: cards_cast}, "mt": {c: mana_turns}}``.

    Mana-turns: each card cast on turn t contributes ``c * (T - t)`` of
    post-cast board presence.
    """
    castable = {c: n for c, n in counts.items() if c <= m_t and n > 1e-9}
    if not castable:
        return {"cast": {}, "mt": {}}
    total = sum(castable.values())
    cast: Dict[int, float] = {}
    mt: Dict[int, float] = {}
    for c, n in castable.items():
        share = m_t * n / total
        cards = min(share / c, n)
        cast[c] = cards
        mt[c] = cards * c * max(0, T - t)
    return {"cast": cast, "mt": mt}


def play_to_curve(
    curve_counts: Dict[int, float],
    ramp_pieces: List[tuple],
    T: int,
) -> Dict[str, Any]:
    """Simulate play-to-curve and return total mana-turns per CMC.

    Allocation rule is fixed at count-proportional (the §4 sweep showed it
    sits cleanly between the optimistic top_loaded and the pessimistic
    curve_shift rules and matches mana_proportional within ~10-20%).
    """
    schedule = schedule_ramp(ramp_pieces, T)
    mana_stream = value_mana_per_turn(schedule, T)
    counts_remaining: Dict[int, float] = {int(c): float(n) for c, n in curve_counts.items()}
    mt_per_cmc: Dict[int, float] = {}
    for t_idx, m_t in enumerate(mana_stream, start=1):
        if m_t <= 0:
            continue
        result = _allocate_count_proportional(m_t, t_idx, T, counts_remaining)
        for c, mt_c in result["mt"].items():
            mt_per_cmc[c] = mt_per_cmc.get(c, 0.0) + mt_c
        for c, n_cast in result["cast"].items():
            counts_remaining[c] = max(0.0, counts_remaining.get(c, 0.0) - n_cast)
    return {
        "mt_per_cmc": mt_per_cmc,
        "schedule": schedule,
        "mana_stream": mana_stream,
    }


def _replace_ramp_with_value(
    curve_counts: Dict[int, float], ramp_pieces: List[tuple]
) -> Dict[int, float]:
    """Counterfactual: each ramp piece becomes a same-cost value spell."""
    out = dict(curve_counts)
    for cmc, _M in ramp_pieces:
        out[int(cmc)] = out.get(int(cmc), 0.0) + 1.0
    return out


def _resolve_baseline_cmc(
    curve_counts: Dict[int, float], preferred: int = BASELINE_CMC
) -> Optional[int]:
    """Pick a baseline CMC. Default is preferred (2) when it has slots; else
    fall back to the smallest CMC with N(c) > 0. Returns None if the deck
    has no value spells at all (verdict undefined)."""
    if curve_counts.get(preferred, 0) > 0:
        return preferred
    castable = [c for c, n in curve_counts.items() if n > 0]
    return min(castable) if castable else None


def ramp_share_from_mana(land_mana: float, ramp_excess: float) -> float:
    """Fraction of total mana over T turns that came from ramp (B2 framing).

    Superseded for production by ``loan_size_alpha`` (B3) — kept because
    earlier callers and tests still consume it.
    """
    excess = max(0.0, ramp_excess)
    total = land_mana + excess
    return excess / total if total > 0 else 0.0


def loan_size_alpha(
    ramp_specs: List[RampCardSpec],
    threshold: float = DEFAULT_LOAN_THRESHOLD,
) -> float:
    """Legacy: B3 commitment factor from gross loan size. Kept for tests.

    The production verdict uses ``excess_alpha`` instead, because loan-size
    alpha saturates above ``threshold`` -- cutting ramp from a heavy deck
    has no visible effect until the loan crosses below the cliff.
    """
    if threshold <= 0:
        return 0.0
    loan = sum(s.cmc for s in ramp_specs if s.mana_per_turn > 0)
    return max(0.0, min(1.0, loan / threshold))


def idealized_ramp_excess(ramp_specs: List[RampCardSpec], T: int) -> float:
    """Net mana the deck's ramp produces over T turns, idealized.

    Per piece: ``M * (T - c) - c`` -- mana produced after cast, minus the
    cost paid on cast turn. Summed across ramp pieces with ``mana_per_turn
    > 0`` and ``cmc <= T``. Floored at 0 (a deck with net-negative ramp
    is rare and shouldn't drag alpha below 0).

    Cutting any positive-NPV ramp piece reduces excess monotonically, so
    excess-derived alpha shrinks on every cut -- the property the
    median/mean/portfolio-IRR aggregations don't have.
    """
    total = 0.0
    for s in ramp_specs:
        if s.mana_per_turn <= 0 or s.cmc > T:
            continue
        total += s.mana_per_turn * (T - s.cmc) - s.cmc
    return max(0.0, total)


def excess_alpha(
    ramp_excess: float,
    k: float = DEFAULT_EXCESS_K,
) -> float:
    """Commitment factor from net ramp excess. Smooth, never saturates.

    ``alpha = 1 - exp(-excess / k)``. Cutting any positive-NPV ramp piece
    reduces excess and therefore alpha; A_eff = 1 + alpha * (A_raw - 1)
    drops monotonically on any cut. k=30 puts heavy decks near 0.87 and
    low-ramp decks near 0.35 -- still distinguishable, no cliff.
    """
    if k <= 0:
        return 0.0
    return 1.0 - math.exp(-max(0.0, ramp_excess) / k)


def compute_curve_verdict(
    curve_counts: Dict[int, float],
    ramp_specs: List[RampCardSpec],
    T: int,
    baseline_cmc: int = BASELINE_CMC,
    coherence_tolerance: float = 0.10,
    ramp_share: Optional[float] = None,
    irr_cap: Optional[float] = None,
    delta_override: Optional[float] = None,
) -> Optional[CurveVerdict]:
    """Combine A (required) and B (implicit) into a per-CMC verdict.
    Returns None for decks with no value spells.

    Production (Option C): delta is fixed at ``DEFAULT_FIXED_DELTA`` and the
    commitment factor alpha is derived from the deck's idealized ramp excess
    via ``excess_alpha``. This makes A_eff monotonic in ramp cuts (every cut
    reduces excess and therefore alpha).

    Test overrides:
      - `ramp_share`: pass an explicit alpha to bypass the excess calc.
      - `delta_override`: pass an explicit delta to bypass the fixed anchor.
      - `irr_cap`: legacy hook for callers that still want the median-IRR
        delta path; only consulted when `delta_override` is also None and
        callers explicitly want delta from per-piece IRR aggregation.
    """
    resolved_baseline = _resolve_baseline_cmc(curve_counts, preferred=baseline_cmc)
    if resolved_baseline is None:
        return None

    has_ramp = any(s.mana_per_turn > 0 for s in ramp_specs)
    excess = idealized_ramp_excess(ramp_specs, T)
    no_ramp = not has_ramp

    if delta_override is not None:
        delta = delta_override
    elif no_ramp:
        delta = 1.0
    else:
        delta = DEFAULT_FIXED_DELTA

    # median_irr is preserved on the result for reporting, even though it no
    # longer drives the verdict math.
    agg = aggregate_deck_irr(ramp_specs, T, irr_cap=irr_cap)
    median_r = agg.get("median_irr", float("nan"))

    max_cmc_for_a = max(list(curve_counts.keys()) + [resolved_baseline])
    a_req = power_mults_option_a(
        delta, T=T, baseline_cmc=resolved_baseline, max_cmc=max_cmc_for_a
    )

    # Option B: with-ramp vs. counterfactual play-to-curve.
    ramp_pieces = [(r.cmc, r.mana_per_turn) for r in ramp_specs if r.mana_per_turn > 0]
    with_ramp = play_to_curve(curve_counts, ramp_pieces, T)
    counterfactual = _replace_ramp_with_value(curve_counts, ramp_pieces)
    no_ramp_run = play_to_curve(counterfactual, [], T)

    mt_with = with_ramp["mt_per_cmc"]
    mt_no = no_ramp_run["mt_per_cmc"]
    all_cmcs = sorted(set(mt_with.keys()) | set(mt_no.keys()) | set(curve_counts.keys()))
    deltas = {c: mt_with.get(c, 0.0) - mt_no.get(c, 0.0) for c in all_cmcs}
    net_flat = sum(deltas.values())
    loss = {c: -d for c, d in deltas.items() if d < -1e-9}
    gain = {c: d for c, d in deltas.items() if d > 1e-9}

    # B_implicit baseline: mana-turns per slot at the baseline CMC under the
    # with-ramp run. Undefined if the baseline slot has zero mt (which can
    # happen for a baseline pushed past T by ramp scheduling, but not in
    # practice for cmc 2). Fall back to a no-comparison row.
    baseline_n = curve_counts.get(resolved_baseline, 0)
    base_mt_per_slot = (
        mt_with.get(resolved_baseline, 0.0) / baseline_n if baseline_n > 0 else 0.0
    )

    if ramp_share is None:
        alpha = excess_alpha(excess) if has_ramp else 0.0
    else:
        alpha = max(0.0, min(1.0, ramp_share))

    rows: List[CurveVerdictRow] = []
    for c in sorted(curve_counts.keys()):
        n = curve_counts[c]
        if n <= 0:
            continue
        mt_per_slot = mt_with.get(c, 0.0) / n
        a_raw = a_req.get(c, float("nan"))
        a_val = (
            1.0 + alpha * (a_raw - 1.0)
            if not (math.isnan(a_raw) or math.isinf(a_raw))
            else a_raw
        )

        if base_mt_per_slot > 0 and mt_per_slot > 0:
            b_imp = base_mt_per_slot / mt_per_slot
        else:
            b_imp = None

        if c == resolved_baseline:
            kind = "baseline"
            gap_v = None
            slack_v = None
        elif c < resolved_baseline:
            kind = "below_baseline"
            gap_v = None
            slack_v = None
        elif math.isnan(a_val) or math.isinf(a_val):
            # c >= T -> duration term is 0 -> A_raw blows up. The slot is
            # structurally uncastable in the modeled game length; tag it as
            # no_slots rather than ramp_over_aggressive with an inf gap.
            kind = "no_slots"
            gap_v = None
            slack_v = None
        elif b_imp is None:
            kind = "no_slots"
            gap_v = None
            slack_v = None
        else:
            ratio = a_val / b_imp if b_imp > 0 else float("inf")
            if abs(ratio - 1.0) <= coherence_tolerance:
                kind = "coherent"
                gap_v = None
                slack_v = None
            elif b_imp < a_val:
                kind = "ramp_over_aggressive"
                gap_v = ratio
                slack_v = None
            else:
                kind = "over_allocated"
                gap_v = None
                slack_v = b_imp / a_val

        rows.append(CurveVerdictRow(
            cmc=c, n_cards=float(n), mt_per_slot=mt_per_slot,
            a_required=a_val, b_implicit=b_imp,
            kind=kind, gap=gap_v, slack=slack_v,
        ))

    loan = float(sum(s.cmc for s in ramp_specs if s.mana_per_turn > 0))

    return CurveVerdict(
        delta=delta,
        median_irr=median_r,
        baseline_cmc=resolved_baseline,
        no_ramp=no_ramp,
        T=T,
        net_flat=net_flat,
        ramp_share=alpha,
        loan_size=loan,
        idealized_excess=excess,
        loss_breakdown=loss,
        gain_breakdown=gain,
        rows=rows,
    )


# ---------------------------------------------------------------------------
# Turn Structure: post-cast turns of spendable-spell board presence
# ---------------------------------------------------------------------------


@dataclass
class TurnStructureRow:
    """Per-CMC comparison of post-cast turns of spendable-spell board presence.

    Ramp's own board presence is not credited. ``n_ramp_cards`` is the
    informational count of ramp pieces at this CMC. The counterfactual
    distributes ramp slots back across the spendable curve in proportion to the
    deck's existing spendable-spell shape, so its added cards at each CMC are
    fractional and tracked in ``counterfactual_added``.

    With a draw cap, ``cast`` values are fractional (expected counts under
    proportional draw of the deck's curve), and ``n_drawn`` denominators are
    expected drawn counts, not raw deck counts.
    """

    cmc: int
    n_value_cards: float
    n_ramp_cards: int
    counterfactual_added: float
    with_ramp_cast: float
    with_ramp_total_turns: float
    with_ramp_turns_per_cast: Optional[float]
    with_ramp_turns_per_drawn: Optional[float]
    counterfactual_cast: float
    counterfactual_total_turns: float
    counterfactual_turns_per_cast: Optional[float]
    counterfactual_turns_per_drawn: Optional[float]
    delta_turns: float


@dataclass
class TurnStructureResult:
    """Top-level result of the turn-structure comparison.

    ``with_ramp_*`` plays the deck as classified. The counterfactual replaces
    every ramp piece with a spendable spell sampled in proportion to the deck's
    existing spendable-curve shape -- so the spendable curve grows but keeps shape,
    and ramp's mana stream is removed. Both scenarios use the same
    top-of-curve allocator (cast biggest castable first, repeat until mana
    exhausted). "Spendable" means non-ramp spells; commanders are modeled as
    always available, while main-deck spendables are draw-capped.

    When ``D`` and a draw schedule are supplied, both scenarios cap
    castable cards at expected drawn count by turn (``N(c) * draws_t / D``)
    so totals reflect only cards expected to actually be in hand.
    """

    T: int
    rows: List[TurnStructureRow]
    with_ramp_total_turns: float
    counterfactual_total_turns: float
    delta_turns: float
    with_ramp_mana_stream: List[float]
    counterfactual_mana_stream: List[float]
    with_ramp_casts: List[tuple]
    counterfactual_casts: List[tuple]
    with_ramp_schedule: List[tuple]
    counterfactual_schedule: List[tuple]
    with_ramp_value_spend_by_turn: List[Dict[int, float]]
    counterfactual_value_spend_by_turn: List[Dict[int, float]]
    with_ramp_ramp_spend: List[float]
    counterfactual_ramp_spend: List[float]
    with_ramp_unused_mana: List[float]
    counterfactual_unused_mana: List[float]
    with_ramp_total_value_mana_spent: float
    counterfactual_total_value_mana_spent: float
    delta_value_mana_spent: float
    draw_capped: bool = False
    per_turn_cumulative_draws: Optional[List[float]] = None


def _allocate_top_of_curve(
    m_t: float, in_hand: Dict[int, float], eps: float = 1e-9
) -> Dict[int, float]:
    """Greedy top-of-curve allocator: cast biggest castable first.

    Supports fractional ``in_hand`` counts (so the counterfactual and the
    draw-capped allocator can use expected card counts). Mutates ``in_hand``;
    returns ``{cmc: cards_cast_this_turn}``.
    """
    cast: Dict[int, float] = {}
    budget = float(m_t)
    while budget > eps:
        choices = [c for c, n in in_hand.items() if c <= budget + eps and n > eps]
        if not choices:
            break
        c = max(choices)
        # cast up to one full card; budget may allow more on next iter.
        cast_amount = min(in_hand[c], 1.0, budget / c)
        if cast_amount <= eps:
            break
        in_hand[c] -= cast_amount
        budget -= cast_amount * c
        cast[c] = cast.get(c, 0.0) + cast_amount
    return cast


def _allocate_always_available(
    m_t: float, in_hand: Dict[int, float], eps: float = 1e-9
) -> Dict[int, float]:
    """Allocate command-zone spendables, allowing one-mana-short fractions.

    The draw-capped timeline mixes game states into expected mana. A commander
    that is castable in some states but one mana short in others can therefore
    sit just below its CMC in expectation. Model that as a fractional cast.
    """
    cast: Dict[int, float] = {}
    budget = float(m_t)
    while budget > eps:
        exact = [c for c, n in in_hand.items() if c <= budget + eps and n > eps]
        if exact:
            c = max(exact)
            cast_amount = min(in_hand[c], 1.0, budget / c)
        else:
            near = [
                c for c, n in in_hand.items()
                if c - 1.0 < budget < c and n > eps
            ]
            if not near:
                break
            c = max(near)
            cast_amount = min(in_hand[c], 1.0, budget - (c - 1.0), budget / c)
        if cast_amount <= eps:
            break
        in_hand[c] -= cast_amount
        budget -= cast_amount * c
        cast[c] = cast.get(c, 0.0) + cast_amount
    return cast


def _ramp_buckets(ramp_pieces: List[tuple], use_cap: bool) -> List[Dict[str, float]]:
    """Aggregate interchangeable ramp pieces for expected-availability scheduling."""
    buckets: Dict[tuple, Dict[str, float]] = {}
    for c, M in ramp_pieces:
        key = (int(c), float(M))
        bucket = buckets.setdefault(
            key,
            {
                "cmc": float(int(c)),
                "mana_per_turn": float(M),
                "count": 0.0,
                "available": 0.0,
                "cast_so_far": 0.0,
            },
        )
        bucket["count"] += 1.0
    out = sorted(buckets.values(), key=lambda b: (b["cmc"], b["mana_per_turn"]))
    if not use_cap:
        for bucket in out:
            bucket["available"] = bucket["count"]
    return out


def _play_to_curve_top_of_curve(
    curve_counts: Dict[int, float],
    ramp_pieces: List[tuple],
    T: int,
    D: Optional[int] = None,
    per_turn_cumulative_draws: Optional[List[float]] = None,
    always_available_counts: Optional[Dict[int, float]] = None,
) -> Dict[str, Any]:
    """Play-to-curve with top-of-curve allocation; record every cast.

    Without a draw cap (``D`` and per-turn draws both None) every card in
    ``curve_counts`` is in hand at t=1. With a cap, cards arrive each turn
    in proportion to the curve: ``delta(c, t) = N(c) * delta_draws[t] / D``.
    ``always_available_counts`` are in hand from turn 1 in both modes and
    are allocated before ramp setup; main-deck spendables are allocated after
    ramp setup.

    Returns ``casts`` (list of ``(turn, cmc, amount)``), ``schedule``,
    ``mana_stream``, and ``in_hand`` (remaining at end).
    """
    always_available_counts = always_available_counts or {}
    use_cap = D is not None and per_turn_cumulative_draws is not None and D > 0
    in_hand: Dict[int, float] = (
        {int(c): 0.0 for c in curve_counts}
        if use_cap
        else {int(c): float(n) for c, n in curve_counts.items()}
    )
    always_in_hand: Dict[int, float] = {
        int(c): float(n) for c, n in always_available_counts.items()
    }
    ramp_hand = _ramp_buckets(ramp_pieces, use_cap)

    casts: List[tuple] = []
    schedule: List[tuple] = []
    mana_stream: List[float] = []
    active_ramp_mana = 0.0
    prev_draws = 0.0
    for t_idx in range(1, T + 1):
        if use_cap:
            draws_t = float(per_turn_cumulative_draws[t_idx - 1])
            delta = max(0.0, draws_t - prev_draws)
            prev_draws = draws_t
            draw_share = delta / float(D)
            for ramp in ramp_hand:
                count = ramp["count"]
                p_card_seen = max(0.0, min(1.0, draws_t / float(D)))
                expected_drawn = count * p_card_seen
                p_any_drawn = 1.0 - ((1.0 - p_card_seen) ** count)
                ramp["available"] = max(
                    0.0,
                    min(expected_drawn - ramp["cast_so_far"], p_any_drawn),
                )
            for c, n in curve_counts.items():
                in_hand[int(c)] = in_hand.get(int(c), 0.0) + float(n) * draw_share

        total_budget = float(t_idx) + active_ramp_mana
        budget = total_budget
        commander_casts = _allocate_always_available(budget, always_in_hand)
        commander_spend = sum(int(c) * float(amt) for c, amt in commander_casts.items())
        budget = max(0.0, budget - commander_spend)
        for c, amt in commander_casts.items():
            casts.append((t_idx, c, amt))

        new_ramp_mana = 0.0
        ramp_spend = 0.0
        ramp_cast_capacity = float("inf") if use_cap else 1.0
        for ramp in ramp_hand:
            c = int(ramp["cmc"])
            if ramp_cast_capacity <= 1e-9:
                break
            if budget + 1e-9 < c or ramp["available"] <= 1e-9:
                continue
            cast_amount = min(ramp["available"], budget / c, ramp_cast_capacity)
            if cast_amount <= 1e-9:
                continue
            ramp["available"] -= cast_amount
            ramp["cast_so_far"] += cast_amount
            budget -= cast_amount * c
            ramp_spend += cast_amount * c
            new_ramp_mana += cast_amount * ramp["mana_per_turn"]
            schedule.append((t_idx, c, ramp["mana_per_turn"], cast_amount))
            ramp_cast_capacity -= cast_amount

        spendable_budget = max(0.0, budget)
        mana_stream.append(max(0.0, total_budget - ramp_spend))
        if spendable_budget <= 0:
            active_ramp_mana += new_ramp_mana
            continue
        per_cmc = _allocate_top_of_curve(spendable_budget, in_hand)
        for c, amt in per_cmc.items():
            casts.append((t_idx, c, amt))
        active_ramp_mana += new_ramp_mana

    return {
        "casts": casts,
        "schedule": schedule,
        "mana_stream": mana_stream,
        "in_hand": in_hand,
    }


def _curve_proportional_counterfactual(
    curve_counts: Dict[int, float], ramp_pieces: List[tuple]
) -> Dict[int, float]:
    """Distribute each ramp slot across the spendable curve proportionally.

    Each ramp piece becomes ``N(c) / sum(N)`` of a card at every CMC c that
    already has spendable spells, so total card count grows by ``len(ramp_pieces)``
    and curve shape is preserved exactly. Result counts are fractional.
    """
    out: Dict[int, float] = {int(c): float(n) for c, n in curve_counts.items()}
    total_value = sum(out.values())
    n_ramp = len(ramp_pieces)
    if total_value <= 0 or n_ramp == 0:
        return out
    for c in list(out.keys()):
        out[c] += n_ramp * out[c] / total_value
    # Floating-point: rescale to exact target if drift accumulates.
    target = total_value + n_ramp
    actual = sum(out.values())
    if actual > 0 and abs(actual - target) > 1e-9:
        scale = target / actual
        for c in out:
            out[c] *= scale
    return out


def _value_spend_by_turn(casts: List[tuple], T: int) -> List[Dict[int, float]]:
    """Return per-turn value mana spent by CMC from cast records."""
    out: List[Dict[int, float]] = [dict() for _ in range(T)]
    for t, c, amt in casts:
        if 1 <= t <= T:
            out[t - 1][int(c)] = out[t - 1].get(int(c), 0.0) + int(c) * float(amt)
    return out


def _ramp_spend_by_turn(schedule: List[tuple], T: int) -> List[float]:
    """Return per-turn mana spent casting ramp pieces."""
    out = [0.0 for _ in range(T)]
    for item in schedule:
        t, c, _M = item[:3]
        if 1 <= t <= T:
            out[t - 1] += float(c) * _scheduled_amount(item)
    return out


def _unused_mana_by_turn(
    mana_stream: List[float],
    value_spend_by_turn: List[Dict[int, float]],
) -> List[float]:
    """Return mana not spent on modeled spendable spells each turn."""
    out: List[float] = []
    for m_t, spends in zip(mana_stream, value_spend_by_turn):
        out.append(max(0.0, float(m_t) - sum(spends.values())))
    return out


def compute_turn_structure(
    curve_counts: Dict[int, float],
    ramp_specs: List[RampCardSpec],
    T: int,
    D: Optional[int] = None,
    per_turn_cumulative_draws: Optional[List[float]] = None,
    always_available_counts: Optional[Dict[int, float]] = None,
) -> TurnStructureResult:
    """Compare post-cast turns of spendable-spell board presence.

    For each CMC c, the row reports how many spendable spells get cast under each
    scenario and the total ``sum(T - cast_turn)`` over those casts. The
    counterfactual distributes each ramp piece's slot proportionally back
    across the deck's spendable curve, preserving shape and total card count.
    Always-available spells, such as commanders, are added to both scenarios
    but are not used as the shape for replacing ramp slots.

    If ``D`` and ``per_turn_cumulative_draws`` are supplied, cards are only
    available for casting in proportion to expected draws so totals reflect
    realistic hand availability.
    """
    always_available_counts = always_available_counts or {}
    ramp_pieces = [(r.cmc, r.mana_per_turn) for r in ramp_specs if r.mana_per_turn > 0]
    ramp_by_cmc: Dict[int, int] = {}
    for cmc, _M in ramp_pieces:
        ramp_by_cmc[int(cmc)] = ramp_by_cmc.get(int(cmc), 0) + 1

    with_run = _play_to_curve_top_of_curve(
        curve_counts, ramp_pieces, T,
        D=D, per_turn_cumulative_draws=per_turn_cumulative_draws,
        always_available_counts=always_available_counts,
    )

    counterfactual_counts = _curve_proportional_counterfactual(curve_counts, ramp_pieces)
    cf_run = _play_to_curve_top_of_curve(
        counterfactual_counts, [], T,
        D=D, per_turn_cumulative_draws=per_turn_cumulative_draws,
        always_available_counts=always_available_counts,
    )

    def agg(casts: List[tuple]) -> Dict[int, Dict[str, float]]:
        out: Dict[int, Dict[str, float]] = {}
        for t, c, amt in casts:
            d = out.setdefault(int(c), {"count": 0.0, "turns": 0.0})
            d["count"] += amt
            d["turns"] += amt * max(0, T - t)
        return out

    with_agg = agg(with_run["casts"])
    cf_agg = agg(cf_run["casts"])

    use_cap = D is not None and per_turn_cumulative_draws is not None and D > 0
    draws_T = float(per_turn_cumulative_draws[-1]) if use_cap else None

    all_cmcs = sorted(
        set(int(c) for c in curve_counts.keys())
        | set(int(c) for c in counterfactual_counts.keys())
        | set(int(c) for c in always_available_counts.keys())
    )
    rows: List[TurnStructureRow] = []
    for c in all_cmcs:
        n_deck = float(curve_counts.get(c, 0))
        n_always = float(always_available_counts.get(c, 0))
        n_value = n_deck + n_always
        n_ramp = int(ramp_by_cmc.get(c, 0))
        cf_deck_total = float(counterfactual_counts.get(c, 0.0))
        cf_total = cf_deck_total + n_always
        cf_added = cf_deck_total - n_deck

        if use_cap:
            n_drawn_with = n_deck * draws_T / float(D) + n_always
            n_drawn_cf = cf_deck_total * draws_T / float(D) + n_always
        else:
            n_drawn_with = n_value
            n_drawn_cf = cf_total

        w = with_agg.get(c, {"count": 0.0, "turns": 0.0})
        k = cf_agg.get(c, {"count": 0.0, "turns": 0.0})
        w_cast = float(w["count"])
        k_cast = float(k["count"])
        w_turns = float(w["turns"])
        k_turns = float(k["turns"])
        rows.append(TurnStructureRow(
            cmc=c,
            n_value_cards=n_value,
            n_ramp_cards=n_ramp,
            counterfactual_added=cf_added,
            with_ramp_cast=w_cast,
            with_ramp_total_turns=w_turns,
            with_ramp_turns_per_cast=(w_turns / w_cast) if w_cast > 1e-9 else None,
            with_ramp_turns_per_drawn=(w_turns / n_drawn_with) if n_drawn_with > 1e-9 else None,
            counterfactual_cast=k_cast,
            counterfactual_total_turns=k_turns,
            counterfactual_turns_per_cast=(k_turns / k_cast) if k_cast > 1e-9 else None,
            counterfactual_turns_per_drawn=(k_turns / n_drawn_cf) if n_drawn_cf > 1e-9 else None,
            delta_turns=w_turns - k_turns,
        ))

    total_with = sum(r.with_ramp_total_turns for r in rows)
    total_cf = sum(r.counterfactual_total_turns for r in rows)
    with_spend = _value_spend_by_turn(with_run["casts"], T)
    cf_spend = _value_spend_by_turn(cf_run["casts"], T)
    with_value_spent = sum(sum(turn.values()) for turn in with_spend)
    cf_value_spent = sum(sum(turn.values()) for turn in cf_spend)
    return TurnStructureResult(
        T=T,
        rows=rows,
        with_ramp_total_turns=total_with,
        counterfactual_total_turns=total_cf,
        delta_turns=total_with - total_cf,
        with_ramp_mana_stream=list(with_run["mana_stream"]),
        counterfactual_mana_stream=list(cf_run["mana_stream"]),
        with_ramp_casts=list(with_run["casts"]),
        counterfactual_casts=list(cf_run["casts"]),
        with_ramp_schedule=list(with_run["schedule"]),
        counterfactual_schedule=list(cf_run["schedule"]),
        with_ramp_value_spend_by_turn=with_spend,
        counterfactual_value_spend_by_turn=cf_spend,
        with_ramp_ramp_spend=_ramp_spend_by_turn(with_run["schedule"], T),
        counterfactual_ramp_spend=_ramp_spend_by_turn(cf_run["schedule"], T),
        with_ramp_unused_mana=_unused_mana_by_turn(with_run["mana_stream"], with_spend),
        counterfactual_unused_mana=_unused_mana_by_turn(cf_run["mana_stream"], cf_spend),
        with_ramp_total_value_mana_spent=with_value_spent,
        counterfactual_total_value_mana_spent=cf_value_spent,
        delta_value_mana_spent=with_value_spent - cf_value_spent,
        draw_capped=use_cap,
        per_turn_cumulative_draws=(
            list(per_turn_cumulative_draws) if use_cap else None
        ),
    )


# ---------------------------------------------------------------------------
# Implied Ramp
# ---------------------------------------------------------------------------

ROCK_CMC = 2
ROCK_MANA_PER_TURN = 1.0


def ramp_to_rock_equivalents(ramp_specs: List[RampCardSpec], T: int) -> float:
    """Convert the deck's ramp package to 2-mana-rock equivalents.

    Each piece's idealized excess ``M*(T-c) - c`` is divided by one rock's
    excess ``1*(T-2) - 2 = T-4``. Pieces with cmc > T or M <= 0 contribute 0.
    Negative-excess pieces are floored at 0 so a single bad rock doesn't
    negate the value of the rest.
    """
    one_rock = ROCK_MANA_PER_TURN * (T - ROCK_CMC) - ROCK_CMC
    if one_rock <= 0:
        return 0.0
    total = 0.0
    for s in ramp_specs:
        if s.mana_per_turn <= 0 or s.cmc > T:
            continue
        excess = s.mana_per_turn * (T - s.cmc) - s.cmc
        if excess > 0:
            total += excess
    return total / one_rock


def _scale_curve(V_curve: Dict[int, int], V_slots: float) -> Dict[int, float]:
    """Rescale ``V_curve`` so the slot total equals ``V_slots``."""
    total = sum(V_curve.values())
    if total <= 0 or V_slots <= 0:
        return {int(c): 0.0 for c in V_curve}
    factor = V_slots / total
    return {int(c): float(n) * factor for c, n in V_curve.items()}


def _simulate_float_stuck(
    L: int,
    scaled_curve: Dict[int, float],
    R: float,
    D: int,
    T: int,
    commanders: List[CommanderSpec],
    stuck_mode: str = DEFAULT_STUCK_MODE,
) -> tuple:
    """Expected float/stuck mana-units over T turns for a counterfactual deck."""
    if stuck_mode not in STUCK_MODES:
        raise ValueError(
            f"stuck_mode must be one of {STUCK_MODES}, got {stuck_mode!r}"
        )
    hand_curve: Dict[int, float] = {int(c): 0.0 for c in scaled_curve}
    hand_rocks = 0.0
    hand_lands = 0.0
    lands_in_play = 0.0
    rocks_in_play = 0.0
    cmd_to_cast: List[int] = sorted([c.cmc for c in commanders if 0 < c.cmc <= T])

    float_cost = 0.0
    stuck_cost = 0.0
    cards_seen_prev = 0
    stuck_mass_prev: Dict[int, float] = {int(c): 0.0 for c in scaled_curve}

    for t in range(1, T + 1):
        seen = cards_seen_by_turn(t)
        new_cards = seen - cards_seen_prev
        cards_seen_prev = seen

        if D > 0:
            for c in hand_curve:
                hand_curve[c] += new_cards * scaled_curve.get(c, 0.0) / D
            hand_rocks += new_cards * R / D
            hand_lands += new_cards * L / D

        land_drop = min(hand_lands, max(0.0, t - lands_in_play), 1.0)
        hand_lands -= land_drop
        lands_in_play += land_drop

        m_t = lands_in_play + rocks_in_play

        if cmd_to_cast and cmd_to_cast[0] <= m_t:
            m_t -= cmd_to_cast.pop(0)

        if hand_rocks > 0 and m_t >= ROCK_CMC:
            rocks_can_play = min(hand_rocks, m_t / ROCK_CMC)
            hand_rocks -= rocks_can_play
            m_t -= rocks_can_play * ROCK_CMC
            rocks_in_play += rocks_can_play

        for c in sorted(hand_curve.keys(), reverse=True):
            if c <= 0 or hand_curve[c] <= 0 or m_t < c:
                continue
            n_cast = min(hand_curve[c], m_t / c)
            hand_curve[c] -= n_cast
            m_t -= n_cast * c
            if m_t <= 0:
                break

        float_cost += max(0.0, m_t)

        max_cast = lands_in_play + rocks_in_play
        for c, n in hand_curve.items():
            stuck_here = c > max_cast and n > 0
            if stuck_mode == STUCK_MODE_UNIFORM:
                if stuck_here:
                    stuck_cost += c * n
            elif stuck_mode == STUCK_MODE_TURN_DECAY:
                if stuck_here:
                    stuck_cost += (c * n) / t
            elif stuck_mode == STUCK_MODE_PER_CARD_CAP:
                if stuck_here:
                    current_mass = c * n
                    delta = current_mass - stuck_mass_prev.get(c, 0.0)
                    if delta > 0:
                        stuck_cost += delta
                    stuck_mass_prev[c] = current_mass
                else:
                    stuck_mass_prev[c] = 0.0
            elif stuck_mode == STUCK_MODE_MANA_GAP:
                if stuck_here:
                    stuck_cost += (c - max_cast) * n

    return float_cost, stuck_cost


def compute_implied_ramp(
    L: int,
    V_curve: Dict[int, int],
    ramp_specs: List[RampCardSpec],
    commanders: List[CommanderSpec],
    D: int,
    T: int,
    R_max: Optional[int] = None,
    stuck_mode: str = DEFAULT_STUCK_MODE,
) -> ImpliedRampResult:
    """Sweep R over [0, R_max] and return the cost minimizer.

    The flex-slot pool is ``V_total + len(ramp_specs)`` -- all non-land,
    non-commander slots in the original deck. Each R uses R rocks plus
    (flex - R) value slots scaled from the original curve. R_max defaults
    to flex.
    """
    V_total = int(sum(V_curve.values()))
    flex = V_total + len(ramp_specs)
    if R_max is None:
        R_max = flex
    R_max = max(0, min(R_max, flex))

    R_actual = ramp_to_rock_equivalents(ramp_specs, T)

    R_grid: List[int] = list(range(0, R_max + 1))
    float_curve: List[float] = []
    stuck_curve: List[float] = []
    for R in R_grid:
        V_slots = float(flex - R)
        scaled = _scale_curve(V_curve, V_slots)
        f, s = _simulate_float_stuck(
            L, scaled, float(R), D, T, commanders, stuck_mode=stuck_mode
        )
        float_curve.append(f)
        stuck_curve.append(s)

    total_curve = [f + s for f, s in zip(float_curve, stuck_curve)]
    best_idx = min(range(len(total_curve)), key=lambda i: total_curve[i])
    R_star = R_grid[best_idx]
    delta = R_star - R_actual
    if abs(delta) <= 1.0:
        verdict = "right_sized"
    elif delta > 0:
        verdict = "under_ramped"
    else:
        verdict = "over_ramped"

    return ImpliedRampResult(
        T=T,
        R_actual=R_actual,
        R_star=R_star,
        R_grid=R_grid,
        float_curve=float_curve,
        stuck_curve=stuck_curve,
        total_curve=total_curve,
        verdict=verdict,
        delta_rocks=delta,
        stuck_mode=stuck_mode,
    )


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------

def compute_curve_value(
    deck_list: List[Dict[str, Any]],
    registry: Optional[EffectRegistry] = None,
    overrides: Optional[Dict[str, Any]] = None,
    turns: int = 8,
    actual_total_draws: Optional[float] = None,
    actual_per_turn_cumulative_draws: Optional[List[float]] = None,
    max_cmc: Optional[int] = None,
) -> CurveValueResult:
    """End-to-end: classify the deck, compute Implied Draw and Implied Spell Value."""
    cls = classify_for_curve_value(deck_list, registry=registry, overrides=overrides)

    implied_draw = compute_implied_draw(
        L=cls["L"], V=cls["V"], V_avg_cmc=cls["V_avg_cmc"],
        ramp_specs=cls["ramp_specs"], commanders=cls["commanders"],
        D=cls["D"], T=turns,
        actual_per_turn_cumulative_draws=actual_per_turn_cumulative_draws,
        actual_total_draws=actual_total_draws,
    )

    if max_cmc is None:
        curve_keys = list(cls["V_curve"].keys()) or [BASELINE_CMC]
        cmd_cmcs = [c.cmc for c in cls["commanders"]] or [BASELINE_CMC]
        max_cmc = max(curve_keys + cmd_cmcs + [BASELINE_CMC])

    implied_spell_value = compute_implied_spell_value(
        ramp_specs=cls["ramp_specs"],
        T=turns,
        max_cmc=max_cmc,
        baseline_cmc=BASELINE_CMC,
        irr_cap=DEFAULT_IRR_CAP,
    )

    # Production verdict (Option C): fixed delta + excess-based alpha. The
    # verdict computes alpha internally when `ramp_share` is None.
    curve_verdict = compute_curve_verdict(
        curve_counts={int(c): float(n) for c, n in cls["V_curve"].items()},
        ramp_specs=cls["ramp_specs"],
        T=turns,
        baseline_cmc=BASELINE_CMC,
    )

    turn_structure = compute_turn_structure(
        curve_counts={int(c): float(n) for c, n in cls["spendable_curve"].items()},
        ramp_specs=cls["ramp_specs"],
        T=turns,
        D=cls["D"],
        per_turn_cumulative_draws=(
            implied_draw.per_turn_actual or implied_draw.per_turn_natural
        ),
        always_available_counts={
            int(c): float(n) for c, n in cls["commander_spendable_curve"].items()
        },
    )

    implied_ramp = compute_implied_ramp(
        L=cls["L"],
        V_curve={int(c): int(n) for c, n in cls["V_curve"].items()},
        ramp_specs=cls["ramp_specs"],
        commanders=cls["commanders"],
        D=cls["D"],
        T=turns,
    )

    return CurveValueResult(
        turns=turns,
        deck_size_effective=cls["D"],
        implied_draw=implied_draw,
        implied_spell_value=implied_spell_value,
        curve_verdict=curve_verdict,
        turn_structure=turn_structure,
        implied_ramp=implied_ramp,
    )
