import argparse
import pprint
from pyrchidekt.api import getDeckById
import json
import os
import scrython
from tqdm import tqdm
import time
pp = pprint.PrettyPrinter(indent=4)

def get_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--deck_url",
        type=str, 
        default="https://archidekt.com/decks/7947868/kesss_cozy_cantrips",
    )
    parser.add_argument(
        "--deck_name",
        type=str,
        default="kess"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
    )
    return parser

def main(config):
    deck_list = get_decklist(config)
    save_path = get_deckpath(config['deck_name'])
    with open(save_path, 'w') as f:
        json.dump(deck_list, f, indent=4)

def get_decklist(config):
    pp.pprint(config)

    deck_list = []

    deckid = int(config['deck_url'].split('/')[-2])

    deck = getDeckById(deckid)
    categories_in_deck = {cat.name:cat.included_in_deck for cat in deck.categories}
    cards = [card for card in deck.cards if categories_in_deck[card.categories[0]]]
    for card in tqdm(cards, desc="Getting decklist"):
        for i in range(card.quantity):
            if categories_in_deck[card.categories[0]]:
                card_dict = {}
                card_dict["name"] = card.card.oracle_card.name
                card_dict["quantity"] = 1
                card_dict["oracle_cmc"] = card.card.oracle_card.cmc
                card_dict["cmc"] = card.card.oracle_card.cmc
                if card.custom_cmc is not None:
                    card_dict["cmc"] = card.custom_cmc
                card_dict["cost"] = card.card.oracle_card.mana_cost
                card_dict["text"] = card.card.oracle_card.text
                card_dict["sub_types"] = card.card.oracle_card.sub_types
                card_dict["super_types"] = card.card.oracle_card.super_types
                card_dict["types"] = card.card.oracle_card.types
                card_dict["identity"] = card.card.oracle_card.color_identity
                card_dict["default_category"] = card.card.oracle_card.default_category
                card_dict["user_category"] = card.categories[0]
                card_dict["commander"] = card.categories[0] == 'Commander'
                if card.card.oracle_card.faces:
                    card_dict["cost"] = None
                    card_dict["text"] = None
                    card_dict["sub_types"] = []
                    card_dict["super_types"] = []
                    card_dict["types"] = []
                    for face in card.card.oracle_card.faces:
                        if card_dict["cost"] is None:
                            card_dict["cost"] = face['manaCost'] + "//"
                        else:
                            card_dict["cost"] += face['manaCost']
                        if card_dict["text"] is None:
                            card_dict["text"] = face['text'] + "//"
                        else:
                            card_dict["text"] += face['text']
                        card_dict["sub_types"].extend(face['subTypes'])
                        card_dict["super_types"].extend(face['superTypes'])
                        card_dict["types"].extend(face['types'])
                        

                # scrycard = scrython.cards.Named(fuzzy=card_dict['name'])
                # time.sleep(0.05)
                if config['verbose']: print(f"\t{card_dict['quantity']} {card_dict['name']} cmc:{card_dict['oracle_cmc']} custom_cmc:{card_dict['cmc']}")

                deck_list.append(card_dict)


    return deck_list

def get_deckpath(deck_name):
    package_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    deck_dir = os.path.join(package_dir, "decks", deck_name)
    os.makedirs(deck_dir, exist_ok=True)
    deck_path = os.path.join(deck_dir, f"{deck_name}.json")
    return deck_path

def load_decklist(deck_name):
    decklist_path = get_deckpath(deck_name)
    with open(decklist_path, 'r') as f:
        decklist = json.load(f)
    return decklist
    
def get_basic_island():
    return {
        "name": "Island",
        "quantity": 1,
        "oracle_cmc": 0,
        "cmc": 0,
        "cost": "",
        "text": "({T}: Add {U}.)",
        "sub_types": [
            "Island"
        ],
        "super_types": [
            "Basic"
        ],
        "types": [
            "Land"
        ],
        "identity": [
            "Blue"
        ],
        "default_category": None,
        "user_category": "Land",
        "commander": False
    }

def get_hare_apparent():
    return {
        "name": "Hare Apparent",
        "quantity": 1,
        "oracle_cmc": 2,
        "cmc": 2,
        "cost": "{1}{W}",
        "text": "When this creature enters, create a number of 1/1 white Rabbit creature tokens equal to the number of other creatures you control named Hare Apparent.\nA deck can have any number of cards named Hare Apparent.",
        "sub_types": [
            "Rabbit",
            "Noble"
        ],
        "super_types": [],
        "types": [
            "Creature"
        ],
        "identity": [
            "White"
        ],
        "default_category": "Tokens",
        "user_category": "hare apparent",
        "commander": False
    }

if __name__ == "__main__":
    parser = get_parser()
    args = parser.parse_args()
    config = vars(args)
    main(config)
    print("done")