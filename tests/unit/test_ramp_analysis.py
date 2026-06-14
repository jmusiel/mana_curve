"""Tests for src/auto_goldfish/optimization/ramp_analysis.py."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from auto_goldfish.optimization.curve_value import CommanderSpec
from auto_goldfish.optimization.ramp_analysis import (
    RampBucketStats,
    RampMCPanel,
    RampVariant,
    _build_callouts,
    build_ramp_variants,
    classify_ramp_tradeoff_input,
    combined_mana_util,
    compute_ramp_tradeoff,
    compute_ramp_mc_panel,
    compute_ramp_panel,
    expected_rocks_in_bucket,
    hypergeo_pmf,
    ramp_draw_probabilities,
    redistribute_curve,
    simulate_ramp_conditional,
)


def _load_plot_demo_module():
    path = Path(__file__).resolve().parents[2] / "scripts" / "plot_ramp_analysis_demo.py"
    spec = importlib.util.spec_from_file_location("plot_ramp_analysis_demo", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Hypergeometric / probability bucketing
# ---------------------------------------------------------------------------

def test_hypergeo_pmf_known_value():
    # 10-card deck with 3 successes, draw 5: P(K=2) = C(3,2)*C(7,3)/C(10,5)
    # = 3 * 35 / 252 = 0.4166...
    assert abs(hypergeo_pmf(10, 3, 5, 2) - 105 / 252) < 1e-9


def test_hypergeo_pmf_no_successes():
    assert hypergeo_pmf(99, 0, 11, 0) == 1.0
    assert hypergeo_pmf(99, 0, 11, 1) == 0.0


def test_ramp_draw_probabilities_sum_to_one():
    probs = ramp_draw_probabilities(D=99, R=11, n_draws=11, k_max_bucket=3)
    assert abs(sum(probs.values()) - 1.0) < 1e-9
    assert set(probs.keys()) == {0, 1, 2, 3}


def test_ramp_draw_probabilities_no_rocks_all_mass_at_zero():
    probs = ramp_draw_probabilities(D=99, R=0, n_draws=11, k_max_bucket=3)
    assert probs[0] == 1.0
    assert all(probs[b] == 0.0 for b in (1, 2, 3))


def test_ramp_draw_probabilities_more_draws_shifts_mass_to_higher_buckets():
    """When the deck sees more cards (cantrips, draw effects), P(K=0) must
    fall and P(K>=3) must rise -- monotonically. This is the headline
    behavioral change the deck-draw-signature wiring is meant to expose."""
    low = ramp_draw_probabilities(D=99, R=11, n_draws=11)
    high = ramp_draw_probabilities(D=99, R=11, n_draws=14)
    assert high[0] < low[0]
    assert high[3] > low[3]
    # Each probability vector still sums to 1.
    assert abs(sum(low.values()) - 1.0) < 1e-9
    assert abs(sum(high.values()) - 1.0) < 1e-9


def test_ramp_draw_probabilities_hermes_calibrated_magnitudes():
    """Pin the magnitudes for the hermes calibration point (D=99, R=11).
    Measured by the main simulator at turn 5: ~14 cards seen. The shift
    versus the natural-rate baseline (n_draws=11) is large: P(K=0) drops
    from ~25% to ~17%, P(K>=3) rises from ~10% to ~19%."""
    natural = ramp_draw_probabilities(D=99, R=11, n_draws=11)
    measured = ramp_draw_probabilities(D=99, R=11, n_draws=14)
    # Natural: ~25/39/25/10 percent.
    assert 0.24 < natural[0] < 0.27
    assert 0.09 < natural[3] < 0.12
    # Measured: ~17/35/30/19 percent.
    assert 0.15 < measured[0] < 0.19
    assert 0.17 < measured[3] < 0.20


def test_expected_rocks_in_bucket_below_max_is_index():
    # For non-overflow buckets, E[K|bucket=b] is just b.
    for b in (0, 1, 2):
        assert expected_rocks_in_bucket(99, 11, 11, b, k_max_bucket=3) == float(b)


def test_expected_rocks_in_bucket_overflow_is_conditional_mean():
    # E[K | K>=3] for hypergeo(99, 11, 11) is between 3 and 11.
    ek = expected_rocks_in_bucket(99, 11, 11, 3, k_max_bucket=3)
    assert 3.0 <= ek <= 11.0


# ---------------------------------------------------------------------------
# Curve redistribution
# ---------------------------------------------------------------------------

def test_redistribute_curve_preserves_shape_when_adding():
    curve = {2: 10.0, 3: 20.0, 4: 10.0}
    new = redistribute_curve(curve, n_swap=4)
    # Total grows by 4, shape preserved: each bucket grows in proportion.
    assert abs(sum(new.values()) - 44.0) < 1e-9
    # cmc 3 (50% of mass) gets +2; cmc 2 and 4 (25% each) get +1.
    assert abs(new[3] - 22.0) < 1e-9
    assert abs(new[2] - 11.0) < 1e-9
    assert abs(new[4] - 11.0) < 1e-9


def test_redistribute_curve_removing_proportional():
    curve = {2: 10.0, 3: 20.0, 4: 10.0}
    new = redistribute_curve(curve, n_swap=-4)
    assert abs(sum(new.values()) - 36.0) < 1e-9
    assert abs(new[3] - 18.0) < 1e-9


def test_redistribute_curve_empty_safe():
    assert redistribute_curve({}, n_swap=5) == {}


def test_redistribute_curve_floors_at_zero():
    curve = {2: 1.0}
    new = redistribute_curve(curve, n_swap=-10)
    assert new[2] == 0.0


# ---------------------------------------------------------------------------
# Variant building
# ---------------------------------------------------------------------------

def test_build_ramp_variants_includes_full_range():
    variants = build_ramp_variants(base_R=10, spendable_curve={2: 30.0, 3: 20.0})
    labels = [v.label for v in variants]
    assert "current" in labels
    assert "+3 Signets" in labels
    assert "-3 Signets" in labels
    assert len(variants) == 7


def test_build_ramp_variants_conserves_slot_pool():
    # Each variant should have R + total_value_slots == base_R + base_value.
    base_V = {2: 30.0, 3: 20.0}
    base_R = 10
    base_pool = base_R + sum(base_V.values())
    for v in build_ramp_variants(base_R=base_R, spendable_curve=base_V):
        pool = v.R + sum(v.spendable_curve.values())
        assert abs(pool - base_pool) < 1e-9


def test_build_ramp_variants_clips_negative_R():
    variants = build_ramp_variants(base_R=1, spendable_curve={2: 30.0})
    for v in variants:
        assert v.R >= 0
    assert [v.R for v in variants] == [0, 1, 2, 3, 4]


def test_build_ramp_variants_include_no_ramp_prepends_zero_rock_variant():
    variants = build_ramp_variants(
        base_R=11, spendable_curve={3: 30.0, 4: 20.0}, include_no_ramp=True,
    )
    # 7 sweep variants + 1 no_ramp = 8 total.
    assert len(variants) == 8
    assert variants[0].label == "no_ramp"
    assert variants[0].R == 0
    assert variants[0].delta_rocks == -11
    # All rocks redistributed into the value pool -> total V grows by 11.
    base_total = 30.0 + 20.0
    new_total = sum(variants[0].spendable_curve.values())
    assert abs(new_total - (base_total + 11)) < 1e-9


def test_build_ramp_variants_include_no_ramp_skipped_when_redundant():
    """If the -3 column already lands at R=0 (base_R <= 3), no_ramp would
    duplicate it -- skip rather than add a redundant column."""
    variants = build_ramp_variants(
        base_R=3, spendable_curve={3: 30.0}, include_no_ramp=True,
    )
    labels = [v.label for v in variants]
    assert "no_ramp" not in labels
    assert len(variants) == 7


def test_build_ramp_variants_zero_ramp_is_add_only_from_current():
    variants = build_ramp_variants(
        base_R=0, spendable_curve={3: 30.0}, include_no_ramp=True,
    )
    assert [v.label for v in variants] == ["current", "+1 Signet", "+2 Signets", "+3 Signets"]
    assert [v.R for v in variants] == [0, 1, 2, 3]


# ---------------------------------------------------------------------------
# Conditional simulator
# ---------------------------------------------------------------------------

def test_simulate_ramp_conditional_land_priority_invariant():
    """If rock_util > 0 anywhere, then land_util reached 1.0 on the turn
    rock was spent. Aggregate check: if rock was spent, total land available
    was fully consumed at least once -- so total land spent should equal
    total land available *up to and including that turn*. Weak aggregate
    check: rock_spent > 0 ==> land_util >= 0.5 (avoids edge cases where the
    deck has tons of unused early land mana)."""
    curve = {2: 10.0, 3: 10.0, 4: 10.0}
    # A deck heavy enough at the top end to need rock mana.
    outcome = simulate_ramp_conditional(
        L=35, R=10, spendable_curve=curve, k_phase1=2.0,
        commanders=[], D=99, T=8,
    )
    if outcome.rock_mana_spent > 1e-6:
        # If rock mana got spent, land mana must have been mostly used.
        assert outcome.land_util >= 0.5


def test_simulate_ramp_conditional_zero_rock_scenario_has_zero_rock_mana():
    outcome = simulate_ramp_conditional(
        L=35, R=10, spendable_curve={3: 30.0}, k_phase1=0.0,
        commanders=[], D=99, T=8,
    )
    # Phase 1 contributes no rocks; phase 2 still draws from remaining
    # rock pool though, so some rocks may enter play late.
    # But rock_mana_available should be much smaller than if we'd
    # conditioned on many rocks early.
    big = simulate_ramp_conditional(
        L=35, R=10, spendable_curve={3: 30.0}, k_phase1=3.0,
        commanders=[], D=99, T=8,
    )
    assert outcome.rock_mana_available < big.rock_mana_available


def test_simulate_ramp_conditional_no_value_no_stuck():
    outcome = simulate_ramp_conditional(
        L=35, R=0, spendable_curve={}, k_phase1=0.0,
        commanders=[], D=99, T=8,
    )
    assert outcome.stuck_cards == 0.0


def test_simulate_ramp_conditional_signature_increases_land_mana_available():
    """When the deck sees more cards per turn (a cantrip-heavy signature),
    land density per draw stays the same but cumulative non-rock draws by
    turn 5 grow -- so by the same turn more lands should have been found
    and dropped. Land mana available aggregated over T should grow.
    """
    curve = {3: 30.0}
    natural = simulate_ramp_conditional(
        L=35, R=10, spendable_curve=curve, k_phase1=1.0,
        commanders=[], D=99, T=8,
        per_turn_cumulative_draws=None,
    )
    # Hermes-like signature (T1=8.4 grows to T5=14.45).
    sig = [8.4, 9.7, 11.1, 12.7, 14.5, 16.4, 18.5, 20.5]
    cantripping = simulate_ramp_conditional(
        L=35, R=10, spendable_curve=curve, k_phase1=1.0,
        commanders=[], D=99, T=8,
        per_turn_cumulative_draws=sig,
        phase1_cards=14,
    )
    assert cantripping.land_mana_available > natural.land_mana_available


def test_simulate_ramp_conditional_no_signature_matches_natural_default():
    """Passing no signature must produce the same numbers as before --
    this is the regression guard for callers that don't opt in."""
    args = dict(
        L=35, R=10, spendable_curve={3: 30.0}, k_phase1=1.5,
        commanders=[], D=99, T=8,
    )
    a = simulate_ramp_conditional(**args)
    b = simulate_ramp_conditional(**args, per_turn_cumulative_draws=None)
    assert a.land_mana_available == b.land_mana_available
    assert a.rock_mana_available == b.rock_mana_available
    assert a.unspent_mana == b.unspent_mana
    assert a.stuck_cards == b.stuck_cards


