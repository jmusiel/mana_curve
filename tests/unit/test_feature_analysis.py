"""Unit tests for the feature_analysis module."""

import numpy as np
import pytest

from auto_goldfish.optimization.feature_analysis import (
    aggregate_hyperband_scores,
    analyze_optimization,
    compute_marginal_impact,
    fit_ols,
    predict_top_configs,
    regression_analysis,
    synthesize_recommendations,
)
from auto_goldfish.optimization.deck_config import DeckConfig


# ── Helpers ───────────────────────────────────────────────────────────


def _make_simple_dataset():
    """Create a small dataset with known properties.

    2 features: land_delta (-1, 0, +1) and count_CardA (0, 1).
    Score = 10 + 2*land_delta + 1*count_CardA + noise=0.
    6 configs in a full grid.
    """
    feature_dicts = [
        {"land_delta": -1, "count_CardA": 0},
        {"land_delta": -1, "count_CardA": 1},
        {"land_delta": 0, "count_CardA": 0},
        {"land_delta": 0, "count_CardA": 1},
        {"land_delta": 1, "count_CardA": 0},
        {"land_delta": 1, "count_CardA": 1},
    ]
    feature_names = ["count_CardA", "land_delta"]
    X = np.array([[fd[name] for name in feature_names] for fd in feature_dicts],
                 dtype=float)
    # Perfect linear: score = 10 + 2*land_delta + 1*count_CardA
    scores = np.array([10 + 2 * fd["land_delta"] + 1 * fd["count_CardA"]
                       for fd in feature_dicts], dtype=float)
    return X, scores, feature_names, feature_dicts


# ── fit_ols tests ─────────────────────────────────────────────────────


class TestFitOLS:
    def test_perfect_linear_fit(self):
        X, scores, feature_names, _ = _make_simple_dataset()
        coeffs, intercept, r_sq, std_errors = fit_ols(X, scores)

        assert r_sq == pytest.approx(1.0, abs=1e-10)
        assert intercept == pytest.approx(10.0, abs=1e-10)
        # feature_names = ["count_CardA", "land_delta"]
        assert coeffs[0] == pytest.approx(1.0, abs=1e-10)  # count_CardA
        assert coeffs[1] == pytest.approx(2.0, abs=1e-10)  # land_delta

    def test_predicted_values(self):
        X, scores, _, _ = _make_simple_dataset()
        coeffs, intercept, _, _ = fit_ols(X, scores)
        y_pred = X @ coeffs + intercept
        np.testing.assert_allclose(y_pred, scores, atol=1e-10)

    def test_weighted_least_squares(self):
        X, scores, _, _ = _make_simple_dataset()
        # Uniform weights should give same result as unweighted
        weights = np.ones(len(scores))
        coeffs_w, intercept_w, r_sq_w, _ = fit_ols(X, scores, weights)
        coeffs_u, intercept_u, r_sq_u, _ = fit_ols(X, scores)

        np.testing.assert_allclose(coeffs_w, coeffs_u, atol=1e-10)
        assert intercept_w == pytest.approx(intercept_u, abs=1e-10)
        assert r_sq_w == pytest.approx(r_sq_u, abs=1e-10)


# ── regression_analysis tests ─────────────────────────────────────────


class TestRegressionAnalysis:
    def test_returns_predicted_scores(self):
        X, scores, feature_names, _ = _make_simple_dataset()
        reg_dict, y_pred = regression_analysis(X, scores, feature_names)

        np.testing.assert_allclose(y_pred, scores, atol=1e-10)

    def test_score_std_matches_numpy(self):
        X, scores, feature_names, _ = _make_simple_dataset()
        reg_dict, _ = regression_analysis(X, scores, feature_names)

        expected_std = float(np.std(scores))
        assert reg_dict["score_std"] == pytest.approx(expected_std, abs=1e-5)

    def test_ranked_by_coefficient_descending(self):
        X, scores, feature_names, _ = _make_simple_dataset()
        reg_dict, _ = regression_analysis(X, scores, feature_names)

        coeffs = [c["coefficient"] for c in reg_dict["coefficients"]]
        assert coeffs == sorted(coeffs, reverse=True)


