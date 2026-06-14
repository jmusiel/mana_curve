"""Calibrate the Mana Model's land-count recommendation against the simulator.

For each deck, runs a goldfishing land sweep, finds the land count that maximizes
value-mana spent (the empirical optimum), then regresses that optimum on deck
features (avg CMC, ramp, draw). The recommendation in
``auto_goldfish.optimization.mana_model.optimal_land_count`` is fit from these
results -- but anchored to a consensus level rather than the simulator's absolute
number, because the goldfishing optimum is noisy and horizon-sensitive (see
ADR-0003). The trustworthy signal is the *relative* slopes.

Why a 14-turn horizon: in short games flooding never bites (you never run out of
spells), so value-mana rises monotonically with lands and the "optimum" pins to the
sweep ceiling. By ~14 turns the spell pool depletes, excess lands become dead draws,
and an interior optimum appears at realistic counts. Shorter/longer horizons shift
the absolute level, which is exactly why we anchor it externally and keep only slopes.

Usage:
    .venv/bin/python scripts/fit_land_model.py --decks-file data/sample_decks.json
    .venv/bin/python scripts/fit_land_model.py --fit-only   # re-fit cached results

Results checkpoint to --out (default land_fit_data.json) and are resumable.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from typing import Dict, List, Optional

import numpy as np

from auto_goldfish.decklist.archidekt import fetch_and_save
from auto_goldfish.decklist.loader import get_deckpath, load_decklist
from auto_goldfish.effects.card_database import DEFAULT_REGISTRY
from auto_goldfish.engine.goldfisher import Goldfisher
from auto_goldfish.optimization.deck_analyzer import analyze_deck_composition
from auto_goldfish.optimization.mana_model import optimal_land_count

# Consensus anchor (must match mana_model.REC_ANCHOR_*): used to report the
# final anchored formula, not to fit the slopes.
ANCHOR_LANDS, ANCHOR_CMC = 37.0, 3.0


def _canonical_url(url: str) -> Optional[str]:
    """Archidekt id -> a slugged URL (the fetcher reads the id from path[-2])."""
    m = re.search(r"/decks/(\d+)", url)
    return f"https://archidekt.com/decks/{m.group(1)}/x" if m else None


def _smoothed_argmax(curve: List) -> int:
    """3-point moving-average argmax, to tame the plateau noise of the optimum."""
    ks = [k for k, _ in curve]
    vs = [v for _, v in curve]
    best_k, best = ks[0], -1e9
    for i in range(len(vs)):
        lo, hi = max(0, i - 1), min(len(vs), i + 2)
        avg = sum(vs[lo:hi]) / (hi - lo)
        if avg > best:
            best, best_k = avg, ks[i]
    return best_k


def collect(urls: List[str], out: str, sweep, sims: int, turns: int, seed: int, workers: int) -> Dict:
    results: Dict = json.load(open(out)) if os.path.isfile(out) else {}
    for n, url in enumerate(urls, 1):
        curl = _canonical_url(url)
        if not curl:
            print(f"[{n}] bad url {url}", flush=True)
            continue
        did = re.search(r"/decks/(\d+)", curl).group(1)
        if did in results:
            continue
        name, t0 = f"calib_{did}", time.time()
        try:
            if not os.path.isfile(get_deckpath(name)):
                fetch_and_save(curl, name)
            cards = load_decklist(name)
            comp = analyze_deck_composition(cards, DEFAULT_REGISTRY, {})
            gf = Goldfisher(cards, turns=turns, sims=sims, seed=seed, workers=workers)
            curve = []
            for k in sweep:
                gf.set_lands(k, cuts=[])
                curve.append((k, round(gf.simulate().mean_mana_value, 3)))
            results[did] = {
                "deck_size": comp.deck_size, "current_lands": comp.land_count,
                "avg_cmc": round(comp.avg_cmc, 3), "ramp": comp.ramp_cards,
                "draw": comp.draw_cards, "sim_optimal": _smoothed_argmax(curve),
                "model_rec": optimal_land_count(
                    deck_size=comp.deck_size, cmc_distribution=comp.cmc_distribution,
                    ramp_cards=comp.ramp_cards, draw_cards=comp.draw_cards,
                    commander_cmcs=list(comp.commander_cmcs))["recommended_lands"],
                "curve": curve,
            }
            json.dump(results, open(out, "w"))
            r = results[did]
            print(f"[{n}/{len(urls)}] {did} cur={r['current_lands']} avg_cmc={r['avg_cmc']} "
                  f"ramp={r['ramp']} draw={r['draw']} -> SIM={r['sim_optimal']} "
                  f"MODEL={r['model_rec']} ({time.time()-t0:.1f}s)", flush=True)
        except Exception as exc:
            print(f"[{n}/{len(urls)}] {did} FAIL: {exc}", flush=True)
    return results


def fit(results: Dict, floor: int, ceil: int) -> None:
    rows = np.array([[v["avg_cmc"], v["ramp"], v["draw"], v["sim_optimal"]]
                     for v in results.values()], float)
    cmc, ramp, draw, sim = rows[:, 0], rows[:, 1], rows[:, 2], rows[:, 3]
    # Fit slopes only on uncensored decks (those pinned at a sweep boundary have a
    # truncated optimum and would bias the slopes).
    unc = (sim > floor) & (sim < ceil)
    X = np.column_stack([np.ones(unc.sum()), cmc[unc], ramp[unc], draw[unc]])
    coef, *_ = np.linalg.lstsq(X, sim[unc], rcond=None)
    b0, bc, br, bd = coef
    print(f"\nn={len(sim)}  uncensored={int(unc.sum())}  "
          f"floored={int((sim == floor).sum())}  ceiling={int((sim == ceil).sum())}")
    print(f"raw fit (uncensored): sim ~= {b0:.2f} + {bc:.3f}*cmc + {br:.3f}*ramp + {bd:.3f}*draw")
    print(f"residual sd: {np.std(sim[unc] - X @ coef):.2f} lands")
    print(f"\nanchored formula (level pinned to consensus avg-CMC-{ANCHOR_CMC}->{ANCHOR_LANDS:.0f}):")
    print(f"  recommended = {ANCHOR_LANDS:.0f} + {bc:.2f}*(cmc-{ANCHOR_CMC}) "
          f"+ {br:.3f}*ramp + {bd:.3f}*draw   [clamp]")
    print("  NOTE: review the draw slope — draw-heavy decks tend to censor at the "
          "floor, which can flip its sign. A conventional small negative is safer.")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--decks-file", default="data/sample_decks.json",
                   help="JSON list of Archidekt deck URLs.")
    p.add_argument("--out", default="land_fit_data.json")
    p.add_argument("--sweep-min", type=int, default=28)
    p.add_argument("--sweep-max", type=int, default=44)
    p.add_argument("--sims", type=int, default=800)
    p.add_argument("--turns", type=int, default=14)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--workers", type=int, default=0, help="0 = all CPUs")
    p.add_argument("--fit-only", action="store_true", help="Skip collection; re-fit --out.")
    args = p.parse_args()

    workers = args.workers or (os.cpu_count() or 4)
    if args.fit_only:
        results = json.load(open(args.out))
    else:
        urls = json.load(open(args.decks_file))
        sweep = list(range(args.sweep_min, args.sweep_max + 1))
        print(f"collecting {len(urls)} decks, sweep {sweep[0]}-{sweep[-1]}, "
              f"sims={args.sims}, turns={args.turns}, workers={workers}", flush=True)
        results = collect(urls, args.out, sweep, args.sims, args.turns, args.seed, workers)
    fit(results, args.sweep_min, args.sweep_max)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
