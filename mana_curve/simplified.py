import argparse
import pprint
pp = pprint.PrettyPrinter(indent=4)

import numpy as np
from collections import Counter
from tqdm import tqdm


def get_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mana_curve",
        type=int,
        nargs="+", 
        # mv:   [0,  1,  2,  3,  4,  5,  6,  7,  8+]
        default=[0,  7, 15, 21, 19,  4,  3,  2,  0],
    )
    parser.add_argument(
        "--num_cards",
        type=int, 
        default=100,
    )
    parser.add_argument(
        "--commanders",
        type=int,
        nargs="+", 
        default=[3, 5],
    )
    parser.add_argument(
        "--num_lands",
        type=int,
        default=35,
    )
    parser.add_argument(
        "--land_range",
        type=int,
        default=10,
    )
    parser.add_argument(
        "--mulligan_max_lands",
        type=int, 
        default=5,
    )
    parser.add_argument(
        "--mulligan_min_lands",
        type=int, 
        default=3,
    )
    parser.add_argument(
        "--starting_hand_size",
        type=int, 
        default=7,
    )
    parser.add_argument(
        "--mulligan_to_hand_size",
        type=int, 
        default=6,
    )
    parser.add_argument(
        "--num_turns",
        type=int, 
        default=10,
    )
    parser.add_argument(
        "--num_simulations",
        type=int, 
        default=10000,
    )
    parser.add_argument(
        "--curve_after",
        type=int,
        default=2,
    )
    return parser

def main(config):
    pp.pprint(config)
    lands_dict = {}

    total_mana_possible = sum([i for i in range(config['num_turns'])])
    mana_values = [i for i in range(len(config["mana_curve"]))] + [-1]
    mana_curve = config["mana_curve"]
    for commander_mc in config["commanders"]:
        mana_curve[commander_mc] -= 1

    land_counts = [config['num_lands'] + i for i in range(config['land_range'])]
    for land_count in tqdm(land_counts):
        lands_dict[land_count] = {}
        nonland_count = config["num_cards"] - land_count - len(config["commanders"])

        mana_curve_total = sum(mana_curve)
        weights = [mc * (nonland_count/ mana_curve_total) for mc in mana_curve] + [land_count]  

        curvout_turn = []
        screwed_turn = []
        mana_expenditure = []
        turns_mana_spent_list = []
        for sim in tqdm(range(config["num_simulations"]), leave=False):
            # create deck
            deck = []
            for i, weight in enumerate(weights):
                deck += [mana_values[i]] * round(weight)
            commanders = [c for c in config["commanders"]]

            # draw initial hand
            turn = 0
            mulligans = 0
            initial_hand_size = 7
            while True:
                hand = np.random.choice(deck, initial_hand_size, replace=False)
                hand_count = Counter(hand)
                if hand_count[-1] <= config["mulligan_max_lands"] and hand_count[-1] >= config["mulligan_min_lands"]:
                    break
                if initial_hand_size <= config["mulligan_to_hand_size"]:
                    break
                if mulligans >= 1:
                    initial_hand_size -= 1
                mulligans += 1

            hand = list(hand)
            # play game
            total_mana_spent = 0
            lands_available = 0
            curved_out_until = 0
            turns_mana_spent = []
            screwed = 0
            curving_out = True
            for i in range(config["num_turns"]):
                turn += 1
                hand.append(np.random.choice(deck))
                if -1 in hand:
                    lands_available += 1
                    hand.remove(-1)
                elif screwed == 0:
                    screwed = turn
                mana_available = lands_available
                mana_spent = 0
                if mana_available in commanders:
                    mana_spent = mana_available
                    commanders.remove(mana_available)
                    mana_available = 0
                else:
                    playable_cards = sorted([card for card in hand if card <= lands_available and card != -1])
                    while playable_cards:
                        played_card = playable_cards.pop()
                        if played_card <= mana_available:
                            mana_spent += played_card
                            hand.remove(played_card)
                            mana_available -= played_card
                total_mana_spent += mana_spent
                turns_mana_spent.append(mana_spent)
                if mana_spent < turn and turn > config["curve_after"]:
                    if curving_out:
                        curved_out_until = turn - 1
                    curving_out = False

            curvout_turn.append(curved_out_until)
            screwed_turn.append(screwed)
            mana_expenditure.append(total_mana_spent)
            turns_mana_spent_list.append(turns_mana_spent)
            # print(f"total_mana_spent: {total_mana_spent}/{total_mana_possible}, curved_out_until: {curved_out_until}, mulligans: {mulligans}")
    
        lands_dict[land_count]["curved_out_until"] = np.mean(curvout_turn)
        lands_dict[land_count]["screwed"] = np.mean(screwed_turn)
        lands_dict[land_count]["mana_expenditure"] = np.mean(mana_expenditure)
        lands_dict[land_count]["turns_mana_spent"] = np.round(np.mean(turns_mana_spent_list, axis=0),2)
    pp.pprint(lands_dict)
    print(f"possible expenditure: {total_mana_possible}")

    
    


    # print("mana_curve:", mana_curve)
    # print(f"land_count: {land_count}, nonland_count: {nonland_count}, mana_curve_total: {mana_curve_total}, ratio: {nonland_count/ mana_curve_total}")
    # print(f"weights: {weights}, sum: {sum(weights)}")
    # print(f"mana_values: {mana_values}")
    # print(f"deck: {Counter(deck)}")




if __name__ == "__main__":
    parser = get_parser()
    args = parser.parse_args()
    config = vars(args)
    main(config)
    print("done")