# ---------------------------------------------------------------------------
# Panel
# ---------------------------------------------------------------------------

def test_compute_ramp_panel_probs_sum_to_one():
    variant = RampVariant(label="current", delta_rocks=0, R=10, spendable_curve={3: 50.0})
    panel = compute_ramp_panel(
        variant=variant, L=35, commanders=[], D=99, T=8,
    )
    assert abs(sum(panel.scenario_probs.values()) - 1.0) < 1e-9
    # Outcomes recorded for all four buckets.
    assert set(panel.outcomes.keys()) == {0, 1, 2, 3}


def test_compute_ramp_panel_expected_unspent_is_p_weighted():
    variant = RampVariant(label="current", delta_rocks=0, R=5, spendable_curve={3: 50.0})
    panel = compute_ramp_panel(
        variant=variant, L=35, commanders=[], D=99, T=8,
    )
    manual = sum(
        panel.scenario_probs[b] * panel.outcomes[b].unspent_mana for b in panel.outcomes
    )
    assert abs(panel.expected_unspent_mana - manual) < 1e-9


def test_compute_ramp_panel_signature_overrides_n_draws():
    """A signature with T5 cumulative ~14 must produce the same probability
    vector as calling ramp_draw_probabilities directly with n_draws=14."""
    variant = RampVariant(label="current", delta_rocks=0, R=11, spendable_curve={3: 40.0})
    sig = [8.4, 9.7, 11.1, 12.7, 14.45, 16.4, 18.5, 20.5]
    panel = compute_ramp_panel(
        variant=variant, L=35, commanders=[], D=99, T=8,
        per_turn_cumulative_draws=sig,
    )
    expected = ramp_draw_probabilities(D=99, R=11, n_draws=14)
    for b in (0, 1, 2, 3):
        assert abs(panel.scenario_probs[b] - expected[b]) < 1e-9


