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
        "--mulligan_at_least_one_spell",
        type=int, 
        nargs="+",
        default=None,
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
    parser.add_argument(
        "--commander_effect",
        type=str,
        default="none",
    )
    return parser

def commander_effect(played_cards, mana_available, mana_spent, deck, hand, lands_available, name):
    if name == "lurrus":
        # cantrip with bauble
        if 0 in hand:
            hand.remove(0)
            played_cards.append(0)
            card_drawn = np.random.choice(deck)
            hand.append(card_drawn)
            deck.remove(card_drawn)
        # cantrip with any 2 drop
        if 2 in hand and lands_available == 2:
            if 0 == np.random.choice([0,1]):
                mana_available -= 2
                mana_spent += 2
                hand.remove(2)
                played_cards.append(2)
                card_drawn = np.random.choice(deck)
                hand.append(card_drawn)
                deck.remove(card_drawn)
        if lands_available > 3:
            # recur cards with lurrus
            to_play = None
            if 2 in played_cards:
                to_play = 2
            elif 1 in played_cards:
                to_play = 1
            if to_play:
                mana_available -= to_play
                mana_spent += to_play
                played_cards.remove(to_play)

            # draw an extra card if played a 2 drop (approximates draw spell)
            if to_play == 2 or 2 in hand:
                if 0 == np.random.choice([0,1]):
                    card_drawn = np.random.choice(deck)
                    hand.append(card_drawn)
                    deck.remove(card_drawn)
    
    if name == "kess":
        if 1 in hand:
            mana_available -= 1
            mana_spent += 1
            hand.remove(1)
            played_cards.append(1)
            card_drawn = np.random.choice(deck)
            hand.append(card_drawn)
            deck.remove(card_drawn)
        if lands_available > 4 and len(played_cards)>=2*lands_available:
            # recur cards with kess
            to_play = min(played_cards)
            if to_play == 0:
                played_cards.remove(to_play)
                to_play = min(played_cards)
            if to_play <= mana_available:
                mana_available -= to_play
                mana_spent += to_play
                played_cards.remove(to_play)
                if to_play == 1:
                    card_drawn = np.random.choice(deck)
                    hand.append(card_drawn)
                    deck.remove(card_drawn)

        
    return played_cards, mana_available, mana_spent, deck, hand

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
        cards_remaining = []
        total_lands_played = []
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
                    if config["mulligan_at_least_one_spell"]:
                        for spell in config["mulligan_at_least_one_spell"]:
                            if hand_count[spell] > 0:
                                break
                    else:
                        break
                if initial_hand_size <= config["mulligan_to_hand_size"]:
                    break
                if mulligans >= 1:
                    initial_hand_size -= 1
                mulligans += 1

            mulligan_list.append(mulligans)
            hand = list(hand)
            for card in hand:
                deck.remove(card)
            # play game
            total_mana_spent = 0
            lands_available = 0
            curved_out_until = config["num_turns"]
            turns_mana_spent = []
            played_cards = []
            screwed = config["num_turns"]
            for i in range(config["num_turns"]):
                turn += 1
                card_drawn = np.random.choice(deck)
                hand.append(card_drawn)
                deck.remove(card_drawn)
                if -1 in hand:
                    lands_available += 1
                    hand.remove(-1)
                    played_cards.append(-1)
                elif screwed == config["num_turns"]:
                    screwed = turn
                mana_available = lands_available
                mana_spent = 0
                if mana_available in commanders:
                    mana_spent = mana_available
                    commanders.remove(mana_available)
                    mana_available = 0
                else:
                    played_cards, mana_available, mana_spent, deck, hand = commander_effect(played_cards, mana_available, mana_spent, deck, hand, lands_available, config["commander_effect"])
                    playable_cards = sorted([card for card in hand if card <= lands_available and card != -1])
                    while playable_cards:
                        played_card = playable_cards.pop()
                        if played_card <= mana_available:
                            mana_spent += played_card
                            hand.remove(played_card)
                            played_cards.append(played_card)
                            mana_available -= played_card
                total_mana_spent += mana_spent
                turns_mana_spent.append(mana_spent)
                if mana_spent < turn and turn > config["curve_after"]:
                    if curved_out_until == config["num_turns"]:
                        curved_out_until = turn - 1

            curvout_turn.append(curved_out_until)
            screwed_turn.append(screwed)
            mana_expenditure.append(total_mana_spent)
            turns_mana_spent_list.append(turns_mana_spent)
            cards_remaining.append(len(deck))
            total_lands_played.append(lands_available)
            # print(f"total_mana_spent: {total_mana_spent}/{total_mana_possible}, curved_out_until: {curved_out_until}, mulligans: {mulligans}")
    
        lands_dict[land_count]["lands"] = land_count
        lands_dict[land_count]["!mana_expent"] = np.mean(mana_expenditure)
        lands_dict[land_count]["!mana_stdev"] = np.std(mana_expenditure)
        lands_dict[land_count]["!mana_IDR"] = f"{np.percentile(mana_expenditure, 10):.1f} - {np.percentile(mana_expenditure, 90):.1f}"
        lands_dict[land_count]["curved_out_until"] = np.mean(curvout_turn)
        lands_dict[land_count]["screwed"] = np.mean(screwed_turn)
        lands_dict[land_count]["turns_mana_spent"] = np.round(np.mean(turns_mana_spent_list, axis=0),2)
        lands_dict[land_count]["mulligans"] = np.mean(mulligan_list)
        lands_dict[land_count]["deck_counts"] = int_weights
        lands_dict[land_count]["cards_drawn"] = cards_in_deck - np.mean(cards_remaining)
        lands_dict[land_count]["lands_played"] = np.mean(total_lands_played)

        if config['verbose']:
            print(f'\nmana expenditure for {land_count} lands: {lands_dict[land_count]["!mana_expent"]} +/- {lands_dict[land_count]["!mana_stdev"]} (IDR: {lands_dict[land_count]["!mana_IDR"]})')
            fig = tpl.figure()
            counts, bin_edges = np.histogram(mana_expenditure, bins=10, range=(0, total_mana_possible))
            fig.hist(counts, bin_edges, orientation='horizontal', force_ascii=False)
            fig.show()
            print('\n')
    # pp.pprint(lands_dict)
    columns = ""
    lengths = []
    for key, val in lands_dict[land_count].items():
        colstring = f"{key} "
        if isinstance(val, float):
            rowstring = f"{val:.2f} "
        else:
            rowstring = f"{val} "

        length = max(len(colstring), len(rowstring))
        lengths.append(length)
        blankstring = ""
        if length > len(colstring):
            blankstring = " " * (length - len(colstring))
        colstring += blankstring
        columns += colstring
    print(columns)
    for land_count in land_counts:
        row = ""
        for length, key in zip(lengths,lands_dict[land_count].keys()):
            val = lands_dict[land_count][key]
            if isinstance(val, float):
                rowstring = f"{val:.2f} "
            else:
                rowstring = f"{val} "
            blankstring = ""
            if length > len(rowstring):
                blankstring = " " * (length - len(rowstring))
            rowstring += blankstring
            row += rowstring
        print(row)
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