from mana_curve.decklist_model.decklist import get_decklist, load_decklist, get_basic_island
from mana_curve.decklist_model.decklist import main as save_archidekt
from mana_curve.decklist_model.cards import card_factory
import bisect
import copy
import random
from tqdm import tqdm
import numpy as np
from tabulate import tabulate

import argparse
import pprint
pp = pprint.PrettyPrinter(indent=4)

def get_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--deck_name",
        type=str, 
        default="kess",
    )
    parser.add_argument(
        "--deck_url",
        type=str, 
        default=None,
    )
    parser.add_argument(
        "--turns",
        type=int, 
        default=10,
    )
    parser.add_argument(
        "--sims",
        type=int, 
        default=1000,
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
    )
    parser.add_argument(
        "--min_lands",
        type=int,
        default=35,
    )
    parser.add_argument(
        "--max_lands",
        type=int,
        default=39,
    )
    parser.add_argument(
        "--cuts",
        nargs='+',
        type=str,
        default=[
        ],
    )
    return parser

class Goldfisher:
    def __init__(self, decklist_dict, turns, sims, verbose, **kwargs):
        self.commanders = []
        commander_index = 0
        to_pop = []
        for i, card in enumerate(decklist_dict):
            if card['commander']:
                self.commanders.append(card_factory(**card, goldfisher=self, index=commander_index))
                to_pop.append(i)
                commander_index += 1
        to_pop.reverse()
        for i in to_pop:
            decklist_dict.pop(i)

        self.decklist = [card_factory(**card, goldfisher=self, index=i) for i, card in enumerate(decklist_dict)]
        self.turns = turns
        self.sims = sims
        self.mulligans = -1
        self.verbose = verbose
        self.land_count = len([card for card in self.decklist if card.land])
        self.original_card_count = len(self.decklist)

        self.reset()

    def set_lands(self, land_count, cuts=[]):
        cutted = []
        spells_list = []
        lands_list = []
        for card in self.decklist:
            if card.land:
                lands_list.append(card)
            else:
                spells_list.append(card)
        land_diff = land_count - len(lands_list)
        while land_diff > 0:
            lands_list.append(card_factory(**get_basic_island()))
            land_diff -= 1
            if cuts and len(spells_list) + len(lands_list) > self.original_card_count:
                for j, card in enumerate(spells_list):
                    if card.name in cuts:
                        spells_list.remove(card)
                        cutted.append(card.name)
                        break
        while land_diff < 0:
            for card in lands_list:
                if not card.spell:
                    lands_list.remove(card)
                    cutted.append(card.name)
                    break
            land_diff += 1
        updated_decklist = spells_list + lands_list
        self.decklist = []
        for i, card in enumerate(updated_decklist):
            card_dict = vars(card)
            card_dict['goldfisher'] = self
            card_dict['index'] = i
            self.decklist.append(card_factory(**card_dict))
        if cutted:
            print(f"Cutted: {cutted}")
        print(f"Set land count to {land_count} prev {self.land_count} ({len(lands_list)} lands, {len(spells_list)} spells, total {len(self.decklist)})")
        self.land_count = len([card for card in self.decklist if card.land])

        
    def reset(self):
        self.turn = 0
        self.draws = 0
        # reset zones
        self.command_zone = []
        self.deck = []
        self.yard = []
        self.hand = []
        self.battlefield = []
        self.exile = []
        self.lands = []
        # reset commanders and deck
        for card in self.commanders:
            card.zone = self.command_zone
            self.command_zone.append(card.index)
        for card in self.decklist:
            card.zone = self.deck
            self.deck.append(card.index)
        random.shuffle(self.deck)
        # reset effects
        self.mana_production = 0
        self.treasure = 0
        self.per_turn_effects = []
        self.cast_triggers = []
        self.nonpermanent_cost_reduction = 0
        self.permanent_cost_reduction = 0
        self.spell_cost_reduction = 0
        self.creature_cost_reduction = 0

    def draw(self):
        if len(self.deck) == 0:
            if self.verbose: print(f"Draw failed, deck is empty")
            self.draws += 1
            return
        drawn_i = self.deck.pop()
        drawn = self.decklist[drawn_i]
        drawn.zone = self.hand
        self.hand.append(drawn_i)
        self.draws += 1
        if self.verbose: print(f"Draw {drawn.printable}")

    def randomdiscard(self):
        discarded_i = random.choice(self.hand)
        discarded = self.decklist[discarded_i]
        discarded.change_zone(self.yard)
        if self.verbose: print(f"Discarded {discarded.printable}")

    def mulligan(self):
        while True:
            if self.verbose:
                if self.mulligans == -1:
                    print("### Opening hand:")
                else:
                    print(f"### Mulligan #{self.mulligans+1}")
                
            self.reset()
            cards = 7
            if self.mulligans > 0:
                cards -= self.mulligans
            self.mulligans += 1
            lands_in_hand = 0
            for i in range(cards):
                self.draw()
            for i in self.hand:
                card = self.decklist[i]
                if card.land:
                    lands_in_hand += 1
            if lands_in_hand > 2 and lands_in_hand < 5:
                break
            if len(self.hand) < 7:
                break
        if self.verbose: print(f"### Kept {lands_in_hand}/{len(self.hand)} lands/cards")

    def get_mana(self):
        return len(self.lands) + self.mana_production
    
    def get_hand_strings(self):
        return [self.decklist[i].printable for i in self.hand]
    
    def get_playables(self, available_mana):
        playables = []
        for i in self.hand:
            card = self.decklist[i]
            if card.get_current_cost() <= available_mana and card.spell:
                playables.append(card)
        playables = sorted(playables)
        for i in self.command_zone:
            card = self.commanders[i]
            if card.get_current_cost() <= available_mana and card.spell:
                playables.append(card)

        if self.verbose: 
            playables_string = []
            for card in playables:
                if card.commander:
                    playables_string.append(f"{card.cmc}(c)")
                else:
                    playables_string.append(f"{card.cmc}")
            print(f"--Playable Spells: {playables_string}")
        return playables
    
    def play_land(self):
        played_effects = []
        mdfc = None
        land = None
        for i in self.hand:
            card = self.decklist[i]
            if card.land:
                if card.mdfc:
                    mdfc = card
                else:
                    land = card
                    break
        if land is None:
            land = mdfc
        if land is not None:
            land.change_zone(self.lands)
            played_effects.append(land.played_as_land())

        return played_effects
    
    def play_spells(self):
        mana_available = self.get_mana() + self.treasure
        playables = self.get_playables(mana_available)
        played_effects = []
        while playables:
            for card in reversed(playables):
                if card.get_current_cost() <= mana_available:
                    mana_available -= card.get_current_cost()
                    if card.spell and card.nonpermanent:
                        card.change_zone(self.yard)
                    elif card.spell and card.permanent and not card.nonpermanent:
                        card.change_zone(self.battlefield)
                    else:
                        raise ValueError(f"incompatible types {card.types} for card {card.name}")
                    # cast triggers
                    for trigger in self.cast_triggers:
                        trigger.cast_trigger(card)
                    # add to cast triggers
                    if hasattr(card, 'cast_trigger'):
                        self.cast_triggers.append(card)
                    # add to per turn effects
                    if hasattr(card, 'per_turn'):
                        self.per_turn_effects.append(card)
                    # add to played cards
                    played_effects.append(card.when_played())
            playables = self.get_playables(mana_available)

        if mana_available < self.treasure:
            if self.verbose: print(f"Spent treasures: [{self.treasure}] -> [{self.mana_available}]")
            self.treasure = mana_available
        return played_effects
    
    def take_turn(self):
        if self.verbose: print(f"### Turn {self.turn+1} (Lands: {len(self.lands)}, Mana: {self.get_mana()}[{self.treasure}], Hand: {len(self.hand)})")
        self.draw()
        for card in self.per_turn_effects:
            card.per_turn()
        played_land = self.play_land()
        played_effects = self.play_spells()
        if played_land is not None:
            played_effects.extend(played_land)
        self.turn += 1
        return played_effects
    
    def simulate(self):
        mana_spent_list = []
        mulls_list = []
        lands_played_list = []
        cards_drawn_list = []
        bad_turns_list = []
        mid_turns_list = []
        for j in tqdm(range(self.sims)):
            total_mana_spent = 0
            lands_played = 0
            bad_turns = 0
            mid_turns = 0
            self.mulligans = -1
            self.mulligan()
            for i in range(self.turns):
                mana_spent = 0
                spells_played = 0
                played_effects = self.take_turn()
                for card in played_effects:
                    if not card.ramp:
                        mana_spent += card.mana_spent_when_played
                    if card.land:
                        lands_played += 1
                    if card.spell:
                        spells_played += 1
                if spells_played == 0 and self.deck:
                    bad_turns += 1
                if spells_played < 2 and self.deck and mana_spent < i+1:
                    mid_turns += 1
                total_mana_spent += mana_spent
            mana_spent_list.append(total_mana_spent)
            lands_played_list.append(lands_played)
            mulls_list.append(self.mulligans)
            cards_drawn_list.append(self.draws)
            bad_turns_list.append(bad_turns)
            mid_turns_list.append(mid_turns)
            if self.verbose: 
                print(f"\n### Game {j+1} finished")
                print(f"lands: {len(self.lands)}")
                print(f"surplus mana production: {self.mana_production}")
                print(f"nonpermanent cost reduction: {self.nonpermanent_cost_reduction}")
                print(f"permanent cost reduction: {self.permanent_cost_reduction}")
                print(f"spell cost reduction: {self.spell_cost_reduction}")
                print(f"per turn effects:")
                for card in self.per_turn_effects:
                    print(f"\t{card.name}")
                print(f"cast triggers:")
                for card in self.cast_triggers:
                    print(f"\t{card.name}")

        mean_mana = np.mean(mana_spent_list)
        mean_lands = np.mean(lands_played_list)
        mean_mulls = np.mean(mulls_list)
        mean_draws = np.mean(cards_drawn_list)
        mean_bad_turns = np.mean(bad_turns_list)
        mean_mid_turns = np.mean(mid_turns_list)

        percentile_25 = np.percentile(mana_spent_list, 25)
        percentile_50 = np.percentile(mana_spent_list, 50)
        percentile_75 = np.percentile(mana_spent_list, 75)

        total_mana = np.sum(mana_spent_list)
        quarter_mana = total_mana * 0.25
        sorted_mana = sorted(mana_spent_list)
        cumulative_mana = np.cumsum(sorted_mana)
        bottom_25_index = bisect.bisect_left(cumulative_mana, quarter_mana)
        bottom_25_percent = bottom_25_index / len(mana_spent_list)
        bottom_25_mana = sorted_mana[bottom_25_index]
        # consistency = (1-bottom_25_percent)/0.75

        con_threshold = 0.25
        threshold_index = bisect.bisect_left(cumulative_mana, total_mana * con_threshold)
        threshold_percent = threshold_index / len(mana_spent_list)
        threshold_mana = sorted_mana[threshold_index]
        consistency = (1 - threshold_percent)/(1 - con_threshold)
        # consistency = con_threshold/threshold_percent

        if self.verbose:
            print(f"Average mana spent: {np.mean(mana_spent_list)}")
            print(f"Average lands played: {np.mean(lands_played_list)}")
            print(f"Average mulligans: {np.mean(mulls_list)}")
            print(f"Average cards drawn: {np.mean(cards_drawn_list)}")
            print(f"25th, 50th, 75th percentile mana: {percentile_25}, {percentile_50}, {percentile_75}")
            print(f"Bottom 25% mana: ({bottom_25_percent*100:.2f}%)")
            print(f"Bottom 25% game: {bottom_25_mana}")
        
        return self.land_count, mean_mana, consistency, mean_bad_turns, mean_mid_turns, mean_lands, mean_mulls, mean_draws, percentile_25, percentile_50, percentile_75, threshold_percent, threshold_mana, con_threshold