# ---------------------------------------------------------------------------
# Combined mana_util
# ---------------------------------------------------------------------------

def test_combined_mana_util_full_land_full_rock_is_one():
    assert combined_mana_util(10.0, 10.0, 4.0, 4.0) == 1.0


def test_combined_mana_util_land_deficit_is_negative():
    # Half the land mana was unspent -> -0.5; rock activity ignored.
    assert combined_mana_util(10.0, 5.0, 4.0, 4.0) == -0.5


def test_combined_mana_util_full_land_no_rocks_is_zero():
    assert combined_mana_util(10.0, 10.0, 0.0, 0.0) == 0.0


def test_combined_mana_util_no_land_uses_rock_share():
    # Pathological: zero land, half rocks spent.
    assert combined_mana_util(0.0, 0.0, 4.0, 2.0) == 0.5


def test_combined_mana_util_zero_safe():
    assert combined_mana_util(0.0, 0.0, 0.0, 0.0) == 0.0


# ---------------------------------------------------------------------------
# Monte Carlo panel
# ---------------------------------------------------------------------------

def test_ramp_mc_panel_samples_sum_to_n_trials():
    variant = RampVariant(label="current", delta_rocks=0, R=10, spendable_curve={3: 50.0})
    panel = compute_ramp_mc_panel(
        variant=variant, L=35, commanders=[], D=99, T=8, n_trials=400, seed=1,
    )
    total_samples = sum(s.n_samples for s in panel.bucket_stats.values())
    assert total_samples == 400


