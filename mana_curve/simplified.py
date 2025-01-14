import argparse
import pprint
pp = pprint.PrettyPrinter(indent=4)

import numpy as np
from collections import Counter
from tqdm import tqdm
import termplotlib as tpl


def get_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mana_curve",
        type=int,
        nargs="+", 
        # mv:   [0,  1,  2,  3,  4,  5,  6,  7,  8+]
        # default=[0,  7, 15, 21, 19,  4,  3,  2,  0], # base R&R connection
        default=[0,  6, 13, 19, 17,  4,  2,  1,  0], # with farseek and steve land cuts (38 lands)
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
        default=33,
    )
    parser.add_argument(
        "--land_range",
        type=int,
        default=11,
    )
    parser.add_argument(
        "--step_size",
        type=int,
        default=1,
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
    parser.add_argument(
        "--verbose",
        action="store_true",
    )
    return parser

def main(config):
    pp.pprint(config)
    lands_dict = {}

    total_mana_possible = sum([i+1 for i in range(config['num_turns'])])
    mana_values = [i for i in range(len(config["mana_curve"]))] + [-1]
    mana_curve = config["mana_curve"]
    for commander_mc in config["commanders"]:
        mana_curve[commander_mc] -= 1

    land_counts = [config['num_lands'] + i for i in range(0 , config['land_range'], config['step_size'])]
    for land_count in tqdm(land_counts):
        lands_dict[land_count] = {}
        nonland_count = config["num_cards"] - land_count - len(config["commanders"])

        mana_curve_total = sum(mana_curve)
        weights = [mc * (nonland_count / mana_curve_total) for mc in mana_curve] + [land_count]  
        # get the non int remainders
        remainders = [weight % 1 for weight in weights]
        remainders_args = np.argsort(remainders)
        int_weights = [round(weight) for weight in weights]
        a = 0
        while config["num_cards"] - len(config["commanders"]) < sum(int_weights):
            if not remainders[remainders_args[a]] == 0:
                int_weights[remainders_args[a]] -= 1
            a += 1
        a = -1
        while config["num_cards"] - len(config["commanders"]) > sum(int_weights):
            if not remainders[remainders_args[a]] == 0:
                int_weights[remainders_args[a]] += 1
            a -= 1

        curvout_turn = []
        screwed_turn = []
        mana_expenditure = []
        mulligan_list = []
        turns_mana_spent_list = []
        for sim in tqdm(range(config["num_simulations"]), leave=False):
            # create deck
            deck = []
            for i, weight in enumerate(int_weights):
                deck += [mana_values[i]] * weight
            commanders = [c for c in config["commanders"]]
            cards_in_deck = len(deck)

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

            mulligan_list.append(mulligans)
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
    
        lands_dict[land_count]["!mana_expenditure"] = np.mean(mana_expenditure)
        lands_dict[land_count]["!mana_stdev"] = np.std(mana_expenditure)
        lands_dict[land_count]["!mana_IDR"] = f"{np.percentile(mana_expenditure, 10)} - {np.percentile(mana_expenditure, 90)}"
        lands_dict[land_count]["curved_out_until"] = np.mean(curvout_turn)
        lands_dict[land_count]["screwed"] = np.mean(screwed_turn)
        lands_dict[land_count]["turns_mana_spent"] = np.round(np.mean(turns_mana_spent_list, axis=0),2)
        lands_dict[land_count]["mulligans"] = np.mean(mulligan_list)
        lands_dict[land_count]["cards_in_deck"] = cards_in_deck
        lands_dict[land_count]["deck_counts"] = int_weights

        if config['verbose']:
            print(f'\nmana expenditure for {land_count} lands: {lands_dict[land_count]["!mana_expenditure"]} +/- {lands_dict[land_count]["!mana_stdev"]} (IDR: {lands_dict[land_count]["!mana_IDR"]})')
            fig = tpl.figure()
            counts, bin_edges = np.histogram(mana_expenditure, bins=10, range=(0, total_mana_possible))
            fig.hist(counts, bin_edges, orientation='horizontal', force_ascii=False)
            fig.show()
            print('\n')
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