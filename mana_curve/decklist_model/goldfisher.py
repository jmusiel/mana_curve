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
        default=1,
    )
    parser.add_argument(
        "--verbose",
        action="store_false",
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

        self.reset()
        
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

    def draw(self):
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


        print(f"Average mana spent: {mana_spent/self.sims}")
        print(f"Average lands played: {lands_played/self.sims}")
        print(f"Average mulligans: {mulls/self.sims}")
        print(f"Average cards drawn: {cards_drawn/self.sims}")


def main(config):
    pp.pprint(config)
    if config['deck_url'] is not None:
        deck_list = get_decklist(config)
    deck_list = load_decklist(config['deck_name'])
    goldfisher = Goldfisher(deck_list, **config)
    goldfisher.simulate()


if __name__ == "__main__":
    parser = get_parser()
    args = parser.parse_args()
    config = vars(args)
    main(config)
    print("done")