def test_ramp_mc_panel_probs_are_analytical():
    """Analytical scenario probabilities (not MC frequencies)."""
    variant = RampVariant(label="current", delta_rocks=0, R=11, spendable_curve={3: 40.0})
    panel = compute_ramp_mc_panel(
        variant=variant, L=35, commanders=[], D=99, T=8, n_trials=200, seed=1,
    )
    assert abs(sum(panel.scenario_probs.values()) - 1.0) < 1e-9


def test_ramp_mc_panel_higher_R_lowers_p_zero():
    """More rocks in the deck => lower P(K=0) by turn 5."""
    low = compute_ramp_mc_panel(
        variant=RampVariant(label="low", delta_rocks=0, R=3, spendable_curve={3: 50.0}),
        L=35, commanders=[], D=99, T=8, n_trials=200, seed=1,
    )
    high = compute_ramp_mc_panel(
        variant=RampVariant(label="high", delta_rocks=0, R=15, spendable_curve={3: 50.0}),
        L=35, commanders=[], D=99, T=8, n_trials=200, seed=1,
    )
    assert high.scenario_probs[0] < low.scenario_probs[0]


def test_ramp_mc_panel_signature_increases_draw_count_on_avg():
    """A cantrip-heavy signature must cause the MC sim to draw more cards
    per trial -- enough that the K-bucket distribution shifts toward higher
    K. Concretely: P(K=0) should drop versus the natural-draw baseline."""
    variant = RampVariant(label="current", delta_rocks=0, R=11, spendable_curve={3: 40.0})
    sig = [8.4, 9.7, 11.1, 12.7, 14.45, 16.4, 18.5, 20.5]
    natural = compute_ramp_mc_panel(
        variant=variant, L=35, commanders=[], D=99, T=8,
        n_trials=2000, seed=1,
    )
    cantripping = compute_ramp_mc_panel(
        variant=variant, L=35, commanders=[], D=99, T=8,
        n_trials=2000, seed=1,
        per_turn_cumulative_draws=sig,
    )
    # Probability vectors come from the analytical hypergeometric -- both
    # should match what ramp_draw_probabilities gives, with the signature
    # version using n_draws=14.
    assert cantripping.scenario_probs[0] < natural.scenario_probs[0]
    assert cantripping.scenario_probs[3] > natural.scenario_probs[3]
    # MC bucket counts should also reflect the higher K-mass: high-K bucket
    # gets more samples under the signature.
    assert cantripping.bucket_stats[3].n_samples > natural.bucket_stats[3].n_samples


