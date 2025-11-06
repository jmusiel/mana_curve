import argparse
import pprint
from mana_curve.decklist_model.decklist import get_decklist
import numpy as np
import pandas as pd

def get_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--deck_urls",
        type=str, 
        nargs="+",
        default=[
            "https://archidekt.com/decks/9699790/santas_etb_workshop",
            "https://archidekt.com/decks/16391355/kesss_chill_charms",
            "https://archidekt.com/decks/81320/the_rr_connection",
            "https://archidekt.com/decks/1930237/riku_because_riku_is_bonkers",
            "https://archidekt.com/decks/9538770/hms_her_majestys_slivers",
            "https://archidekt.com/decks/16113063/mycotyrants_mushroom_mill",
            "https://archidekt.com/decks/9603710/rubys_ripjaw_raptors",
            "https://archidekt.com/decks/12122030/cantripping_through_time",
            "https://archidekt.com/decks/3390122/will_the_real_mr_markov_please_stand_up",
            "https://archidekt.com/decks/15749155/cunning_conquerors_celerity",
            "https://archidekt.com/decks/1847823/good_ol_superfriends",
            "https://archidekt.com/decks/482754/bantchantress",
            "https://archidekt.com/decks/1856247/lords_landed_libations",
        ],
    )
    parser.add_argument(
        "--include_cuts_and_adds",
        "-a",
        action="store_true",
    )
    return parser

def card_is_land(card):
    if "Land" in card['types']:
        return True
    if "rien Revealed" in card['name']:
        return True
    return False

def print_terminal_histogram(values):
    max_value = max(values)
    min_value = min(values)
    num_bins = max_value - min_value + 1
    bins = [0] * num_bins
    for value in values:
        bins[value - min_value] += 1
    for i in range(num_bins):
        print(f"{i + min_value}: {bins[i]}")

def main(config):
    pp = pprint.PrettyPrinter(indent=4)
    pp.pprint(config)

    decklists = []
    avgcmcs = []
    deck_names = []
    spell_counts = []
    land_counts = []
    total_counts = []
    for deck_url in config['deck_urls']:
        deck_name = deck_url.split('/')[-1]
        decklist = get_decklist({'deck_url': deck_url, 'verbose': False, 'include_cuts_and_adds': config['include_cuts_and_adds']})
        decklists.append(decklist)

        cmcs = []
        nonland_count = 0
        land_count = 0
        commander_mvs = []
        for card in decklist:
            if card['commander']:
                commander_mvs.append(card['cmc'])
            elif not card_is_land(card):
                cmcs.append(card['cmc'])
                nonland_count += 1
            else:
                land_count += 1
            if not card['cmc'] == card['oracle_cmc']:
                print(f"{card['name']} cmc: {card['cmc']}")
        avgcmc = np.mean(cmcs)
        avgcmcs.append(avgcmc)
        deck_names.append(deck_name)
        spell_counts.append(nonland_count)
        land_counts.append(land_count)
        total_counts.append(nonland_count + land_count)
        print_terminal_histogram(cmcs)
        print(f"{deck_name}: avg_cmc: {avgcmc} ({nonland_count} spells, {land_count} lands)")
        print(f"commander mvs: {commander_mvs}")
        print("\n")

    df = pd.DataFrame({'deck_name': deck_names, 'avg_cmc': avgcmcs, 'spell_counts': spell_counts, 'land_counts': land_counts, 'total': total_counts})
    # sort by by avg_cmc
    df = df.sort_values('avg_cmc')
    print(df.to_string())

    print("done")

if __name__ == "__main__":
    parser = get_parser()
    args = parser.parse_args()
    config = vars(args)
    main(config)