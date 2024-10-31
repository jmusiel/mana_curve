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

def generate_parameter_combinations(num_samples):
    # Define parameter ranges to test
    params = {
        'lands': range(28, 43, 1),         # 34-42 lands
        'mana_rocks': range(0, 4, 1),      # 2-8 mana rocks
        'land_ramp': range(2, 20, 2),       # 2-8 land ramp
        'immediate_draw': range(0, 15, 2),   # 2-6 immediate draw
        'per_turn_draw': range(0, 4, 1),    # 2-6 per turn draw
        'on_cast_draw': range(0, 4, 1),     # 2-6 on cast draw
        'curve': [2.5, 3.0, 3.5]      # Average mana value
    }
    
    # Generate random combinations
    combinations = []
    for _ in range(num_samples):
        sample = {
            key: random.choice(list(value)) 
            for key, value in params.items()
        }
        combinations.append(sample)
    
    return combinations

def calculate_deck_stats(deck_file: str) -> dict:
    """Calculate statistics about the deck's mana curve."""
    with open(deck_file, 'r') as f:
        deck = json.load(f)
    
    # Count cards at each CMC (excluding lands)
    cmc_counts = {}
    nonland_cmcs = []
    
    for card in deck:
        # Handle cards with quantity field (like basic lands)
        quantity = card.get('quantity', 1)
        for _ in range(quantity):
            if not card.get('is_land', False):
                cmc = card['cmc']
                cmc_counts[cmc] = cmc_counts.get(cmc, 0) + 1
                nonland_cmcs.append(cmc)
    
    # Calculate actual curve center
    actual_curve = statistics.mean(nonland_cmcs) if nonland_cmcs else 0
    
    # Create stats dictionary
    stats = {
        'actual_curve': actual_curve,
    }
    
    # Add counts for each CMC (0-8+)
    for cmc in range(9):
        if cmc < 8:
            stats[f'cmc_{cmc}'] = cmc_counts.get(cmc, 0)
        else:
            # Combine all cards with CMC 8 or greater
            stats[f'cmc_8plus'] = sum(count for c, count in cmc_counts.items() if c >= 8)
    
    return stats

def run_simulation(params, num_simulations):
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Create a unique temp file name using process ID and timestamp
    pid = os.getpid()
    timestamp = int(time.time() * 1000)
    temp_deck_file = os.path.join(current_dir, f'temp_deck_{pid}_{timestamp}.json')
    
    try:
        # Clean up any existing temp file
        if os.path.exists(temp_deck_file):
            os.remove(temp_deck_file)
        
        # Generate deck with parameters
        gen_cmd = [
            'python',
            os.path.join(current_dir, 'deck_generator.py'),
            '--lands', str(params['lands']),
            '--mana-rocks', str(params['mana_rocks']),
            '--land-ramp', str(params['land_ramp']),
            '--immediate-draw', str(params['immediate_draw']),
            '--per-turn-draw', str(params['per_turn_draw']),
            '--on-cast-draw', str(params['on_cast_draw']),
            '--curve', str(params['curve']),
            '--output', temp_deck_file
        ]
        
        result = subprocess.run(gen_cmd, capture_output=True, text=True)
        
        # Fail fast if deck generation fails
        if result.returncode != 0:
            raise RuntimeError(f"Deck generation failed:\n{result.stderr}")
            
        if not os.path.exists(temp_deck_file):
            raise RuntimeError("Deck file was not created")
            
        # Run simulator
        sim_cmd = [
            'python',
            os.path.join(current_dir, 'simulator.py'),
            '--deck', temp_deck_file,
            '--turns', '14',
            '--simulations', str(num_simulations),
            '--verbose', 'false'
        ]
        
        sim_result = subprocess.run(sim_cmd, capture_output=True, text=True)
        
        # Fail fast if simulation fails
        if sim_result.returncode != 0:
            raise RuntimeError(f"Simulation failed:\n{sim_result.stderr}")
        
        # Parse simulation results (only first line should be JSON)
        try:
            json_line = sim_result.stdout.strip().split('\n')[0]
            simulation_results = json.loads(json_line)
        except (IndexError, json.JSONDecodeError) as e:
            raise RuntimeError(f"Failed to parse simulation results: {str(e)}")
        
        # Calculate deck statistics
        deck_stats = calculate_deck_stats(temp_deck_file)
        
        return {
            **params,
            'actual_curve': deck_stats['actual_curve'],
            'total_mana_spent': simulation_results['total_mana_spent'],
            'ramp_mana_spent': simulation_results['ramp_mana_spent'],
            'nonramp_mana_spent': simulation_results['nonramp_mana_spent'],
            **{f'cmc_{i}': deck_stats[f'cmc_{i}'] for i in range(8)},
            'cmc_8plus': deck_stats['cmc_8plus']
        }
        
    except Exception as e:
        raise RuntimeError(f"Failed to process params {params}: {str(e)}")
        
    finally:
        # Clean up temp file
        try:
            if os.path.exists(temp_deck_file):
                os.remove(temp_deck_file)
        except Exception as e:
            print(f"Warning: Failed to clean up temp file {temp_deck_file}: {str(e)}", file=sys.stderr)

