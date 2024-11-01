import argparse
import pprint
import random
import statistics
from collections import Counter
from typing import List, Dict
import json
import sys
import os
from dataclasses import dataclass

from deck_loader import Card, load_deck, validate_deck_size

pp = pprint.PrettyPrinter(indent=4)

class GameState:
    def __init__(self, deck: List[Card], mana_threshold: int):
        self.deck = deck.copy()
        self.hand: List[Card] = []
        self.played: List[Card] = []
        self.lands_played = 0
        self.available_mana = 0
        self.turn = 0
        self.mana_spent_total = 0
        self.mana_spent_ramp = 0
        self.mana_spent_draw = 0
        self.mana_spent_nonramp_nondraw = 0
        self.mana_spent_high_cmc = 0
        self.draw_turn = 0
        self.draw_cast = 0
        self.mana_threshold = mana_threshold
    
    def draw(self, count: int = 1):
        for _ in range(count):
            if self.deck:
                self.hand.append(self.deck.pop(0))
    
    def play_turn(self):
        self.turn += 1
        self.draw()
        self.draw(self.draw_turn)
        self.lands_played = 0
        
        # Play land if possible
        lands = [c for c in self.hand if c.is_land]
        if lands and self.lands_played == 0:
            self.play_land(lands[0])
            
        # Calculate available mana
        self.available_mana = len([c for c in self.played if c.is_land])
        
        # If we're above the mana threshold, change play priority
        if self.available_mana >= self.mana_threshold:
            self.play_high_cmc_priority()
        else:
            self.play_ramp_priority()
    
    def play_high_cmc_priority(self):
        # First try to play highest CMC spells
        while True:
            playable = [c for c in self.hand 
                       if not c.is_land and c.cmc <= self.available_mana]
            if not playable:
                break
            playable.sort(key=lambda x: x.cmc, reverse=True)
            self.play_spell(playable[0])
        
        # Then try utility spells if we couldn't play big stuff
        self.play_utility_spells()
    
    def play_ramp_priority(self):
        # Original priority order: land ramp -> mana rocks -> draw -> high CMC
        # Land ramp first
        while True:
            ramp_cards = [c for c in self.hand 
                         if c.is_ramp and c.ramp_type == "land" 
                         and c.cmc <= self.available_mana]
            if not ramp_cards:
                break
            ramp_cards.sort(key=lambda x: (x.ramp_amount / max(x.cmc, 1)), reverse=True)
            self.play_spell(ramp_cards[0])
        
        # Then other utility spells
        self.play_utility_spells()
        
        # Finally, highest CMC possible
        playable = [c for c in self.hand 
                   if not c.is_land and not c.is_ramp and not c.is_draw 
                   and c.cmc <= self.available_mana]
        if playable:
            playable.sort(key=lambda x: x.cmc, reverse=True)
            self.play_spell(playable[0])
    
    def play_utility_spells(self):
        # Mana rocks
        while True:
            rocks = [c for c in self.hand 
                    if c.is_ramp and c.ramp_type == "rock" 
                    and c.cmc <= self.available_mana]
            if not rocks:
                break
            rocks.sort(key=lambda x: (x.ramp_amount / max(x.cmc, 1)), reverse=True)
            self.play_spell(rocks[0])
        
        # Card draw
        while True:
            draw_spells = [c for c in self.hand 
                          if c.is_draw and c.cmc <= self.available_mana]
            if not draw_spells:
                break
            draw_priority = {"immediate": 3, "turn": 2, "cast": 1}
            draw_spells.sort(
                key=lambda x: (draw_priority[x.draw_type], x.draw_amount / max(x.cmc, 1)),
                reverse=True
            )
            self.play_spell(draw_spells[0])
    
    def play_spell(self, card: Card):
        self.hand.remove(card)
        self.played.append(card)
        self.available_mana -= card.cmc
        self.mana_spent_total += card.cmc
        
        if card.is_ramp:
            self.mana_spent_ramp += card.cmc
            if card.ramp_type == "land":
                # Add lands from deck to battlefield (but they can't tap this turn)
                for _ in range(card.ramp_amount):
                    land = next((card for card in self.deck if card.is_land), None)
                    if land:
                        self.deck.remove(land)
                        # Add to played list but don't count for available_mana this turn
                        self.played.append(land)
                        
                # Add lands to hand if it's a Cultivate-style effect
                for _ in range(getattr(card, 'land_to_hand', 0)):
                    land = next((card for card in self.deck if card.is_land), None)
                    if land:
                        self.deck.remove(land)
                        self.hand.append(land)
            else:  # mana rocks
                # Mana rocks can be used immediately, so we increase available_mana
                self.available_mana += card.ramp_amount
        
        # Handle card draw effects
        if card.is_draw:
            if card.draw_type == "immediate":
                self.draw(card.draw_amount)
            elif card.draw_type == "turn":
                self.draw_turn += card.draw_amount
            elif card.draw_type == "cast":
                self.draw_cast += card.draw_amount
            self.mana_spent_draw += card.cmc

        if not card.is_ramp and not card.is_draw:
            self.mana_spent_nonramp_nondraw += card.cmc

        if card.cmc > 6:
            self.mana_spent_high_cmc += card.cmc
        
        # Handle any cast triggers from other permanents
        self.draw(self.draw_cast)
    
    def play_land(self, land: Card):
        self.hand.remove(land)
        self.played.append(land)
        self.lands_played += 1