def test_ramp_mc_panel_no_signature_matches_default():
    """Regression guard: passing per_turn_cumulative_draws=None must give
    bit-identical results to the default call (same seed)."""
    args = dict(
        variant=RampVariant(label="current", delta_rocks=0, R=10, spendable_curve={3: 50.0}),
        L=35, commanders=[], D=99, T=8, n_trials=300, seed=7,
    )
    a = compute_ramp_mc_panel(**args)
    b = compute_ramp_mc_panel(**args, per_turn_cumulative_draws=None)
    for b_idx in (0, 1, 2, 3):
        assert a.bucket_stats[b_idx].n_samples == b.bucket_stats[b_idx].n_samples
        assert a.bucket_stats[b_idx].mana_util_mean == b.bucket_stats[b_idx].mana_util_mean


def test_ramp_mc_panel_sd_is_nonneg_when_samples_exist():
    variant = RampVariant(label="current", delta_rocks=0, R=10, spendable_curve={3: 50.0})
    panel = compute_ramp_mc_panel(
        variant=variant, L=35, commanders=[], D=99, T=8, n_trials=500, seed=1,
    )
    for s in panel.bucket_stats.values():
        if s.n_samples >= 2:
            assert s.mana_util_sd >= 0.0
            assert s.unspent_mana_sd >= 0.0
            assert s.stuck_cards_sd >= 0.0


