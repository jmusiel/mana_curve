import subprocess
import json
import itertools
import pandas as pd
from tqdm import tqdm
import numpy as np
import os
import random
import argparse
from multiprocessing import Pool, cpu_count
import statistics
import time
import sys
from collections import Counter

def load_template(template_path: str) -> tuple[list, list]:
    """Load and separate fixed and flex cards from template."""
    with open(template_path, 'r') as f:
        template = json.load(f)
    
    fixed_cards = [card for card in template if not card.get('flex', False)]
    flex_cards = [card for card in template if card.get('flex', False)]
    
    return fixed_cards, flex_cards

def generate_deck_combinations(fixed_cards: list, flex_cards: list, num_samples: int) -> list:
    """Generate random deck combinations using fixed cards and sampling from flex cards."""
    target_deck_size = 100  # Commander deck size
    fixed_count = sum(card.get('quantity', 1) for card in fixed_cards)
    flex_slots = target_deck_size - fixed_count
    
    combinations = []
    for _ in range(num_samples):
        # Randomly sample from flex cards until we hit the target deck size
        selected_flex = []
        current_count = 0
        available_flex = flex_cards.copy()

        multi_cards = [card for card in available_flex if card.get('quantity', 1) > 1]
        for card in multi_cards:
            available_flex.remove(card)
            card_copy = card.copy()
            card_copy['quantity'] = 1
            num_to_add = np.random.randint(0, card.get('quantity', 1)+1)
            for _ in range(num_to_add):
                selected_flex.append(card_copy)
                current_count += 1
        
        while current_count < flex_slots and available_flex:
            card = random.choice(available_flex)
            available_flex.remove(card)  # Remove to avoid duplicates
            selected_flex.append(card)
            current_count += card.get('quantity', 1)
        
        combinations.append(selected_flex)
    
    return combinations

def categorize_deck(deck: list) -> dict:
    """Analyze deck composition by card types."""
    stats = {
        'lands': sum(1 for card in deck if card['is_land']),
        'ramp': sum(1 for card in deck if card['is_ramp']),
        'rock_ramp': sum(1 for card in deck if card.get('is_ramp') and card.get('ramp_type') == 'rock'),
        'land_ramp': sum(1 for card in deck if card.get('is_ramp') and card.get('ramp_type') == 'land'),
        'ramp_1': sum(1 for card in deck if card.get('is_ramp') and card.get('ramp_amount') == 1),
        'ramp_2': sum(1 for card in deck if card.get('is_ramp') and card.get('ramp_amount') == 2),
        'ramp_3': sum(1 for card in deck if card.get('is_ramp') and card.get('ramp_amount') == 3),
        'draw': sum(1 for card in deck if card['is_draw']),
        'immediate_draw': sum(1 for card in deck if card.get('is_draw') and card.get('kind') == 'immediate'),
        'turn_draw': sum(1 for card in deck if card.get('is_draw') and card.get('kind') == 'turn'),
        'cast_draw': sum(1 for card in deck if card.get('is_draw') and card.get('kind') == 'cast'),
        'draw_1': sum(1 for card in deck if card.get('is_draw') and card.get('kind') == 'immediate' and card.get('draw_amount') == 1),
        'draw_2': sum(1 for card in deck if card.get('is_draw') and card.get('kind') == 'immediate' and card.get('draw_amount') == 2),
        'draw_3': sum(1 for card in deck if card.get('is_draw') and card.get('kind') == 'immediate' and card.get('draw_amount') == 3),
        'value': sum(1 for card in deck if card['is_value']),
        'value_cmc': statistics.mean([card['cmc'] for card in deck if card['is_value']]),
        'curve': statistics.mean([card['cmc'] for card in deck if not card['is_land']]),
        'cmc_1': sum(1 for card in deck if card['cmc'] == 1),
        'cmc_2': sum(1 for card in deck if card['cmc'] == 2),
        'cmc_3': sum(1 for card in deck if card['cmc'] == 3),
        'cmc_4': sum(1 for card in deck if card['cmc'] == 4),
        'cmc_5': sum(1 for card in deck if card['cmc'] == 5),
        'cmc_6': sum(1 for card in deck if card['cmc'] == 6),
        'cmc_7+': sum(1 for card in deck if card['cmc'] >= 7),
    }
    return stats

def run_simulation(deck_combo: tuple[list, list], num_simulations: int, mana_threshold: int) -> dict:
    """Run simulation for a given deck combination."""
    fixed_cards, flex_cards = deck_combo
    
    # Create full deck list
    full_deck = fixed_cards + flex_cards
    
    # Create a unique temp file name using process ID and timestamp
    pid = os.getpid()
    timestamp = int(time.time() * 1000)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    temp_deck_file = os.path.join(current_dir, f'temp_deck_{pid}_{timestamp}.json')
    
    try:
        # Write deck to temp file
        with open(temp_deck_file, 'w') as f:
            json.dump(full_deck, f)
        
        # Run simulator
        sim_cmd = [
            'python',
            os.path.join(current_dir, 'simulator.py'),
            '--deck', temp_deck_file,
            '--turns', '14',
            '--simulations', str(num_simulations),
            '--mana_threshold', str(mana_threshold),
            '--verbose', 'false'
        ]
        
        sim_result = subprocess.run(sim_cmd, capture_output=True, text=True)
        
        if sim_result.returncode != 0:
            raise RuntimeError(f"Simulation failed:\n{sim_result.stderr}")
        
        # Parse simulation results
        try:
            json_line = sim_result.stdout.strip().split('\n')[0]
            simulation_results = json.loads(json_line)
        except (IndexError, json.JSONDecodeError) as e:
            raise RuntimeError(f"Failed to parse simulation results: {str(e)}")
        
        # Categorize deck
        deck_stats = categorize_deck(full_deck)
        
        return {
            **deck_stats,
            'total_mana_spent': simulation_results['total_mana_spent'],
            'ramp_mana_spent': simulation_results['ramp_mana_spent'],
            'draw_mana_spent': simulation_results['draw_mana_spent'],
            'nonramp_nondraw_mana_spent': simulation_results['nonramp_nondraw_mana_spent'],
            'high_cmc_mana_spent': simulation_results['high_cmc_mana_spent']
        }
        
    except Exception as e:
        print(f"Error in simulation: {str(e)}", file=sys.stderr)
        return None
        
    finally:
        # Clean up temp file
        try:
            if os.path.exists(temp_deck_file):
                os.remove(temp_deck_file)
        except Exception as e:
            print(f"Warning: Failed to clean up temp file {temp_deck_file}: {str(e)}", file=sys.stderr)