def get_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--deck_file",
        type=str, 
        default="deck.json",
        help="JSON file containing deck information"
    )
    parser.add_argument(
        "--simulations",
        type=int,
        default=1000,
        help="Number of simulations to run"
    )
    parser.add_argument(
        "--turns",
        type=int,
        default=10,
        help="Number of turns to simulate for each game"
    )
    parser.add_argument(
        "--mana_threshold",
        type=int,
        default=999,  # Default high value means it won't trigger unless specified
        help="Amount of mana at which to prioritize high CMC spells over ramp/draw"
    )
    parser.add_argument(
        "--verbose",
        type=bool,
        default=False,
        help="Print detailed statistics"
    )
    return parser

def simulate_game(deck: List[Card], turns: int, mana_threshold: int) -> Dict:
    random.shuffle(deck)
    game = GameState(deck, mana_threshold)
    game.draw(7)  # Initial hand
    
    turn_stats = []
    for turn in range(turns):
        game.play_turn()
        turn_stats.append({
            'turn': turn + 1,
            'available_mana': game.available_mana,
            'cards_played': len(game.played),
            'cards_in_hand': len(game.hand)
        })
    
    return {
        'turn_stats': turn_stats,
        'cards_played': [c.name for c in game.played],
        'mana_spent_total': game.mana_spent_total,
        'mana_spent_ramp': game.mana_spent_ramp,
        'mana_spent_draw': game.mana_spent_draw,  # Calculate draw mana spent
        'nonramp_nondraw_mana_spent': game.mana_spent_nonramp_nondraw,  # Update this line
        'mana_spent_high_cmc': game.mana_spent_high_cmc  # High CMC spells
    }

def calculate_statistics(values: List[float]) -> Dict:
    if not values:
        return {
            'average': 0,
            'median': 0,
            'mode': 0,
            'maximum': 0,
            'minimum': 0
        }
    
    # Calculate mode (might have multiple values)
    counter = Counter(values)
    max_count = max(counter.values())
    modes = [k for k, v in counter.items() if v == max_count]
    
    return {
        'average': statistics.mean(values),
        'median': statistics.median(values),
        'mode': modes[0] if len(modes) == 1 else modes,
        'maximum': max(values),
        'minimum': min(values)
    }

def plot_distribution(values: List[float], title: str, width: int = 60, height: int = 8) -> str:
    """Create an ASCII bar chart of the distribution of values."""
    if not values:
        return "No data to plot"
    
    # Create bins for the histogram
    min_val = min(values)
    max_val = max(values)
    num_bins = min(20, max_val - min_val + 1)  # Max 20 bins
    bin_size = (max_val - min_val) / num_bins
    bins = [0] * num_bins
    
    # Fill the bins
    for val in values:
        bin_idx = min(int((val - min_val) / bin_size), num_bins - 1)
        bins[bin_idx] += 1
    
    # Find the maximum bin count for scaling
    max_count = max(bins)
    
    # Create the plot
    plot = []
    
    # Add title
    plot.append(title)
    
    # Add y-axis max value
    plot.append(f"Count: {max_count}")
    
    # Add the bars
    for i in range(height - 1, -1, -1):
        row = []
        scale = (i + 1) / height
        for count in bins:
            if count / max_count > scale:
                row.append('█')
            else:
                row.append(' ')
        plot.append(f"|{''.join(row)}|")
    
    # Add the x-axis
    plot.append(f"+{'-' * num_bins}+")
    
    # Add labels
    labels = f"Mana: {min_val:.0f}{' ' * (num_bins-10)}{max_val:.0f}"
    plot.append(f" {labels}")
    
    return '\n'.join(plot)

