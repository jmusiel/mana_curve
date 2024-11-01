import argparse
import pprint
from pyrchidekt.api import getDeckById
import json
import os
pp = pprint.PrettyPrinter(indent=4)

def get_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--deck_url",
        type=str, 
        default="https://archidekt.com/decks/9887623/kess_mana_curve_template",
    )
    parser.add_argument(
        "--deck_name",
        type=str,
        default="kess"
    )
    return parser

def main(config):
    pp.pprint(config)

    os.makedirs(config['deck_name'], exist_ok=True)
    save_path = os.path.join(config['deck_name'],f"{config['deck_name']}_template.json")

    deck_list = []
    counts = {
        "flex": 0,
        "locked": 0,
        "land": 0,
        "value": 0,
        "ramp": 0,
        "draw": 0,
        "commander": 0,
    }
    

    deckid = int(config['deck_url'].split('/')[-2])

    deck = getDeckById(deckid)
    for category in deck.categories:
        print(f"{category.name}")
        for card in category.cards:
            if "~" in category.name or category.name == "Commander":
                card_dict = {}
                card_dict["name"] = card.card.oracle_card.name
                card_dict["quantity"] = card.quantity
                # quantity = card.quantity
                card_dict["flex"] = False
                card_dict["is_land"] = False
                card_dict["is_ramp"] = False
                card_dict["is_draw"] = False
                card_dict["is_value"] = False
                card_dict['is_commander'] = False
                catlist = category.name.split("/")
                if category.name == "Commander":
                    card_dict['is_commander'] = True
                    counts['commander'] += card.quantity
                elif catlist[1] == "land":
                    card_dict["is_land"] = True
                    counts['land'] += card.quantity
                elif catlist[1] == "value":
                    card_dict["is_value"] = True
                    counts['value'] += card.quantity
                else:
                    x, purpose, kind, value = catlist
                    if purpose == "ramp":
                        card_dict["is_ramp"] = True
                        card_dict["ramp_type"] = kind
                        card_dict["ramp_amount"] = int(value)
                        counts['ramp'] += card.quantity
                    elif purpose == "draw":
                        card_dict["is_draw"] = True
                        card_dict["draw_type"] = kind
                        card_dict["draw_amount"] = int(value)
                        counts['draw'] += card.quantity

                cmc = card.card.oracle_card.cmc
                if card.custom_cmc is not None:
                    cmc = card.custom_cmc
                card_dict["cmc"] = cmc

                if card.label == "flex":
                    card_dict["flex"] = True
                    counts['flex'] += card.quantity
                else:
                    counts['locked'] += card.quantity

                deck_list.append(card_dict)
            
            print(f"\t{card.quantity} {card.card.oracle_card.name} cmc:{card.card.oracle_card.cmc} custom_cmc:{card.custom_cmc}")
        print("")
    total = 0
    for key, value in counts.items():
        print(f"{key} count: {value}")
        if not key == 'flex' and not key == 'locked':
            total += value
    print(f"total: {total}")

    with open(save_path, 'w') as f:
        json.dump(deck_list, f)

    

if __name__ == "__main__":
    parser = get_parser()
    args = parser.parse_args()
    config = vars(args)
    main(config)
    print("done")