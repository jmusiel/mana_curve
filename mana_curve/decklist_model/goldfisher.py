from mana_curve.decklist_model.decklist import get_decklist, load_decklist
from mana_curve.decklist_model.cards import card_factory
import bisect
import copy
import random
from tqdm import tqdm

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
        "--turns",
        type=int, 
        default=10,
    )
    parser.add_argument(
        "--sims",
        type=int, 
        default=10000,
    )
    return parser

class Goldfisher:
    def __init__(self, decklist_dict, turns, sims):
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

        self.reset()
        
    def reset(self):
        self.turn = 0
        self.draws = 0
        self.command_zone = []
        self.deck = []
        self.yard = []
        self.hand = []
        self.battlefield = []
        self.exile = []
        self.lands = []
        for card in self.commanders:
            card.zone = self.command_zone
            self.command_zone.append(card.index)
        for card in self.decklist:
            card.zone = self.deck
            self.deck.append(card.index)
        random.shuffle(self.deck)

    def draw(self):
        drawn_i = self.deck.pop()
        drawn = self.decklist[drawn_i]
        drawn.zone = self.hand
        self.hand.append(drawn_i)
        self.draws += 1

    def mulligan(self):
        while True:
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

    def get_mana(self):
        return len(self.lands)
    
    def get_playables(self):
        playables = []
        available_mana = self.get_mana()
        for i in self.hand:
            card = self.decklist[i]
            if card.cmc < available_mana and card.spell:
                playables.append(card)
        playables = sorted(playables)
        for card in self.commanders:
            if card.cmc < available_mana and card.spell:
                playables.append(card)
        return playables
    
    def play_land(self):
        played = False
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
            played = True
        return land
    
    def play_spells(self, playables):
        mana_available = self.get_mana()
        played_effects = []
        for card in reversed(playables):
            if card.cmc <= mana_available:
                mana_available -= card.cmc
                if card.spell and card.nonpermanent:
                    card.change_zone(self.yard)
                elif card.spell and card.permanent and not card.nonpermanent:
                    card.change_zone(self.battlefield)
                else:
                    raise ValueError(f"incompatible types {card.types} for card {card.name}")
                played_effects.append(card.when_played())
        return played_effects
    
    def take_turn(self):
        self.draw()
        played_land = self.play_land()
        playables = self.get_playables()
        played_effects = self.play_spells(playables)
        if played_land is not None:
            played_effects.append(played_land)
        self.turn += 1
        return played_effects
    
    def simulate(self):
        mana_spent = 0
        mulls = 0
        lands_played = 0
        cards_drawn = 0
        all_played_effects = []
        for j in tqdm(range(self.sims)):
            self.mulligans = -1
            self.mulligan()
            for i in range(self.turns):
                played_effects = self.take_turn()
                for card in played_effects:
                    mana_spent += card.cmc
                    if card.land:
                        lands_played += 1
                    all_played_effects.append(card)
            mulls += self.mulligans
            cards_drawn += self.draws

        print(f"Average mana spent: {mana_spent/self.sims}")
        print(f"Average lands played: {lands_played/self.sims}")
        print(f"Average mulligans: {mulls/self.sims}")
        print(f"Average cards drawn: {cards_drawn/self.sims}")


def main(config):
    pp.pprint(config)
    deck_list = load_decklist(config['deck_name'])
    goldfisher = Goldfisher(deck_list, config['turns'], config['sims'])
    goldfisher.simulate()


if __name__ == "__main__":
    parser = get_parser()
    args = parser.parse_args()
    config = vars(args)
    main(config)
    print("done")