# ── compute_marginal_impact tests ─────────────────────────────────────


class TestComputeMarginalImpact:
    def test_delta_std_equals_delta_over_score_std(self):
        _, scores, feature_names, feature_dicts = _make_simple_dataset()
        score_std = float(np.std(scores))

        results = compute_marginal_impact(
            feature_dicts, scores, feature_names, score_std=score_std,
        )

        for r in results:
            assert "delta_std" in r
            assert r["delta_std"] == pytest.approx(
                r["delta"] / score_std, abs=1e-3,
            )

    def test_no_delta_std_without_score_std(self):
        _, scores, feature_names, feature_dicts = _make_simple_dataset()

        results = compute_marginal_impact(
            feature_dicts, scores, feature_names,
        )

        for r in results:
            assert "delta_std" not in r

    def test_sorted_by_delta_descending(self):
        _, scores, feature_names, feature_dicts = _make_simple_dataset()
        results = compute_marginal_impact(
            feature_dicts, scores, feature_names,
        )
        deltas = [r["delta"] for r in results]
        assert deltas == sorted(deltas, reverse=True)


# ── aggregate_hyperband_scores tests ──────────────────────────────────


class TestAggregateHyperbandScores:
    def test_weighted_average(self):
        cfg = DeckConfig(land_delta=1)
        # Two rounds: score=10 with 100 sims, score=12 with 200 sims
        round_scores = [
            (cfg, 10.0, 100),
            (cfg, 12.0, 200),
        ]
        configs, scores, weights = aggregate_hyperband_scores(round_scores)
        assert len(configs) == 1
        # Weighted avg: (10*100 + 12*200) / 300 = 3400/300 = 11.333...
        assert scores[0] == pytest.approx(11.333, abs=0.01)
        assert weights[0] == pytest.approx(np.sqrt(300), abs=0.01)

    def test_sorted_by_score_descending(self):
        round_scores = [
            (DeckConfig(land_delta=-1), 5.0, 100),
            (DeckConfig(land_delta=1), 15.0, 100),
            (DeckConfig(land_delta=0), 10.0, 100),
        ]
        configs, scores, _ = aggregate_hyperband_scores(round_scores)
        assert scores[0] > scores[1] > scores[2]


# ── synthesize_recommendations tests ──────────────────────────────────