def test_ramp_mc_panel_determinism_with_same_seed():
    args = dict(
        variant=RampVariant(label="current", delta_rocks=0, R=10, spendable_curve={3: 50.0}),
        L=35, commanders=[], D=99, T=8, n_trials=300, seed=42,
    )
    p1 = compute_ramp_mc_panel(**args)
    p2 = compute_ramp_mc_panel(**args)
    for b in p1.bucket_stats:
        assert p1.bucket_stats[b].mana_util_mean == p2.bucket_stats[b].mana_util_mean
        assert p1.bucket_stats[b].unspent_mana_mean == p2.bucket_stats[b].unspent_mana_mean


def test_ramp_mc_panel_expected_mana_util_is_p_weighted():
    def stats(util: float) -> RampBucketStats:
        return RampBucketStats(
            n_samples=10,
            mana_util_mean=util,
            mana_util_sd=0.0,
            unspent_mana_mean=0.0,
            unspent_mana_sd=0.0,
            stuck_cards_mean=0.0,
            stuck_cards_sd=0.0,
        )

    panel = RampMCPanel(
        variant=RampVariant(label="current", delta_rocks=0, R=10, spendable_curve={3: 30.0}),
        n_trials=40,
        scenario_probs={0: 0.1, 1: 0.2, 2: 0.3, 3: 0.4},
        bucket_stats={b: stats(float(b) / 10.0) for b in (0, 1, 2, 3)},
    )
    assert panel.expected_mana_util == pytest.approx(0.2)


def _deck_card(name: str, quantity: int, cmc: int, types: list[str], commander: bool = False):
    return {
        "name": name,
        "quantity": quantity,
        "cmc": cmc,
        "oracle_cmc": cmc,
        "types": types,
        "text": "",
        "commander": commander,
    }


def test_classify_ramp_tradeoff_input_includes_draw_spells_as_spendable():
    deck = [
        _deck_card("Swamp", 37, 0, ["Land"]),
        _deck_card("Draw Spell", 2, 2, ["Sorcery"]),
        _deck_card("Three Mana Spell", 20, 3, ["Sorcery"]),
    ]
    overrides = {
        "Draw Spell": {"categories": [{"category": "draw"}]},
    }

    result = classify_ramp_tradeoff_input(deck, registry=None, overrides=overrides)

    assert result["spendable_curve"] == {2: 2.0, 3: 20.0}
    assert result["draw_spells_included"] == 2


def test_compute_ramp_tradeoff_json_shape_uses_spendable_boundary_terms():
    from auto_goldfish.effects.card_database import DEFAULT_REGISTRY

    deck = [
        _deck_card("Swamp", 37, 0, ["Land"]),
        _deck_card("Arcane Signet", 3, 2, ["Artifact"]),
        _deck_card("Three Mana Spell", 20, 3, ["Sorcery"]),
    ]
    result = compute_ramp_tradeoff(
        deck,
        per_turn_cumulative_draws=[8, 9, 10, 11, 12, 13, 14, 15],
        registry=DEFAULT_REGISTRY,
        turns=6,
        n_trials=40,
    )

    assert result["suppressed"] is False
    assert result["current_rocks"] == 3
    assert result["phase1_turn"] == 5
    assert "spendable_slots" in result
    assert "V_curve" not in result
    assert result["variants"][0]["R"] == 0
    assert result["variants"][-1]["R"] == 6
    assert "spendable_slots" in result["variants"][0]
    assert "spend_rate" in result["variants"][0]
    assert set(result["variants"][0]["scenario_probs"].keys()) == {"0", "1", "2", "3"}


def test_compute_ramp_tradeoff_zero_ramp_renders_add_side():
    deck = [
        _deck_card("Swamp", 37, 0, ["Land"]),
        _deck_card("Three Mana Spell", 20, 3, ["Sorcery"]),
    ]
    result = compute_ramp_tradeoff(
        deck,
        per_turn_cumulative_draws=None,
        turns=6,
        n_trials=20,
    )
    assert result["suppressed"] is False
    assert [v["label"] for v in result["variants"]] == ["current", "+1 Signet", "+2 Signets", "+3 Signets"]