def calculate_summary_stats(all_stats: List[Dict]) -> Dict:
    """Calculate summary statistics from all simulation runs."""
    if not all_stats:
        raise ValueError("No simulation data to analyze")
    
    # Extract values from all simulations
    total_mana_spent = [s['mana_spent_total'] for s in all_stats]
    ramp_mana_spent = [s['mana_spent_ramp'] for s in all_stats]
    draw_mana_spent = [s['mana_spent_draw'] for s in all_stats]
    nonramp_nondraw_mana_spent = [s['nonramp_nondraw_mana_spent'] for s in all_stats]
    high_cmc_mana_spent = [s['mana_spent_high_cmc'] for s in all_stats]
    
    # Calculate averages only (for sweep.py compatibility)
    return {
        'total_mana_spent': statistics.mean(total_mana_spent),
        'ramp_mana_spent': statistics.mean(ramp_mana_spent),
        'draw_mana_spent': statistics.mean(draw_mana_spent),
        'nonramp_nondraw_mana_spent': statistics.mean(nonramp_nondraw_mana_spent),
        'high_cmc_mana_spent': statistics.mean(high_cmc_mana_spent)
    }

@dataclass
class Card:
    name: str
    cmc: int
    quantity: int = 1
    flex: bool = False
    is_land: bool = False
    is_ramp: bool = False
    is_value: bool = False
    is_commander: bool = False
    ramp_type: str = ""  # "land" or "rock"
    ramp_amount: int = 0
    land_to_hand: int = 0  # For Cultivate-style effects
    is_draw: bool = False
    draw_type: str = ""  # "immediate", "turn", or "cast"
    draw_amount: int = 0

def load_deck(deck_file: str) -> List[Card]:
    """
    Load a deck from a JSON file and convert it to Card objects.
    
    Example JSON format:
    [
        {
            "name": "Forest",
            "cmc": 0,
            "quantity": 37,
            "is_land": true
        },
        {
            "name": "Cultivate",
            "cmc": 3,
            "is_ramp": true,
            "ramp_type": "land",
            "ramp_amount": 1,
            "land_to_hand": 1
        }
    ]
    """
    try:
        with open(deck_file, 'r') as f:
            deck_data = json.load(f)
        
        deck = []
        for card_data in deck_data:
            # Get quantity and remove it from the data if present
            quantity = card_data.pop('quantity', 1)
            
            # Create Card object
            card = Card(**card_data)
            
            # Add the specified number of copies
            deck.extend([card for _ in range(quantity)])
        
        return deck
    
    except FileNotFoundError:
        raise FileNotFoundError(f"Deck file not found: {deck_file}")
    except json.JSONDecodeError:
        raise ValueError(f"Invalid JSON format in deck file: {deck_file}")
    except TypeError as e:
        raise TypeError(f"Invalid card data format: {str(e)}")

def validate_deck_size(deck: List[Card], expected_size: int = 100):
    """Validates that the deck contains the expected number of cards."""
    if len(deck) != expected_size:
        raise ValueError(f"Deck contains {len(deck)} cards. Expected {expected_size} cards.")

def main(config):
    try:
        # Load and validate deck
        if not os.path.exists(config['deck_file']):
            raise FileNotFoundError(f"Deck file not found: {config['deck_file']}")
            
        deck = load_deck(config['deck_file'])
        validate_deck_size(deck, expected_size=100)
        
        # Validate deck contents
        if not any(card.is_land for card in deck):
            raise ValueError("Deck contains no lands")
            
        all_stats = []
        for i in range(config['simulations']):
            stats = simulate_game(
                deck, 
                config['turns'], 
                config['mana_threshold']
            )
            all_stats.append(stats)
            
            if config['verbose'] and (i + 1) % 100 == 0:
                print(f"Completed {i + 1} simulations...", file=sys.stderr)
        
        # Calculate statistics and output JSON
        stats_summary = calculate_summary_stats(all_stats)
        print(json.dumps(stats_summary))
        return True
        
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        return False
    

if __name__ == "__main__":
    parser = get_parser()
    args = parser.parse_args()
    config = vars(args)
    main(config)
    print("\nSimulation complete!")