"""Tests for compute_turn_structure in optimization/curve_value.py."""

from __future__ import annotations

from auto_goldfish.optimization.curve_value import (
    RampCardSpec,
    compute_turn_structure,
)


def _by_cmc(result):
    return {row.cmc: row for row in result.rows}


def test_no_ramp_with_ramp_equals_counterfactual():
    """No ramp -> the two scenarios are identical for every CMC."""
    curve = {1: 5, 2: 10, 3: 8, 4: 4}
    result = compute_turn_structure(curve, ramp_specs=[], T=8)
    assert result.delta_turns == 0.0
    for row in result.rows:
        assert row.n_ramp_cards == 0
        assert row.counterfactual_added == 0.0
        assert row.with_ramp_cast == row.counterfactual_cast
        assert row.with_ramp_total_turns == row.counterfactual_total_turns


def test_counterfactual_preserves_curve_shape():
    """Curve-proportional counterfactual: each CMC gets a share of ramp slots
    proportional to its existing value count, so shape is preserved exactly.
    """
    curve = {1: 4, 2: 8, 3: 4}  # shares 1/4, 1/2, 1/4
    ramp = [RampCardSpec(name=f"R{i}", cmc=2, mana_per_turn=1.0) for i in range(4)]
    result = compute_turn_structure(curve, ramp_specs=ramp, T=8)
    rows = _by_cmc(result)
    # 4 ramp slots distributed: 4 * 1/4 = 1, 4 * 1/2 = 2, 4 * 1/4 = 1.
    assert abs(rows[1].counterfactual_added - 1.0) < 1e-9
    assert abs(rows[2].counterfactual_added - 2.0) < 1e-9
    assert abs(rows[3].counterfactual_added - 1.0) < 1e-9
    # Total added equals total ramp count.
    assert abs(sum(r.counterfactual_added for r in result.rows) - 4.0) < 1e-9


def test_n_ramp_cards_records_actual_ramp_cmc():
    """n_ramp_cards is informational: where ramp pieces live in the actual deck."""
    curve = {1: 5, 2: 5, 6: 5}
    ramp = [
        RampCardSpec(name="A", cmc=2, mana_per_turn=1.0),
        RampCardSpec(name="B", cmc=2, mana_per_turn=1.0),
        RampCardSpec(name="C", cmc=3, mana_per_turn=1.0),
    ]
    result = compute_turn_structure(curve, ramp_specs=ramp, T=8)
    rows = _by_cmc(result)
    assert rows[2].n_ramp_cards == 2
    assert rows[1].n_ramp_cards == 0
    assert rows[6].n_ramp_cards == 0


def test_top_loaded_curve_with_ramp_reaches_big_spells_earlier():
    """With-ramp should cast the deck's top-CMC spells at earlier turns."""
    curve = {6: 4, 7: 3, 8: 2}
    ramp = [
        RampCardSpec(name=f"BigRamp{i}", cmc=3, mana_per_turn=1.0) for i in range(6)
    ]
    result = compute_turn_structure(curve, ramp_specs=ramp, T=8)
    with_eights = [t for t, c, _amt in result.with_ramp_casts if c == 8]
    cf_eights = [t for t, c, _amt in result.counterfactual_casts if c == 8]
    assert with_eights and cf_eights
    assert min(with_eights) <= min(cf_eights)


def test_uncast_cards_excluded_from_per_cast_included_in_per_drawn():
    """Per-cast denominator is cards cast; per-drawn includes uncast slots."""
    curve = {8: 4}
    result = compute_turn_structure(curve, ramp_specs=[], T=8)
    row = _by_cmc(result)[8]
    # 4 cards at CMC 8 with land-only mana: only 1 castable, on T=8, T-t=0.
    assert abs(row.with_ramp_cast - 1.0) < 1e-9
    assert row.with_ramp_total_turns == 0.0


def test_totals_match_row_sum():
    curve = {1: 4, 2: 6, 3: 4, 4: 2}
    ramp = [RampCardSpec(name="Rock", cmc=2, mana_per_turn=1.0)]
    result = compute_turn_structure(curve, ramp_specs=ramp, T=8)
    assert abs(result.with_ramp_total_turns - sum(r.with_ramp_total_turns for r in result.rows)) < 1e-9
    assert abs(result.counterfactual_total_turns - sum(r.counterfactual_total_turns for r in result.rows)) < 1e-9
    assert abs(result.delta_turns - (result.with_ramp_total_turns - result.counterfactual_total_turns)) < 1e-9


def test_draw_cap_reduces_totals():
    """With a tight draw cap, fewer cards are available and totals shrink."""
    curve = {1: 30, 2: 20, 3: 10}
    ramp = [RampCardSpec(name=f"R{i}", cmc=2, mana_per_turn=1.0) for i in range(3)]
    uncapped = compute_turn_structure(curve, ramp_specs=ramp, T=8)
    # 99-card deck, natural draws by turn (on the play): 7, 8, ..., 14.
    per_turn = [7, 8, 9, 10, 11, 12, 13, 14]
    capped = compute_turn_structure(
        curve, ramp_specs=ramp, T=8, D=99, per_turn_cumulative_draws=per_turn,
    )
    assert capped.draw_capped is True
    assert capped.with_ramp_total_turns < uncapped.with_ramp_total_turns
    assert capped.counterfactual_total_turns < uncapped.counterfactual_total_turns