def main():
    # Add command line argument parsing
    parser = argparse.ArgumentParser(description='Run deck simulations with random parameter combinations')
    parser.add_argument('--samples', type=int, default=1000,
                       help='Number of random parameter combinations to test')
    parser.add_argument('--simulations', type=int, default=1000,
                       help='Number of simulations to run for each parameter combination')
    parser.add_argument('--processes', type=int, default=None,
                       help='Number of parallel processes to use (default: CPU count)')
    parser.add_argument('--sequential', action='store_true',
                       help='Run simulations sequentially (disables parallelism)')
    args = parser.parse_args()
    
    # Generate random parameter combinations
    combinations = generate_parameter_combinations(args.samples)
    
    if args.sequential:
        # Sequential processing
        print(f"Testing {len(combinations)} random parameter combinations sequentially...")
        results = []
        for combo in tqdm(combinations):
            result = run_simulation(combo, args.simulations)
            if result is not None:
                results.append(result)
    else:
        # Parallel processing
        num_processes = args.processes if args.processes else cpu_count()
        print(f"Testing {len(combinations)} random parameter combinations using {num_processes} processes...")
        
        # Run simulations in parallel
        with Pool(processes=num_processes) as pool:
            # Use partial to include simulations parameter
            from functools import partial
            run_sim_with_count = partial(run_simulation, num_simulations=args.simulations)
            
            # Use tqdm to show progress bar
            results = list(tqdm(
                pool.imap(run_sim_with_count, combinations),
                total=len(combinations)
            ))
        # Filter out None results
        results = [r for r in results if r is not None]
    
    if not results:
        print("No valid simulation results obtained!")
        return
    
    # Convert to DataFrame for analysis
    df = pd.DataFrame(results)
    
    # Sort by total mana spent
    df_sorted = df.sort_values('total_mana_spent', ascending=False)
    
    # Calculate average CMC distribution for the top 10 decks
    top_10 = df_sorted.head(10)
    avg_cmc_top_10 = {f'cmc_{i}': top_10[f'cmc_{i}'].mean() for i in range(8)}
    avg_cmc_top_10['cmc_8plus'] = top_10['cmc_8plus'].mean()
    
    # Calculate average CMC distribution for the remaining decks
    remaining_decks = df_sorted.iloc[10:]
    avg_cmc_remaining = {f'cmc_{i}': remaining_decks[f'cmc_{i}'].mean() for i in range(8)}
    avg_cmc_remaining['cmc_8plus'] = remaining_decks['cmc_8plus'].mean()
    
    # Set pandas display options to show all columns
    pd.set_option('display.max_columns', None)  # Show all columns
    pd.set_option('display.width', None)        # Don't wrap wide tables
    pd.set_option('display.max_rows', 10)       # Limit to 10 rows by default
    
    # Save results
    df_sorted.to_csv('simulation_results.csv', index=False)
    
    # Print top 10 configurations (first table with specified columns)
    print("\nTop 10 Configurations (Selected Columns):")
    selected_columns = [
        'lands', 'mana_rocks', 'land_ramp', 'immediate_draw', 
        'per_turn_draw', 'on_cast_draw', 'curve', 
        'actual_curve', 'total_mana_spent', 
        'ramp_mana_spent', 'nonramp_mana_spent'
    ]
    print(top_10[selected_columns])
    
    # Print average CMC distribution in a separate table (second table)
    print("\nAverage CMC Distribution (Top 10 vs Remaining):")
    cmc_distribution = pd.DataFrame({
        'CMC': [f'CMC {i}' for i in range(8)] + ['CMC 8+'],
        'Top 10 Average': [avg_cmc_top_10[f'cmc_{i}'] for i in range(8)] + [avg_cmc_top_10['cmc_8plus']],
        'Remaining Average': [avg_cmc_remaining[f'cmc_{i}'] for i in range(8)] + [avg_cmc_remaining['cmc_8plus']]
    })
    print(cmc_distribution)

if __name__ == "__main__":
    main()