#!/usr/bin/env python3
"""Generate demo plots for the mana-ramp analysis panel.

The figure is intentionally focused on the deckbuilding question:

  - As rocks are added or removed, how do expected unspent mana and stuck
    cards move?
  - How often does each early-rock draw scenario happen?

Draw spells are included in the spendable curve by ``classify_for_curve_value``,
so this visualization shows whether ramp mana has non-ramp spells to spend on.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from auto_goldfish.effects.card_database import DEFAULT_REGISTRY
from auto_goldfish.engine.goldfisher import Goldfisher
from auto_goldfish.optimization.curve_value import classify_for_curve_value
from auto_goldfish.optimization.ramp_analysis import (
    PHASE1_TURN,
    RampMCPanel,
    build_ramp_variants,
    compute_ramp_mc_panel,
)


DEFAULT_DECKS = ["hermes_cantripping_through_time"]
ALL_DEMO_DECKS = [
    "equilibrium-demo",
    "mana-starved-demo",
    "overlanded-cantrips-demo",
    "hermes_cantripping_through_time",
    "the_rr_connection",
]
TURNS = 8
DEFAULT_SIGNATURE_SIMS = 500
DEFAULT_MC_TRIALS = 3000
DEFAULT_OUTPUT_DIR = REPO_ROOT / ".context" / "plots" / "ramp_analysis"


@dataclass(frozen=True)
class RampPlotData:
    labels: List[str]
    rock_counts: List[int]
    value_slots: List[float]
    expected_unspent_mana: List[float]
    expected_stuck_cards: List[float]
    scenario_probabilities: Dict[int, List[float]]


def load_deck(name: str) -> List[Dict[str, Any]]:
    path = REPO_ROOT / "decks" / name / f"{name}.json"
    with path.open() as f:
        return json.load(f)


def measure_draw_signature(
    deck_name: str,
    cards: List[Dict[str, Any]],
    turns: int,
    sims: int,
    seed: int,
) -> List[float]:
    gf = Goldfisher(
        cards,
        turns=turns,
        sims=sims,
        record_results=None,
        seed=seed,
        deck_name=deck_name,
    )
    result = gf.simulate()
    return list(result.mean_cumulative_draws_per_turn)


def ramp_plot_data(panels: Iterable[RampMCPanel]) -> RampPlotData:
    panel_list = list(panels)
    return RampPlotData(
        labels=[p.variant.label for p in panel_list],
        rock_counts=[p.variant.R for p in panel_list],
        value_slots=[sum(p.variant.spendable_curve.values()) for p in panel_list],
        expected_unspent_mana=[p.expected_unspent_mana for p in panel_list],
        expected_stuck_cards=[p.expected_stuck_cards for p in panel_list],
        scenario_probabilities={
            b: [p.scenario_probs.get(b, 0.0) for p in panel_list]
            for b in (0, 1, 2, 3)
        },
    )


def build_panels(
    deck_name: str,
    cards: List[Dict[str, Any]],
    turns: int,
    signature_sims: int,
    mc_trials: int,
    seed: int,
) -> tuple[List[RampMCPanel], List[float], Dict[str, Any]]:
    cls = classify_for_curve_value(cards, registry=DEFAULT_REGISTRY)
    base_R = len(cls["ramp_specs"])
    spendable_curve = {int(c): float(n) for c, n in cls["V_curve"].items()}
    signature = measure_draw_signature(
        deck_name=deck_name,
        cards=cards,
        turns=turns,
        sims=signature_sims,
        seed=seed,
    )
    variants = build_ramp_variants(
        base_R=base_R,
        spendable_curve=spendable_curve,
        include_no_ramp=True,
    )
    panels = [
        compute_ramp_mc_panel(
            variant=v,
            L=cls["L"],
            commanders=cls["commanders"],
            D=cls["D"],
            T=turns,
            n_trials=mc_trials,
            seed=seed,
            per_turn_cumulative_draws=signature,
        )
        for v in variants
    ]
    return panels, signature, cls


def plot_ramp_analysis(
    deck_name: str,
    data: RampPlotData,
    signature: List[float],
    cls: Dict[str, Any],
    output_dir: Path,
    mc_trials: int,
    signature_sims: int,
) -> Path:
    import matplotlib.pyplot as plt

    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{deck_name}_ramp_analysis_demo.png"

    x = list(range(len(data.labels)))
    cards_by_turn_5 = signature[PHASE1_TURN - 1] if len(signature) >= PHASE1_TURN else 0.0
    current_idx = next(
        (i for i, label in enumerate(data.labels) if label == "current"),
        len(data.labels) // 2,
    )
    base_value_slots = data.value_slots[current_idx] if data.value_slots else 0.0
    avg_value_cmc = 0.0
    if base_value_slots > 0:
        curve = cls["V_curve"]
        avg_value_cmc = sum(int(c) * int(n) for c, n in curve.items()) / base_value_slots

    fig, (ax_trade, ax_prob) = plt.subplots(
        2,
        1,
        figsize=(11, 8),
        sharex=True,
        gridspec_kw={"height_ratios": [1.25, 1.0]},
    )
    fig.suptitle(
        (
            f"{deck_name}: ramp-count tradeoff\n"
            f"R={data.rock_counts[current_idx]}  "
            f"V_slots={base_value_slots:.0f}  "
            f"draw_spells_in_value={cls['draw_count']}  "
            f"avg_value_cmc={avg_value_cmc:.2f}  "
            f"cards_by_turn_{PHASE1_TURN}={cards_by_turn_5:.2f}"
        ),
        fontsize=13,
    )

    ax_trade.plot(
        x,
        data.expected_unspent_mana,
        marker="o",
        linewidth=2.2,
        color="#1f77b4",
        label="E[unspent mana]",
    )
    ax_trade.set_ylabel("Expected unspent mana", color="#1f77b4")
    ax_trade.tick_params(axis="y", labelcolor="#1f77b4")
    ax_trade.grid(axis="y", alpha=0.25)

    ax_stuck = ax_trade.twinx()
    ax_stuck.plot(
        x,
        data.expected_stuck_cards,
        marker="s",
        linewidth=2.2,
        color="#d62728",
        label="E[stuck cards]",
    )
    ax_stuck.set_ylabel("Expected stuck cards", color="#d62728")
    ax_stuck.tick_params(axis="y", labelcolor="#d62728")

    ax_trade.axvline(current_idx, color="#444444", linestyle="--", linewidth=1.2)
    ax_trade.text(
        current_idx,
        max(data.expected_unspent_mana or [0]),
        " current",
        color="#444444",
        va="top",
    )
    lines, labels = ax_trade.get_legend_handles_labels()
    lines2, labels2 = ax_stuck.get_legend_handles_labels()
    ax_trade.legend(lines + lines2, labels + labels2, loc="upper left")
    ax_trade.set_title("Outcome tradeoff across rock variants")

    bottoms = [0.0 for _ in x]
    colors = {
        0: "#4e79a7",
        1: "#59a14f",
        2: "#f28e2b",
        3: "#e15759",
    }
    for bucket in (0, 1, 2, 3):
        vals = [p * 100 for p in data.scenario_probabilities[bucket]]
        label = f"P(K={bucket})" if bucket < 3 else "P(K>=3)"
        ax_prob.bar(x, vals, bottom=bottoms, color=colors[bucket], label=label)
        bottoms = [b + v for b, v in zip(bottoms, vals)]
    ax_prob.axvline(current_idx, color="#444444", linestyle="--", linewidth=1.2)
    ax_prob.set_ylabel("Scenario probability")
    ax_prob.set_ylim(0, 100)
    ax_prob.set_yticks([0, 25, 50, 75, 100])
    ax_prob.set_yticklabels(["0%", "25%", "50%", "75%", "100%"])
    ax_prob.set_title("Rocks drawn by turn 5 after measured draw signature")
    ax_prob.legend(ncol=4, loc="upper center", bbox_to_anchor=(0.5, 0.99))

    ax_prob.set_xticks(x)
    ax_prob.set_xticklabels(
        [
            f"{label}\nR={r}\nV={v:.0f}"
            for label, r, v in zip(data.labels, data.rock_counts, data.value_slots)
        ],
        rotation=0,
    )
    fig.text(
        0.5,
        0.018,
        f"MC trials/variant={mc_trials}; draw-signature sims={signature_sims}",
        ha="center",
        fontsize=10,
        color="#555555",
    )

    fig.tight_layout(rect=[0, 0.045, 1, 0.92])
    fig.savefig(out_path, dpi=160)
    plt.close(fig)
    return out_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--deck",
        action="append",
        dest="decks",
        help="Cached deck name to plot. May be provided multiple times.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Plot all cached ramp-analysis demo decks.",
    )
    parser.add_argument("--turns", type=int, default=TURNS)
    parser.add_argument("--signature-sims", type=int, default=DEFAULT_SIGNATURE_SIMS)
    parser.add_argument("--mc-trials", type=int, default=DEFAULT_MC_TRIALS)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    decks = ALL_DEMO_DECKS if args.all else (args.decks or DEFAULT_DECKS)
    for deck_name in decks:
        try:
            cards = load_deck(deck_name)
        except FileNotFoundError:
            print(f"SKIP {deck_name}: not cached")
            continue
        panels, signature, cls = build_panels(
            deck_name=deck_name,
            cards=cards,
            turns=args.turns,
            signature_sims=args.signature_sims,
            mc_trials=args.mc_trials,
            seed=args.seed,
        )
        out_path = plot_ramp_analysis(
            deck_name=deck_name,
            data=ramp_plot_data(panels),
            signature=signature,
            cls=cls,
            output_dir=args.output_dir,
            mc_trials=args.mc_trials,
            signature_sims=args.signature_sims,
        )
        print(out_path)


if __name__ == "__main__":
    main()