def test_draw_cap_limits_expected_ramp_casts():
    """Ramp pieces are also expected draws, not guaranteed opening-hand cards."""
    curve = {2: 20}
    ramp = [RampCardSpec(name=f"R{i}", cmc=2, mana_per_turn=1.0) for i in range(10)]
    per_turn = [7, 8, 9, 10, 11, 12, 13, 14]
    result = compute_turn_structure(
        curve, ramp_specs=ramp, T=8, D=100, per_turn_cumulative_draws=per_turn,
    )
    # By T8, expected ramp cards seen is 10 * 14 / 100 = 1.4. Each costs 2.
    assert abs(sum(result.with_ramp_ramp_spend) - 2.8) < 1e-9
    assert result.with_ramp_mana_stream[-1] < 10.0


def test_draw_cap_makes_casts_fractional_expected_counts():
    """Under the draw cap, cast counts represent expected drawn-and-cast values."""
    curve = {2: 20}
    per_turn = [7, 8, 9, 10, 11, 12, 13, 14]
    result = compute_turn_structure(
        curve, ramp_specs=[], T=8, D=99, per_turn_cumulative_draws=per_turn,
    )
    row = _by_cmc(result)[2]
    # Expected drawn 2-drops by T=8: 20 * 14 / 99 = 2.828...
    # All castable on turns >= 2 (mana >= 2), so cast == drawn.
    expected_drawn = 20 * 14 / 99
    assert abs(row.with_ramp_cast - expected_drawn) < 0.01


def test_always_available_counts_are_not_draw_capped():
    """Command-zone spendables are available from turn 1, not drawn from deck."""
    per_turn = [7, 8, 9, 10, 11, 12, 13, 14]
    result = compute_turn_structure(
        curve_counts={},
        ramp_specs=[],
        T=8,
        D=99,
        per_turn_cumulative_draws=per_turn,
        always_available_counts={4: 1},
    )
    row = _by_cmc(result)[4]
    assert row.n_value_cards == 1.0
    assert row.with_ramp_cast == 1.0
    assert result.with_ramp_value_spend_by_turn[3] == {4: 4.0}


def test_always_available_spendables_prioritize_over_ramp():
    """Commanders spend available mana before ramp setup in the timeline model."""
    ramp = [RampCardSpec(name="FourManaRock", cmc=4, mana_per_turn=1.0)]
    result = compute_turn_structure(
        curve_counts={},
        ramp_specs=ramp,
        T=5,
        always_available_counts={4: 1},
    )
    assert result.with_ramp_value_spend_by_turn[3] == {4: 4.0}
    assert result.with_ramp_ramp_spend[3] == 0.0
    assert result.with_ramp_ramp_spend[4] == 4.0


def test_interchangeable_ramp_bucket_casts_any_available_copy():
    """Eight similar rocks should not behave like only the first named rock."""
    ramp = [
        RampCardSpec(name=f"Rock{i}", cmc=2, mana_per_turn=1.0)
        for i in range(8)
    ]
    result = compute_turn_structure(
        curve_counts={},
        ramp_specs=ramp,
        T=3,
        D=100,
        per_turn_cumulative_draws=[7, 10, 10],
    )
    # P(any of 8 rocks in 10 seen cards) = 1 - 0.9^8 ~= 0.57,
    # so expected turn-2 ramp spend is about 1.14 mana, not 0.2.
    assert result.with_ramp_ramp_spend[1] > 1.0


def test_bucketed_ramp_can_enable_turn_three_commander():
    ramp = [
        RampCardSpec(name=f"Rock{i}", cmc=2, mana_per_turn=1.0)
        for i in range(8)
    ]
    result = compute_turn_structure(
        curve_counts={},
        ramp_specs=ramp,
        T=4,
        D=100,
        per_turn_cumulative_draws=[7, 10, 10, 10],
        always_available_counts={4: 1},
    )
    assert result.with_ramp_value_spend_by_turn[2].get(4, 0.0) > 2.0


def test_value_spend_ledger_matches_cast_records():
    curve = {2: 3}
    result = compute_turn_structure(curve, ramp_specs=[], T=3)
    # Land-only value mana is [1, 2, 3]. Top-of-curve casts one 2-drop on
    # turn 2 and one 2-drop on turn 3, leaving 1 mana unused on turns 1 and 3.
    assert result.with_ramp_value_spend_by_turn == [{}, {2: 2.0}, {2: 2.0}]
    assert result.counterfactual_value_spend_by_turn == result.with_ramp_value_spend_by_turn
    assert result.with_ramp_unused_mana == [1.0, 0.0, 1.0]
    assert result.with_ramp_total_value_mana_spent == 4.0
    assert result.delta_value_mana_spent == 0.0


def test_ramp_spend_is_separate_from_value_spend():
    curve = {2: 4}
    ramp = [RampCardSpec(name="Rock", cmc=2, mana_per_turn=1.0)]
    result = compute_turn_structure(curve, ramp_specs=ramp, T=4)
    # The ramp spell spends turn-2 mana as setup, while value-spell spend only
    # records non-ramp cards cast after that setup cost is paid.
    assert result.with_ramp_ramp_spend == [0.0, 2.0, 0.0, 0.0]
    assert result.counterfactual_ramp_spend == [0.0, 0.0, 0.0, 0.0]
    assert sum(result.with_ramp_value_spend_by_turn[1].values()) == 0.0
    assert result.with_ramp_total_value_mana_spent == sum(
        sum(turn.values()) for turn in result.with_ramp_value_spend_by_turn
    )
