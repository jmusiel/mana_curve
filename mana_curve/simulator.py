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

pp = pprint.PrettyPrinter(indent=4)

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
    played_on_turn: int = None  # Add this field

class GameState:
    def __init__(self, deck: List[Card], mana_threshold: int, force_commander: bool):
        self.deck = deck.copy()
        self.hand: List[Card] = []
        self.commander = next((card for card in deck if card.is_commander), None)
        if self.commander:
            self.deck.remove(self.commander)
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
        self.force_commander = force_commander
        self.commander_cast_turn = None
        self.cards_drawn: List[Card] = []  # Track all cards drawn this game
    
    def draw(self, count: int = 1):
        for _ in range(count):
            if self.deck:
                card = self.deck.pop(0)
                self.hand.append(card)
                self.cards_drawn.append(card)  # Track drawn cards
    
    def play_turn(self):
        self.turn += 1
        self.draw()
        self.draw(self.draw_turn)
        self.lands_played = 0
        
        # Calculate available mana from lands and rocks
        self.available_mana = len([card for card in self.played if card.is_land]) + \
                             sum(card.ramp_amount for card in self.played if card.is_ramp and card.ramp_type == "rock")
        
        # Play land if possible
        lands = [c for c in self.hand if c.is_land]
        if lands and self.lands_played == 0:
            self.play_land(lands[0])
        
        # If commander priority is enabled and we can cast it
        if self.force_commander and self.commander and self.commander in self.hand:
            if self.commander.cmc <= self.available_mana:
                self.play_spell(self.commander)  
            
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
        card.played_on_turn = self.turn
        self.played.append(card)
        self.available_mana -= card.cmc
        self.mana_spent_total += card.cmc
        
        # Track when commander is cast
        if card.is_commander and self.commander_cast_turn is None:
            self.commander_cast_turn = self.turn
        
        if card.is_ramp:
            self.mana_spent_ramp += card.cmc
            if card.ramp_type == "land":
                # Add lands from deck to battlefield (but they can't tap this turn)
                for _ in range(card.ramp_amount):
                    land = next((card for card in self.deck if card.is_land), None)
                    if land:
                        self.deck.remove(land)
                        land.played_on_turn = self.turn
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
        land.played_on_turn = self.turn
        self.played.append(land)
        self.lands_played += 1
        self.available_mana += 1

    def check_opening_hand(self) -> bool:
        land_count = len([c for c in self.hand if c.is_land])
        cheap_spells = any(c for c in self.hand if not c.is_land and c.cmc <= 3)
        return 3 <= land_count <= 5 and cheap_spells

    def mulligan(self):
        attempts = 0
        while attempts < 2:
            # Shuffle current hand back
            self.deck.extend(self.hand)
            self.hand.clear()
            random.shuffle(self.deck)
            self.draw(7)
            
            if self.check_opening_hand():
                break
            attempts += 1

        # Final mulligan - must put highest CMC card back
        if attempts == 2:
            non_lands = [c for c in self.hand if not c.is_land]
            if non_lands:
                highest_cmc = max(non_lands, key=lambda x: x.cmc)
                self.hand.remove(highest_cmc)
                self.deck.append(highest_cmc)
                random.shuffle(self.deck)

        # Always add commander to hand after mulligan
        if self.commander:
            self.hand.append(self.commander)

def get_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--deck_file",
        type=str, 
        default="kess/top_decklists/deck_1_score_65.json",
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
        action='store_true',
        help="Print detailed statistics"
    )
    parser.set_defaults(verbose=False)
    parser.add_argument(
        "--force_commander",
        action='store_true',
        help="Prioritize casting commander when mana is available"
    )
    parser.set_defaults(force_commander=False)
    return parser