def main(config):
    pp.pprint(config)
    if config['deck_url'] is not None:
        deck_list = save_archidekt(config)
    deck_list = load_decklist(config['deck_name'])
    goldfisher = Goldfisher(deck_list, **config)
    min_lands = config['min_lands'] or goldfisher.land_count
    max_lands = (config['max_lands'] or goldfisher.land_count) + 1
    outcomes = []
    for i in range(min_lands, max_lands):
        goldfisher.set_lands(i, cuts=config['cuts'])
        outcome = goldfisher.simulate()
        outcomes.append(outcome[:-1])
    # get land count at max consistency and at max mana ev
    outcomes_arr = np.array(outcomes)
    max_mana = outcomes_arr[:,0][np.argmax(outcomes_arr[:,1])]
    max_consistency = outcomes_arr[:,0][np.argmax(outcomes_arr[:,2])]
    min_bad_turns = outcomes_arr[:,0][np.argmin(outcomes_arr[:,3])]
    min_mid_turns = outcomes_arr[:,0][np.argmin(outcomes_arr[:,4])]

    con_threshold = outcome[-1]*100
    print(f"\n-----------------------------------")
    print(f"{config['deck_name']} ({config['turns']} turns, {config['sims']} sims, {min_lands}-{max_lands-1} lands) - max mana @ {max_mana}, max consistency @ {max_consistency}, min bad turns @ {min_bad_turns}, min mid turns @ {min_mid_turns}")
    print(f"-----------------------------------")
    print(tabulate(outcomes, headers=["Land Ct", "Mana (EV)", "Consistency", "Bad Turns", "Mid Turns", "Lands", "Mulls", "Draws", "25th", "50th", "75th", f"{con_threshold}th% Frac", f"{con_threshold}th% Game"]))
    


if __name__ == "__main__":
    parser = get_parser()
    args = parser.parse_args()
    config = vars(args)
    main(config)
    print("done")