class TestSynthesizeRecommendations:
    def test_produces_recommendations(self):
        _, scores, feature_names, feature_dicts = _make_simple_dataset()
        X = np.array([[fd[name] for name in feature_names] for fd in feature_dicts],
                     dtype=float)
        reg_dict, _ = regression_analysis(X, scores, feature_names)
        marginal = compute_marginal_impact(feature_dicts, scores, feature_names)

        recs = synthesize_recommendations(marginal, reg_dict, "mean_mana")
        assert len(recs) > 0
        # Should be sorted by impact descending
        impacts = [r["impact"] for r in recs]
        assert impacts == sorted(impacts, reverse=True)

    def test_has_required_fields(self):
        _, scores, feature_names, feature_dicts = _make_simple_dataset()
        X = np.array([[fd[name] for name in feature_names] for fd in feature_dicts],
                     dtype=float)
        reg_dict, _ = regression_analysis(X, scores, feature_names)
        marginal = compute_marginal_impact(feature_dicts, scores, feature_names)

        recs = synthesize_recommendations(marginal, reg_dict, "mean_mana")
        for r in recs:
            assert "recommendation" in r
            assert "impact" in r
            assert "confidence" in r
            assert "label" in r
            assert "detail" in r

    def test_land_delta_phrasing(self):
        """land_delta recommendations use 'Add more lands' / 'Cut lands' labels."""
        _, scores, feature_names, feature_dicts = _make_simple_dataset()
        X = np.array([[fd[name] for name in feature_names] for fd in feature_dicts],
                     dtype=float)
        reg_dict, _ = regression_analysis(X, scores, feature_names)
        marginal = compute_marginal_impact(feature_dicts, scores, feature_names)

        recs = synthesize_recommendations(marginal, reg_dict, "mean_mana")
        land_recs = [r for r in recs if "land" in r["label"].lower()]
        assert len(land_recs) > 0
        for r in land_recs:
            assert r["label"] in ("Add more lands", "Cut lands")
            assert "at least one" in r["recommendation"]

    def test_known_candidate_has_example_card(self):
        """Recommendations for known candidates include example_card info."""
        feature_dicts = [
            {"land_delta": 0, "count_Draw2(mv2)": 0},
            {"land_delta": 0, "count_Draw2(mv2)": 1},
            {"land_delta": 0, "count_Draw2(mv2)": 2},
        ]
        feature_names = sorted(feature_dicts[0].keys())
        X = np.array([[fd[name] for name in feature_names] for fd in feature_dicts],
                     dtype=float)
        scores = np.array([8.0, 10.0, 12.0])
        reg_dict, _ = regression_analysis(X, scores, feature_names)
        marginal = compute_marginal_impact(feature_dicts, scores, feature_names)

        recs = synthesize_recommendations(marginal, reg_dict, "mean_mana")
        draw_recs = [r for r in recs if "draw" in r["label"].lower()]
        assert len(draw_recs) > 0
        r = draw_recs[0]
        assert r["label"] == "Add more 2-mana draw"
        assert "example_card" in r
        assert r["example_card"]["name"] == "Night's Whisper"
        assert "scryfall.com" in r["example_card"]["url"]
        assert "Night's Whisper" in r["recommendation"]
        assert "such as" in r["recommendation"]

    def test_unknown_candidate_no_example_card(self):
        """Unknown candidate labels fall back without example_card."""
        _, scores, feature_names, feature_dicts = _make_simple_dataset()
        X = np.array([[fd[name] for name in feature_names] for fd in feature_dicts],
                     dtype=float)
        reg_dict, _ = regression_analysis(X, scores, feature_names)
        marginal = compute_marginal_impact(feature_dicts, scores, feature_names)

        recs = synthesize_recommendations(marginal, reg_dict, "mean_mana")
        card_recs = [r for r in recs if "CardA" in r["label"]]
        assert len(card_recs) > 0
        for r in card_recs:
            assert "example_card" not in r
            assert r["label"] in ("Add more CardA", "Don't add CardA")


# ── analyze_optimization integration test ─────────────────────────────


class TestPredictTopConfigs:
    def test_selects_highest_predicted(self):
        """Regression should predict land_delta=+2 as best when score ~ land_delta."""
        all_configs = [DeckConfig(land_delta=d) for d in range(-2, 3)]
        # Hyperband data: score correlates with land_delta
        round_scores = [
            (DeckConfig(land_delta=d), 10.0 + 2.0 * d, 100)
            for d in range(-2, 3)
        ]
        top, reg_info = predict_top_configs(round_scores, all_configs, top_k=2)
        # Top 2 should be land_delta=+2 and +1
        top_deltas = {c.land_delta for c in top}
        assert 2 in top_deltas
        assert 1 in top_deltas

    def test_returns_all_if_few_scores(self):
        """With fewer than 3 round scores, falls back to returning first top_k."""
        all_configs = [DeckConfig(land_delta=d) for d in range(-2, 3)]
        round_scores = [
            (DeckConfig(land_delta=0), 10.0, 100),
        ]
        top, reg_info = predict_top_configs(round_scores, all_configs, top_k=3)
        assert len(top) == 3
        assert reg_info == {}

    def test_respects_top_k(self):
        all_configs = [DeckConfig(land_delta=d) for d in range(-2, 3)]
        round_scores = [
            (DeckConfig(land_delta=d), 10.0 + d, 100)
            for d in range(-2, 3)
        ]
        top, _ = predict_top_configs(round_scores, all_configs, top_k=3)
        assert len(top) == 3


class TestAnalyzeOptimization:
    def test_empty_input(self):
        result = analyze_optimization([], "mean_mana")
        assert result == {}

    def test_returns_expected_keys(self):
        round_scores = [
            (DeckConfig(land_delta=d), 10.0 + d, 100)
            for d in range(-2, 3)
        ]
        result = analyze_optimization(round_scores, "mean_mana")
        assert "recommendations" in result
        assert "marginal_impact" in result
        assert "regression" in result
        assert "n_configs" in result