def test_compute_ramp_tradeoff_zero_spendable_suppresses():
    from auto_goldfish.effects.card_database import DEFAULT_REGISTRY

    deck = [
        _deck_card("Swamp", 37, 0, ["Land"]),
        _deck_card("Arcane Signet", 3, 2, ["Artifact"]),
    ]
    result = compute_ramp_tradeoff(
        deck,
        per_turn_cumulative_draws=None,
        registry=DEFAULT_REGISTRY,
        turns=6,
        n_trials=20,
    )
    assert result["suppressed"] is True
    assert "spendable spells" in result["reason"]


def test_callouts_do_not_fire_when_delta_is_inside_noise():
    def stats(unspent: float, stuck: float) -> RampBucketStats:
        return RampBucketStats(
            n_samples=10,
            mana_util_mean=0.8,
            mana_util_sd=0.5,
            unspent_mana_mean=unspent,
            unspent_mana_sd=100.0,
            stuck_cards_mean=stuck,
            stuck_cards_sd=100.0,
        )

    current = RampMCPanel(
        variant=RampVariant(label="current", delta_rocks=0, R=5, spendable_curve={3: 30.0}),
        n_trials=40,
        scenario_probs={0: 0.2, 1: 0.3, 2: 0.3, 3: 0.2},
        bucket_stats={b: stats(5.0, 2.0) for b in (0, 1, 2, 3)},
    )
    plus = RampMCPanel(
        variant=RampVariant(label="+1 Signet", delta_rocks=1, R=6, spendable_curve={3: 29.0}),
        n_trials=40,
        scenario_probs={0: 0.15, 1: 0.3, 2: 0.35, 3: 0.2},
        bucket_stats={b: stats(5.2, 1.8) for b in (0, 1, 2, 3)},
    )
    assert _build_callouts([current, plus]) == []


# ---------------------------------------------------------------------------
# Demo plot data
# ---------------------------------------------------------------------------

def test_ramp_plot_data_extracts_panel_series():
    plot_demo = _load_plot_demo_module()

    def stats(unspent: float, stuck: float) -> RampBucketStats:
        return RampBucketStats(
            n_samples=10,
            mana_util_mean=0.0,
            mana_util_sd=0.0,
            unspent_mana_mean=unspent,
            unspent_mana_sd=0.0,
            stuck_cards_mean=stuck,
            stuck_cards_sd=0.0,
        )

    panels = [
        RampMCPanel(
            variant=RampVariant(label="-1 Signet", delta_rocks=-1, R=9, spendable_curve={2: 20.0, 4: 10.0}),
            n_trials=40,
            scenario_probs={0: 0.30, 1: 0.40, 2: 0.20, 3: 0.10},
            bucket_stats={b: stats(unspent=2.0 + b, stuck=4.0 - b) for b in (0, 1, 2, 3)},
        ),
        RampMCPanel(
            variant=RampVariant(label="current", delta_rocks=0, R=10, spendable_curve={2: 18.0, 4: 11.0}),
            n_trials=40,
            scenario_probs={0: 0.25, 1: 0.35, 2: 0.25, 3: 0.15},
            bucket_stats={b: stats(unspent=3.0 + b, stuck=3.0 - b) for b in (0, 1, 2, 3)},
        ),
    ]

    data = plot_demo.ramp_plot_data(panels)

    assert data.labels == ["-1 Signet", "current"]
    assert data.rock_counts == [9, 10]
    assert data.value_slots == [30.0, 29.0]
    assert data.expected_unspent_mana == [
        panels[0].expected_unspent_mana,
        panels[1].expected_unspent_mana,
    ]
    assert data.expected_stuck_cards == [
        panels[0].expected_stuck_cards,
        panels[1].expected_stuck_cards,
    ]
    assert data.scenario_probabilities[0] == [0.30, 0.25]
    assert data.scenario_probabilities[3] == [0.10, 0.15]
