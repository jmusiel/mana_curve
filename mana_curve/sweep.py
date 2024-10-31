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

def generate_parameter_combinations(num_samples):
    # Define parameter ranges to test
    params = {
        'lands': range(34, 43, 1),         # 34-42 lands
        'mana_rocks': range(0, 4, 1),      # 2-8 mana rocks
        'land_ramp': range(2, 20, 2),       # 2-8 land ramp
        'immediate_draw': range(0, 15, 2),   # 2-6 immediate draw
        'per_turn_draw': range(0, 4, 1),    # 2-6 per turn draw
        'on_cast_draw': range(0, 4, 1),     # 2-6 on cast draw
        'curve': [2.9, 3.0, 3.1]      # Average mana value
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

def run_simulation(params):
    # Get the directory of the current script
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Generate deck with parameters
    cmd = [
        'python',
        os.path.join(current_dir, 'deck_generator.py'),
        '--lands', str(params['lands']),
        '--mana-rocks', str(params['mana_rocks']),
        '--land-ramp', str(params['land_ramp']),
        '--immediate-draw', str(params['immediate_draw']),
        '--per-turn-draw', str(params['per_turn_draw']),
        '--on-cast-draw', str(params['on_cast_draw']),
        '--curve', str(params['curve']),
        '--output', 'temp_deck.json'
    ]
    subprocess.run(cmd, capture_output=True)
    
    # Run simulator
    cmd = [
        'python',
        os.path.join(current_dir, 'simulator.py'),
        '--deck', 'temp_deck.json',
        '--turns', '14',
        '--simulations', '1000',
        '--verbose', 'false'
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    # Parse results (assuming simulator outputs JSON)
    try:
        # Split output by newlines and take first non-empty line
        json_line = next(line for line in result.stdout.split('\n') if line.strip())
        simulation_results = json.loads(json_line)
        
        if not simulation_results:
            print(f"Empty results for params: {params}")
            return None
            
        # Combine parameters with results
        combined_results = {
            'lands': params['lands'],
            'mana_rocks': params['mana_rocks'],
            'land_ramp': params['land_ramp'],
            'immediate_draw': params['immediate_draw'],
            'per_turn_draw': params['per_turn_draw'],
            'on_cast_draw': params['on_cast_draw'],
            'curve': params['curve'],
            'total_mana_spent': simulation_results['total_mana_spent'],
            'ramp_mana_spent': simulation_results['ramp_mana_spent'],
            'nonramp_mana_spent': simulation_results['nonramp_mana_spent']
        }
        return combined_results
        
    except json.JSONDecodeError:
        print(f"Error parsing results for params: {params}")
        print(f"stdout: {result.stdout}")
        print(f"stderr: {result.stderr}")
        return None
    except Exception as e:
        print(f"Unexpected error for params {params}: {e}")
        return None

def main():
    # Add command line argument parsing
    parser = argparse.ArgumentParser(description='Run deck simulations with random parameter combinations')
    parser.add_argument('--samples', type=int, default=500,
                       help='Number of random parameter combinations to test')
    parser.add_argument('--processes', type=int, default=None,
                       help='Number of parallel processes to use (default: CPU count)')
    args = parser.parse_args()
    
    # Set number of processes
    num_processes = args.processes if args.processes else cpu_count()
    
    # Generate random parameter combinations
    combinations = generate_parameter_combinations(args.samples)
    print(f"Testing {len(combinations)} random parameter combinations using {num_processes} processes...")
    
    # Run simulations in parallel
    with Pool(processes=num_processes) as pool:
        # Use tqdm to show progress bar
        results = list(tqdm(
            pool.imap(run_simulation, combinations),
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
    
    # Set pandas display options to show all columns
    pd.set_option('display.max_columns', None)  # Show all columns
    pd.set_option('display.width', None)        # Don't wrap wide tables
    pd.set_option('display.max_rows', 10)       # Limit to 10 rows by default
    
    # Save results
    df_sorted.to_csv('simulation_results.csv', index=False)
    
    # Print top 10 configurations
    print("\nTop 10 Configurations:")
    print(df_sorted.head(10))
    
    # Basic statistical analysis
    print("\nParameter Impact Analysis:")
    for param in ['lands', 'mana_rocks', 'land_ramp', 'immediate_draw', 
                 'per_turn_draw', 'on_cast_draw', 'curve']:
        correlation = df[param].corr(df['total_mana_spent'])
        print(f"{param}: correlation with total mana spent = {correlation:.3f}")

if __name__ == "__main__":
    main()