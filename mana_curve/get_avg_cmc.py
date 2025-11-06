import argparse
import pprint
from mana_curve.decklist_model.decklist import get_decklist
import numpy as np

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
        ],
    )
    return parser

def card_is_land(card):
    if "Land" in card['types']:
        return True
    if "rien Revealed" in card['name']:
        return True
    return False

def main(config):
    pp = pprint.PrettyPrinter(indent=4)
    pp.pprint(config)

    decklists = []
    avgcmcs = []
    for deck_url in config['deck_urls']:
        deck_name = deck_url.split('/')[-1]
        decklist = get_decklist({'deck_url': deck_url, 'verbose': False})
        decklists.append(decklist)

        avgcmc = 0
        nonland_count = 0
        for card in decklist:
            if not card_is_land(card):
                avgcmc += card['cmc']
                nonland_count += 1
            if not card['cmc'] == card['oracle_cmc']:
                print(f"{card['name']} cmc: {card['cmc']}")
        avgcmc /= nonland_count
        avgcmcs.append(avgcmc)
        print(f"{deck_name}: avg_cmc: {avgcmcs[-1]} ({nonland_count} spells)")
        print("\n")

    print("done")

if __name__ == "__main__":
    parser = get_parser()
    args = parser.parse_args()
    config = vars(args)
    main(config)