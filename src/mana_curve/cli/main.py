"""CLI entry point for mana_curve simulations."""

from __future__ import annotations

import argparse
import pprint

import numpy as np
from tabulate import tabulate
from tqdm import tqdm

from mana_curve.decklist.archidekt import fetch_and_save
from mana_curve.decklist.loader import get_deckpath, load_decklist
from mana_curve.engine.goldfisher import Goldfisher
from mana_curve.metrics.reporter import save_report

pp = pprint.PrettyPrinter(indent=4)


def get_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MTG Commander deck goldfish simulator")
    parser.add_argument("--deck_name", type=str, default="vren")
    parser.add_argument(
        "--deck_url",
        type=str,
        default="https://archidekt.com/decks/19226307/vrens_murine_marauders",
    )
    parser.add_argument("--turns", type=int, default=10)
    parser.add_argument("--sims", type=int, default=10000)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--min_lands", type=int, default=36)
    parser.add_argument("--max_lands", type=int, default=39)
    parser.add_argument("--cuts", nargs="+", type=str, default=[])
    parser.add_argument("--record_results", type=str, default="quartile")
    parser.add_argument("--seed", type=int, default=None)
    return parser


def run(config: dict) -> None:
    """Main simulation pipeline."""
    pp.pprint(config)

    if config.get("deck_url"):
        fetch_and_save(config["deck_url"], config["deck_name"])

    deck_list = load_decklist(config["deck_name"])
    goldfisher = Goldfisher(deck_list, **config)

    min_lands = config.get("min_lands") or goldfisher.land_count
    max_lands = (config.get("max_lands") or goldfisher.land_count) + 1

    outcomes = []
    distribution_outcomes = []

    for i in tqdm(range(min_lands, max_lands), total=max_lands - min_lands):
        goldfisher.set_lands(i, cuts=config.get("cuts", []))
        result = goldfisher.simulate()

        # Save detailed report
        deck_dir = get_deckpath(config["deck_name"]).replace(
            f"/{config['deck_name']}.json", ""
        )
        save_report(
            result=result,
            decklist=goldfisher.decklist,
            commanders=[c.name for c in goldfisher.commanders],
            output_dir=deck_dir,
            deck_name=goldfisher.deck_name,
        )

        outcomes.append(result.as_row())
        ds = result.distribution_stats
        distribution_outcomes.append([
            i,
            f"{ds.get('top_centile', 0) * 100:.1f}%",
            f"{ds.get('top_decile', 0) * 100:.1f}%",
            f"{ds.get('top_quartile', 0) * 100:.1f}%",
            f"{ds.get('top_half', 0) * 100:.1f}%",
            f"{ds.get('low_half', 0) * 100:.1f}%",
            f"{ds.get('low_quartile', 0) * 100:.1f}%",
            f"{ds.get('low_decile', 0) * 100:.1f}%",
            f"{ds.get('low_centile', 0) * 100:.1f}%",
        ])

    outcomes_arr = np.array(outcomes)
    max_mana = outcomes_arr[:, 0][np.argmax(outcomes_arr[:, 1])]
    max_consistency = outcomes_arr[:, 0][np.argmax(outcomes_arr[:, 2])]
    min_bad_turns = outcomes_arr[:, 0][np.argmin(outcomes_arr[:, 3])]
    min_mid_turns = outcomes_arr[:, 0][np.argmin(outcomes_arr[:, 4])]

    con_threshold = result.con_threshold * 100
    print(f"\n-----------------------------------")
    print(
        f"{config['deck_name']} ({config['turns']} turns, {config['sims']} sims, "
        f"{min_lands}-{max_lands - 1} lands) - max mana @ {max_mana}, "
        f"max consistency @ {max_consistency}, min bad turns @ {min_bad_turns}, "
        f"min mid turns @ {min_mid_turns}"
    )
    print(f"-----------------------------------")
    print(
        tabulate(
            outcomes,
            headers=[
                "Land Ct", "Mana (EV)", "Consistency", "Bad Turns", "Mid Turns",
                "Lands", "Mulls", "Draws", "25th", "50th", "75th",
                f"{int(con_threshold)}th% Frac", f"{int(con_threshold)}th% Game",
            ],
        )
    )

    print("\nDistribution Statistics:")
    print("------------------------")
    print(
        tabulate(
            distribution_outcomes,
            headers=[
                "Land Ct", "Top 1%", "Top 10%", "Top 25%", "Top 50%",
                "Low 50%", "Low 25%", "Low 10%", "Low 1%",
            ],
            tablefmt="simple",
        )
    )


def main() -> None:
    parser = get_parser()
    args = parser.parse_args()
    config = vars(args)
    run(config)
    print("done")


if __name__ == "__main__":
    main()
