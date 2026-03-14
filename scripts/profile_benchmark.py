#!/usr/bin/env python3
"""Profile the racing optimizer to find bottlenecks."""

import time
import numpy as np

from auto_goldfish.engine.goldfisher import Goldfisher
from auto_goldfish.optimization.benchmark_decks import BENCHMARK_DECKS, get_benchmark_deck_dicts
from auto_goldfish.optimization.candidate_cards import ALL_CANDIDATES
from auto_goldfish.optimization.deck_config import DeckConfig, apply_config, enumerate_configs
from auto_goldfish.optimization.fast_optimizer import FastDeckOptimizer


SEED = 42
TURNS = 10
ENABLED = {cid: c for cid, c in ALL_CANDIDATES.items() if c.default_enabled}

deck_dicts = get_benchmark_deck_dicts(BENCHMARK_DECKS[0])
configs = enumerate_configs(ENABLED, max_draw=1, max_ramp=1, land_range=2)
print(f"Configs: {len(configs)}")

gf = Goldfisher(deck_dicts, turns=TURNS, sims=100, seed=SEED, record_results="quartile")

# Time apply_config
t0 = time.monotonic()
for cfg in configs:
    apply_config(gf, cfg, ENABLED)
t_apply = time.monotonic() - t0
print(f"apply_config x{len(configs)}: {t_apply*1000:.1f}ms ({t_apply/len(configs)*1000:.2f}ms each)")

# Time simulate_single_game
apply_config(gf, DeckConfig(), ENABLED)
t0 = time.monotonic()
for j in range(1000):
    gf.simulate_single_game(SEED + j)
t_single = time.monotonic() - t0
print(f"simulate_single_game x1000: {t_single*1000:.1f}ms ({t_single/1000*1000:.3f}ms each)")

# Time full simulate (100 sims)
gf.sims = 100
t0 = time.monotonic()
gf.simulate()
t_sim = time.monotonic() - t0
print(f"simulate(100): {t_sim*1000:.1f}ms ({t_sim/100*1000:.3f}ms per game)")

# Time bootstrap elimination
n = 200
rng = np.random.RandomState(42)
mana_a = rng.normal(20, 5, size=n)
mana_b = rng.normal(19, 5, size=n)

t0 = time.monotonic()
n_boot = 200
for _ in range(75):  # 75 configs
    diffs = []
    for _ in range(n_boot):
        idx = rng.choice(n, size=n, replace=True)
        sorted_a = np.sort(mana_a[idx])
        sorted_b = np.sort(mana_b[idx])
        cutoff = max(1, int(n * 0.25))
        con_a = sorted_a[:cutoff].mean() / mana_a[idx].mean()
        con_b = sorted_b[:cutoff].mean() / mana_b[idx].mean()
        diffs.append(con_a - con_b)
    upper = np.percentile(diffs, 95)
t_boot = time.monotonic() - t0
print(f"bootstrap elimination (75 configs, 200 boot each): {t_boot*1000:.1f}ms")

# Time vectorized bootstrap
t0 = time.monotonic()
for _ in range(75):
    boot_idx = rng.randint(0, n, size=(n_boot, n))
    boot_a = mana_a[boot_idx]  # (n_boot, n)
    boot_b = mana_b[boot_idx]
    # sort along axis=1
    sorted_a = np.sort(boot_a, axis=1)
    sorted_b = np.sort(boot_b, axis=1)
    cutoff = max(1, int(n * 0.25))
    con_a = sorted_a[:, :cutoff].mean(axis=1) / boot_a.mean(axis=1)
    con_b = sorted_b[:, :cutoff].mean(axis=1) / boot_b.mean(axis=1)
    diffs = con_a - con_b
    upper = np.percentile(diffs, 95)
t_vboot = time.monotonic() - t0
print(f"vectorized bootstrap (75 configs, 200 boot each): {t_vboot*1000:.1f}ms")
print(f"Bootstrap speedup from vectorization: {t_boot/t_vboot:.1f}x")

# Total budget breakdown for racing
n_configs = len(configs)
batch_size = 20
max_rounds = 200 // batch_size  # 10 rounds
total_games = n_configs * batch_size * max_rounds
print(f"\nBudget breakdown:")
print(f"  Racing phase: {n_configs} configs x {batch_size} games x {max_rounds} rounds = {total_games} games")
print(f"  Est racing time: {total_games * t_single/1000:.1f}s (games only)")
print(f"  Est apply_config overhead: {n_configs * max_rounds * t_apply/len(configs):.1f}s")
print(f"  Final eval: 5 configs x 500 sims = 2500 games at {t_sim/100*1000:.1f}ms each = {5 * 500 * t_sim/100:.1f}s")