def simulate_game(deck: List[Card], turns: int, mana_threshold: int, force_commander: bool) -> Dict:
    random.shuffle(deck)
    game = GameState(deck, mana_threshold, force_commander)
    game.draw(7)  # Initial hand
    game.mulligan()  # Handle mulligan decisions
    
    turn_stats = []
    for turn in range(turns):
        game.play_turn()
        turn_stats.append({
            'turn': turn + 1,
            'land_mana': len([card for card in game.played if card.is_land]),
            'rock_mana': sum(card.ramp_amount for card in game.played if card.is_ramp and card.ramp_type == "rock"),
            'available_mana': game.available_mana,
            'cards_played': len(game.played),
            'cards_in_hand': len(game.hand),
            'plays': [(card.name, card.played_on_turn) for card in game.played if card.played_on_turn == turn + 1]
        })
    
    return {
        'turn_stats': turn_stats,
        'cards_played': [(card.name, card.played_on_turn) for card in game.played],
        'cards_drawn': [card.name for card in game.cards_drawn],  # Add drawn cards
        'mana_spent_total': game.mana_spent_total,
        'mana_spent_ramp': game.mana_spent_ramp,
        'mana_spent_draw': game.mana_spent_draw,
        'nonramp_nondraw_mana_spent': game.mana_spent_nonramp_nondraw,
        'mana_spent_high_cmc': game.mana_spent_high_cmc,
        'commander_cast_turn': game.commander_cast_turn
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
    avg_commander_turn = statistics.mean([s['commander_cast_turn'] for s in all_stats if s['commander_cast_turn'] is not None]) if [s['commander_cast_turn'] for s in all_stats if s['commander_cast_turn'] is not None] else None
    commander_cast_rate = len([s['commander_cast_turn'] for s in all_stats if s['commander_cast_turn'] is not None]) / len(all_stats) if all_stats else 0
    
    return {
        'total_mana_spent': statistics.mean(total_mana_spent),
        'ramp_mana_spent': statistics.mean(ramp_mana_spent),
        'draw_mana_spent': statistics.mean(draw_mana_spent),
        'nonramp_nondraw_mana_spent': statistics.mean(nonramp_nondraw_mana_spent),
        'high_cmc_mana_spent': statistics.mean(high_cmc_mana_spent),
        'avg_commander_cast_turn': avg_commander_turn,
        'commander_cast_rate': commander_cast_rate  # Percentage of games where commander was cast
    }

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

        if "decklist" in deck_data:
            deck_data = deck_data["decklist"]
        
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

def analyze_card_correlations(all_stats: List[Dict], deck: List[Card]) -> Dict:
    """Analyze which cards correlate with top and bottom performance."""
    # Sort stats by total mana spent
    sorted_stats = sorted(all_stats, key=lambda x: x['mana_spent_total'], reverse=True)
    
    # Get top and bottom 10%
    num_games = len(sorted_stats)
    top_10_percent = sorted_stats[:num_games//10]
    bottom_10_percent = sorted_stats[-num_games//10:]
    
    # Initialize counters for each unique card
    unique_cards = {card.name for card in deck if not card.is_commander}
    card_stats = {name: {
        'top_10_drawn': 0,
        'top_10_played': 0,
        'bottom_10_drawn': 0,
        'bottom_10_played': 0,
        'total_games_drawn': 0,
        'total_games_played': 0
    } for name in unique_cards}
    
    # Count occurrences in all games
    for stat in all_stats:
        drawn_cards = set(stat['cards_drawn'])
        played_cards = {card for card, _ in stat['cards_played']}
        
        for card_name in unique_cards:
            if card_name in drawn_cards:
                card_stats[card_name]['total_games_drawn'] += 1
            if card_name in played_cards:
                card_stats[card_name]['total_games_played'] += 1
    
    # Count occurrences in top 10%
    for stat in top_10_percent:
        drawn_cards = set(stat['cards_drawn'])
        played_cards = {card for card, _ in stat['cards_played']}
        
        for card_name in unique_cards:
            if card_name in drawn_cards:
                card_stats[card_name]['top_10_drawn'] += 1
            if card_name in played_cards:
                card_stats[card_name]['top_10_played'] += 1
    
    # Count occurrences in bottom 10%
    for stat in bottom_10_percent:
        drawn_cards = set(stat['cards_drawn'])
        played_cards = {card for card, _ in stat['cards_played']}
        
        for card_name in unique_cards:
            if card_name in drawn_cards:
                card_stats[card_name]['bottom_10_drawn'] += 1
            if card_name in played_cards:
                card_stats[card_name]['bottom_10_played'] += 1
    
    # Calculate correlations
    for card_name in unique_cards:
        stats = card_stats[card_name]
        total_top = len(top_10_percent)
        total_bottom = len(bottom_10_percent)
        
        # Calculate percentages when drawn
        if stats['total_games_drawn'] > 0:
            stats['top_10_drawn_pct'] = (stats['top_10_drawn'] / total_top) * 100
            stats['bottom_10_drawn_pct'] = (stats['bottom_10_drawn'] / total_bottom) * 100
            stats['draw_correlation'] = stats['top_10_drawn_pct'] - stats['bottom_10_drawn_pct']
        else:
            stats['top_10_drawn_pct'] = None
            stats['bottom_10_drawn_pct'] = None
            stats['draw_correlation'] = None
        
        # Calculate percentages when played
        if stats['total_games_played'] > 0:
            stats['top_10_played_pct'] = (stats['top_10_played'] / total_top) * 100
            stats['bottom_10_played_pct'] = (stats['bottom_10_played'] / total_bottom) * 100
            stats['play_correlation'] = stats['top_10_played_pct'] - stats['bottom_10_played_pct']
        else:
            stats['top_10_played_pct'] = None
            stats['bottom_10_played_pct'] = None
            stats['play_correlation'] = None
    
    return card_stats

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
                config['mana_threshold'],
                config['force_commander']
            )
            all_stats.append(stats)
            
            if config['verbose'] and (i + 1) % 100 == 0:
                print(f"\nCompleted {i + 1} simulations...", file=sys.stderr)
                print("\nExample game sequence:", file=sys.stderr)
                for turn_stat in stats['turn_stats']:
                    turn_num = turn_stat['turn']
                    plays = turn_stat['plays']
                    
                    print(f"\nTurn {turn_num}:", file=sys.stderr)
                    print(f"  Available Mana: {turn_stat['available_mana']}", file=sys.stderr)
                    print(f"  Land Mana: {turn_stat['land_mana']}", file=sys.stderr)
                    print(f"  Rock Mana: {turn_stat['rock_mana']}", file=sys.stderr)
                    print(f"  Cards in Hand: {turn_stat['cards_in_hand']}", file=sys.stderr)
                    
                    if plays:
                        print("  Played:", file=sys.stderr)
                        for card_name, _ in plays:
                            print(f"    - {card_name}", file=sys.stderr)
        
        # Calculate card correlations
        card_correlations = analyze_card_correlations(all_stats, deck)
        
        # Sort and print top correlations
        if config['verbose']:
            print("\nCard Correlation Analysis:", file=sys.stderr)
            
            # Sort by draw correlation
            draw_correlations = sorted(
                [(name, stats['draw_correlation']) for name, stats in card_correlations.items()],
                key=lambda x: x[1],
                reverse=True
            )
            
            print("\nTop 10 Cards by Draw Impact:", file=sys.stderr)
            for card, correlation in draw_correlations[:10]:
                print(f"  {card}: {correlation:+.1f}%", file=sys.stderr)
                
            print("\nBottom 10 Cards by Draw Impact:", file=sys.stderr)
            for card, correlation in draw_correlations[-10:]:
                print(f"  {card}: {correlation:+.1f}%", file=sys.stderr)
            
            # Sort by play correlation
            play_correlations = sorted(
                [(name, stats['play_correlation']) for name, stats in card_correlations.items()],
                key=lambda x: x[1],
                reverse=True
            )
            
            print("\nTop 10 Cards by Play Impact:", file=sys.stderr)
            for card, correlation in play_correlations[:10]:
                print(f"  {card}: {correlation:+.1f}%", file=sys.stderr)
                
            print("\nBottom 10 Cards by Play Impact:", file=sys.stderr)
            for card, correlation in play_correlations[-10:]:
                print(f"  {card}: {correlation:+.1f}%", file=sys.stderr)

        print("\n")
        
        # Calculate statistics and output JSON
        stats_summary = calculate_summary_stats(all_stats)
        print(json.dumps(stats_summary))
        for key, value in stats_summary.items():
            print(f"{key}: {value}")
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