"""Benchmark R² and std_beta ranges across scenarios to calibrate confidence thresholds."""

import numpy as np
import pytest

from auto_goldfish.optimization.feature_analysis import (
    compute_marginal_impact,
    regression_analysis,
    synthesize_recommendations,
)


def _build_scenario(n_configs, feature_effects, noise_std, seed=42):
    """Build a synthetic dataset.

    Args:
        n_configs: number of configs to generate
        feature_effects: dict of feature_name -> (coeff, values_pool)
            e.g. {"land_delta": (2.0, [-2,-1,0,1,2]), "count_CardA": (0.5, [0,1,2,3])}
        noise_std: standard deviation of Gaussian noise added to scores
        seed: random seed
    """
    rng = np.random.default_rng(seed)
    feature_names = sorted(feature_effects.keys())

    feature_dicts = []
    for _ in range(n_configs):
        fd = {}
        for name in feature_names:
            _, pool = feature_effects[name]
            fd[name] = rng.choice(pool)
        feature_dicts.append(fd)

    X = np.array([[fd[name] for name in feature_names] for fd in feature_dicts], dtype=float)

    # True score = intercept + sum(coeff * feature) + noise
    scores = np.full(n_configs, 10.0)
    for i, name in enumerate(feature_names):
        coeff, _ = feature_effects[name]
        scores += coeff * X[:, i]
    scores += rng.normal(0, noise_std, n_configs)

    return X, scores, feature_names, feature_dicts


def _run_scenario(name, n_configs, feature_effects, noise_std, seed=42):
    """Run a scenario and print R², std_beta, and confidence for each feature."""
    X, scores, feature_names, feature_dicts = _build_scenario(
        n_configs, feature_effects, noise_std, seed
    )
    reg_dict, _ = regression_analysis(X, scores, feature_names)
    marginal = compute_marginal_impact(
        feature_dicts, scores, feature_names, score_std=reg_dict["score_std"]
    )
    recs = synthesize_recommendations(marginal, reg_dict, "mean_mana")

    r2 = reg_dict["r_squared"]
    print(f"\n{'='*60}")
    print(f"Scenario: {name}")
    print(f"  n_configs={n_configs}, noise_std={noise_std}")
    print(f"  R² = {r2:.4f}")
    print(f"  Features:")
    for c in reg_dict["coefficients"]:
        print(f"    {c['feature']:20s}  coeff={c['coefficient']:+.4f}  std_beta={c['std_beta']:+.4f}  t={c['t_stat']:+.2f}")
    print(f"  Recommendations:")
    for r in recs:
        print(f"    [{r['confidence']:6s}] {r['recommendation']}")
    print(f"{'='*60}")

    return reg_dict, recs


class TestConfidenceBenchmark:
    """These tests print benchmark data and verify the output structure.

    Run with: pytest tests/unit/test_confidence_benchmark.py -s
    """

    def test_strong_signal_low_noise(self):
        """Strong effects, minimal noise -> should be high confidence."""
        reg, recs = _run_scenario(
            "Strong signal, low noise",
            n_configs=30,
            feature_effects={
                "land_delta": (2.0, [-2, -1, 0, 1, 2]),
                "count_CardA": (1.0, [0, 1, 2, 3]),
            },
            noise_std=0.5,
        )
        confidences = {r["label"]: r["confidence"] for r in recs}
        assert confidences["more lands"] == "high"
        assert confidences["CardA"] == "high"

    def test_strong_signal_moderate_noise(self):
        """Strong effects, moderate noise."""
        reg, recs = _run_scenario(
            "Strong signal, moderate noise",
            n_configs=30,
            feature_effects={
                "land_delta": (2.0, [-2, -1, 0, 1, 2]),
                "count_CardA": (1.0, [0, 1, 2, 3]),
            },
            noise_std=3.0,
        )
        assert len(recs) > 0

    def test_strong_signal_high_noise(self):
        """Strong effects, heavy noise -> strong feature medium, weak feature low."""
        reg, recs = _run_scenario(
            "Strong signal, high noise",
            n_configs=30,
            feature_effects={
                "land_delta": (2.0, [-2, -1, 0, 1, 2]),
                "count_CardA": (1.0, [0, 1, 2, 3]),
            },
            noise_std=8.0,
        )
        confidences = {r["label"]: r["confidence"] for r in recs}
        assert confidences["more lands"] == "medium"
        # CardA drowned out by noise
        assert confidences["CardA"] == "low"

    def test_weak_signal_low_noise(self):
        """Weak effects, low noise."""
        reg, recs = _run_scenario(
            "Weak signal, low noise",
            n_configs=30,
            feature_effects={
                "land_delta": (0.3, [-2, -1, 0, 1, 2]),
                "count_CardA": (0.1, [0, 1, 2, 3]),
            },
            noise_std=0.5,
        )
        assert len(recs) > 0

    def test_weak_signal_high_noise(self):
        """Weak effects, heavy noise -> everything should be low."""
        reg, recs = _run_scenario(
            "Weak signal, high noise",
            n_configs=30,
            feature_effects={
                "land_delta": (0.3, [-2, -1, 0, 1, 2]),
                "count_CardA": (0.1, [0, 1, 2, 3]),
            },
            noise_std=5.0,
        )
        for r in recs:
            assert r["confidence"] == "low"

    def test_many_features_mixed(self):
        """Many features with varying effect sizes."""
        reg, recs = _run_scenario(
            "Many features, mixed effects",
            n_configs=50,
            feature_effects={
                "land_delta": (2.0, [-2, -1, 0, 1, 2]),
                "count_CardA": (1.5, [0, 1, 2, 3]),
                "count_CardB": (0.5, [0, 1, 2]),
                "count_CardC": (0.1, [0, 1]),
                "count_CardD": (0.0, [0, 1, 2]),  # no real effect
            },
            noise_std=2.0,
        )
        assert len(recs) > 0

    def test_single_dominant_feature(self):
        """One strong feature, rest are noise -> only dominant gets high."""
        reg, recs = _run_scenario(
            "Single dominant feature",
            n_configs=40,
            feature_effects={
                "land_delta": (5.0, [-2, -1, 0, 1, 2]),
                "count_CardA": (0.01, [0, 1, 2]),
                "count_CardB": (0.01, [0, 1]),
            },
            noise_std=2.0,
        )
        confidences = {r["label"]: r["confidence"] for r in recs}
        assert confidences["more lands"] == "high"
        # Weak features should not be high confidence
        for label, conf in confidences.items():
            if label != "more lands":
                assert conf != "high", f"{label} should not be high, got {conf}"

    def test_few_configs(self):
        """Very few configs (typical early hyperband)."""
        reg, recs = _run_scenario(
            "Few configs (early hyperband)",
            n_configs=8,
            feature_effects={
                "land_delta": (2.0, [-1, 0, 1]),
                "count_CardA": (1.0, [0, 1]),
            },
            noise_std=1.0,
        )
        assert len(recs) > 0