def main():
    parser = argparse.ArgumentParser(description='Run deck simulations with template-based combinations')
    parser.add_argument('--template', type=str, required=False,
                       help='Path to template JSON file', default='kozilek_template.json')
    parser.add_argument('--samples', type=int, default=1000,
                       help='Number of random combinations to test')
    parser.add_argument('--simulations', type=int, default=1000,
                       help='Number of simulations to run for each combination')
    parser.add_argument('--mana_threshold', type=int, default=7,
                       help='Threshold at which to prioritize big spells')
    parser.add_argument('--processes', type=int, default=None,
                       help='Number of parallel processes to use (default: CPU count)')
    args = parser.parse_args()
    
    # Load template
    fixed_cards, flex_cards = load_template(args.template)
    print(f"Loaded template with {len(fixed_cards)} fixed cards and {len(flex_cards)} flex cards")
    
    # Generate combinations
    combinations = generate_deck_combinations(fixed_cards, flex_cards, args.samples)
    combinations = [(fixed_cards, flex_combo) for flex_combo in combinations]
    
    # Run simulations in parallel
    num_processes = args.processes if args.processes else cpu_count()
    print(f"Testing {len(combinations)} combinations using {num_processes} processes...")
    
    with Pool(processes=num_processes) as pool:
        from functools import partial
        run_sim_with_params = partial(run_simulation, 
                                    num_simulations=args.simulations,
                                    mana_threshold=args.mana_threshold)
        
        results = list(tqdm(
            pool.imap(run_sim_with_params, combinations),
            total=len(combinations)
        ))
    
    # Filter out None results
    results = [r for r in results if r is not None]
    
    if not results:
        print("No valid simulation results obtained!")
        return
    
    # Convert to DataFrame and sort by total mana spent
    df = pd.DataFrame(results)
    df_sorted = df.sort_values('nonramp_nondraw_mana_spent', ascending=False)
    
    # Save results
    df_sorted.to_csv('template_simulation_results.csv', index=False)
    
    # Print top 10 configurations
    print("\nTop 10 Configurations:")
    print(df_sorted.head(10))
    
    # Calculate and print average stats for top 10% vs bottom 90%
    top_10_percent = df_sorted.head(int(len(df_sorted) * 0.1))
    bottom_90_percent = df_sorted.tail(int(len(df_sorted) * 0.9))
    
    print("\nAverage Stats Comparison (Top 10% vs Bottom 90%):")
    comparison_stats = pd.DataFrame({
        'Metric': ['Lands', 'Ramp', 'Rock Ramp', 'Land Ramp', 'Ramp 1', 'Ramp 2', 'Ramp 3', 'Draw', 'Immediate Draw', 
                   'Turn Draw', 'Cast Draw', 'Draw 1', 'Draw 2', 'Draw 3', 'Value Cards', 'Average Value CMC', 'Average Curve',
                   'Total Mana Spent'],
        'Top 10%': [
            top_10_percent['lands'].mean(),
            top_10_percent['ramp'].mean(),
            top_10_percent['rock_ramp'].mean(),
            top_10_percent['land_ramp'].mean(),
            top_10_percent['ramp_1'].mean(),
            top_10_percent['ramp_2'].mean(),
            top_10_percent['ramp_3'].mean(),
            top_10_percent['draw'].mean(),
            top_10_percent['immediate_draw'].mean(),
            top_10_percent['turn_draw'].mean(),
            top_10_percent['cast_draw'].mean(),
            top_10_percent['draw_1'].mean(),
            top_10_percent['draw_2'].mean(),
            top_10_percent['draw_3'].mean(),
            top_10_percent['value'].mean(),
            top_10_percent['value_cmc'].mean(),
            top_10_percent['curve'].mean(),
            top_10_percent['total_mana_spent'].mean()
        ],
        'Bottom 90%': [
            bottom_90_percent['lands'].mean(),
            bottom_90_percent['ramp'].mean(),
            bottom_90_percent['rock_ramp'].mean(),
            bottom_90_percent['land_ramp'].mean(),
            bottom_90_percent['ramp_1'].mean(),
            bottom_90_percent['ramp_2'].mean(),
            bottom_90_percent['ramp_3'].mean(),
            bottom_90_percent['draw'].mean(),
            bottom_90_percent['immediate_draw'].mean(),
            bottom_90_percent['turn_draw'].mean(),
            bottom_90_percent['cast_draw'].mean(),
            bottom_90_percent['draw_1'].mean(),
            bottom_90_percent['draw_2'].mean(),
            bottom_90_percent['draw_3'].mean(),
            bottom_90_percent['value'].mean(),
            bottom_90_percent['value_cmc'].mean(),
            bottom_90_percent['curve'].mean(),
            bottom_90_percent['total_mana_spent'].mean()
        ]
    })
    
    print(comparison_stats)

if __name__ == "__main__":
    main()
