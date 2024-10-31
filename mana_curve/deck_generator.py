import json
from typing import List, Dict, Tuple
import argparse
import random
import os
import sys

def generate_ramp_package(num_rocks: int, num_land_ramp: int) -> List[Dict]:
    """Generate a mix of mana rocks and land ramp spells."""
    ramp_spells = []
    
    # Standard ramp package templates
    mana_rocks = [
        {"name": "Mana Rock 1", "cmc": 1, "ramp_amount": 2},  # Sol Ring
        {"name": "Mana Rock 2", "cmc": 2, "ramp_amount": 1},  # Various signets
        {"name": "Mana Rock 3", "cmc": 2, "ramp_amount": 1},
        {"name": "Mana Rock 4", "cmc": 2, "ramp_amount": 1},
        {"name": "Mana Rock 5", "cmc": 3, "ramp_amount": 1},
        {"name": "Mana Rock 6", "cmc": 3, "ramp_amount": 1}
    ]
    
    land_ramp = [
        {"name": "Land Ramp 1", "cmc": 2, "ramp_amount": 1},  # Nature's Lore style
        {"name": "Land Ramp 2", "cmc": 2, "ramp_amount": 1},
        {"name": "Land Ramp 2", "cmc": 2, "ramp_amount": 1},
        {"name": "Land Ramp 2", "cmc": 2, "ramp_amount": 1},
        {"name": "Land Ramp 2", "cmc": 2, "ramp_amount": 1},
        {"name": "Land Ramp 2", "cmc": 3, "ramp_amount": 1},
        {"name": "Land Ramp 2", "cmc": 3, "ramp_amount": 1},
        {"name": "Land Ramp 2", "cmc": 3, "ramp_amount": 1},
        {"name": "Land Ramp 2", "cmc": 3, "ramp_amount": 1},
        {"name": "Land Ramp 2", "cmc": 3, "ramp_amount": 1},
        {"name": "Land Ramp 2", "cmc": 3, "ramp_amount": 1},
        {"name": "Land Ramp 2", "cmc": 3, "ramp_amount": 1},
        {"name": "Land Ramp 2", "cmc": 3, "ramp_amount": 1},
        {"name": "Land Ramp 2", "cmc": 3, "ramp_amount": 1},
        {"name": "Land Ramp 3", "cmc": 3, "ramp_amount": 1, "land_to_hand": 1},  # Cultivate style
        {"name": "Land Ramp 4", "cmc": 3, "ramp_amount": 1, "land_to_hand": 1},  # Kodama's Reach
        {"name": "Land Ramp 5", "cmc": 4, "ramp_amount": 2},  # Skyshroud Claim style
        {"name": "Land Ramp 6", "cmc": 4, "ramp_amount": 2},
        {"name": "Land Ramp 6", "cmc": 4, "ramp_amount": 2},
        {"name": "Land Ramp 6", "cmc": 4, "ramp_amount": 2},
        {"name": "Land Ramp 6", "cmc": 4, "ramp_amount": 2},
    ]
    
    if num_rocks > len(mana_rocks):
        raise ValueError(f"Requested {num_rocks} mana rocks but only {len(mana_rocks)} templates available")
    if num_land_ramp > len(land_ramp):
        raise ValueError(f"Requested {num_land_ramp} land ramp spells but only {len(land_ramp)} templates available")
    
    for i in range(num_rocks):
        spell = mana_rocks[i].copy()
        spell["is_ramp"] = True
        spell["ramp_type"] = "mana"
        ramp_spells.append(spell)
    
    for i in range(num_land_ramp):
        spell = land_ramp[i].copy()
        spell["is_ramp"] = True
        spell["ramp_type"] = "land"
        ramp_spells.append(spell)
    
    return ramp_spells

def generate_draw_package(num_immediate: int, num_per_turn: int, num_on_cast: int) -> List[Dict]:
    """Generate a mix of different card draw effects."""
    draw_spells = []
    
    # Draw spell templates
    immediate_draw = [
        {"name": "Instant Draw 1", "cmc": 1, "draw_amount": 1},  # Ponder style
        {"name": "Instant Draw 2", "cmc": 2, "draw_amount": 2},  # Divination style
        {"name": "Instant Draw 2", "cmc": 2, "draw_amount": 2},  # Divination style
        {"name": "Instant Draw 2", "cmc": 2, "draw_amount": 2},  # Divination style
        {"name": "Instant Draw 2", "cmc": 2, "draw_amount": 2},  # Divination style
        {"name": "Instant Draw 2", "cmc": 2, "draw_amount": 2},  # Divination style
        {"name": "Instant Draw 3", "cmc": 4, "draw_amount": 3},  # Harmonize style
        {"name": "Instant Draw 3", "cmc": 4, "draw_amount": 3},  # Harmonize style
        {"name": "Instant Draw 3", "cmc": 4, "draw_amount": 3},  # Harmonize style
        {"name": "Instant Draw 3", "cmc": 4, "draw_amount": 3},  # Harmonize style
        {"name": "Instant Draw 3", "cmc": 4, "draw_amount": 3},  # Harmonize style
        {"name": "Instant Draw 4", "cmc": 5, "draw_amount": 4},   # Opportunity style
        {"name": "Instant Draw 4", "cmc": 5, "draw_amount": 4},   # Opportunity style
        {"name": "Instant Draw 4", "cmc": 5, "draw_amount": 4},   # Opportunity style
        {"name": "Instant Draw 4", "cmc": 5, "draw_amount": 4},   # Opportunity style
        {"name": "Instant Draw 4", "cmc": 5, "draw_amount": 4},   # Opportunity style
    ]
    
    per_turn_draw = [
        {"name": "Per Turn Draw 1", "cmc": 2, "draw_amount": 1},  # Faerie mastermind style
        {"name": "Per Turn Draw 2", "cmc": 3, "draw_amount": 1},  # Phyrexian Arena style
        {"name": "Per Turn Draw 2", "cmc": 3, "draw_amount": 1},  # Phyrexian Arena style
        {"name": "Per Turn Draw 2", "cmc": 3, "draw_amount": 1},  # Phyrexian Arena style
        {"name": "Per Turn Draw 2", "cmc": 3, "draw_amount": 1},  # Phyrexian Arena style
        {"name": "Per Turn Draw 3", "cmc": 4, "draw_amount": 1},  # Twilight Prophet style
        {"name": "Per Turn Draw 3", "cmc": 4, "draw_amount": 1},  # Twilight Prophet style
        {"name": "Per Turn Draw 3", "cmc": 4, "draw_amount": 1},  # Twilight Prophet style

    ]
    
    on_cast_draw = [
        {"name": "Cast Draw 1", "cmc": 2, "draw_amount": 1},  # Glimpse of Nature style
        {"name": "Cast Draw 2", "cmc": 3, "draw_amount": 1},  # Rhystic Study style
        {"name": "Cast Draw 3", "cmc": 4, "draw_amount": 1},  # Beast Whisperer style
        {"name": "Cast Draw 3", "cmc": 4, "draw_amount": 1},  # Beast Whisperer style
        {"name": "Cast Draw 3", "cmc": 4, "draw_amount": 1},  # Beast Whisperer style
        {"name": "Cast Draw 3", "cmc": 4, "draw_amount": 1},  # Beast Whisperer style
        {"name": "Cast Draw 3", "cmc": 4, "draw_amount": 1},  # Beast Whisperer style

    ]
    
    if num_immediate > len(immediate_draw):
        raise ValueError(f"Requested {num_immediate} immediate draw spells but only {len(immediate_draw)} templates available")
    if num_per_turn > len(per_turn_draw):
        raise ValueError(f"Requested {num_per_turn} per-turn draw spells but only {len(per_turn_draw)} templates available")
    if num_on_cast > len(on_cast_draw):
        raise ValueError(f"Requested {num_on_cast} on-cast draw spells but only {len(on_cast_draw)} templates available")
    
    for i in range(num_immediate):
        spell = immediate_draw[i].copy()
        spell["is_draw"] = True
        spell["draw_type"] = "immediate"
        draw_spells.append(spell)
    
    for i in range(num_per_turn):
        spell = per_turn_draw[i].copy()
        spell["is_draw"] = True
        spell["draw_type"] = "per_turn"
        draw_spells.append(spell)
    
    for i in range(num_on_cast):
        spell = on_cast_draw[i].copy()
        spell["is_draw"] = True
        spell["draw_type"] = "on_cast"
        draw_spells.append(spell)
    
    return draw_spells

def generate_curve(remaining_cards: int, curve_center: float, spread: float = 1.0) -> List[Dict]:
    """Generate regular spells following a right-skewed distribution around curve_center."""
    spells = []
    
    # Create distribution of CMCs
    min_cmc = max(1, int(curve_center - 2 * spread))
    max_cmc = int(curve_center + 4 * spread)  # Increased from 2 to 4 to allow higher CMCs
    
    # Calculate weights for each CMC with right skew
    weights = {}
    total_weight = 0
    for cmc in range(min_cmc, max_cmc + 1):
        if cmc <= curve_center:
            # Below center: normal weight calculation
            distance_from_center = abs(cmc - curve_center)
            weight = 1.0 / (1.0 + distance_from_center)
        else:
            # Above center: slower dropoff for right skew
            distance_from_center = abs(cmc - curve_center)
            weight = 1.0 / (1.0 + distance_from_center * 1.5)  # Slower dropoff
            
        # Additional scaling for very high CMC
        if cmc >= 7:
            weight *= 0.5  # Reduce frequency of very high CMC spells
            
        weights[cmc] = weight
        total_weight += weight
    
    # Distribute cards according to weights
    cmc_counts = {}
    cards_left = remaining_cards
    
    # First pass: distribute cards proportionally
    for cmc, weight in weights.items():
        count = int((weight / total_weight) * remaining_cards)
        cmc_counts[cmc] = count
        cards_left -= count
    
    # Second pass: distribute remaining cards to closest CMC to center
    while cards_left > 0:
        closest_cmc = min(weights.keys(), key=lambda x: abs(x - curve_center))
        cmc_counts[closest_cmc] += 1
        cards_left -= 1
    
    # Generate spells for each CMC
    for cmc, count in cmc_counts.items():
        for i in range(count):
            spell = {
                "name": f"{cmc}-Drop Spell {i+1}",
                "cmc": cmc
            }
            spells.append(spell)
    
    return spells

def generate_deck(num_lands: int, 
                 num_rocks: int, num_land_ramp: int,
                 num_immediate: int, num_per_turn: int, num_on_cast: int,
                 curve_center: float, output_file: str):
    """Generate a complete deck configuration and save to JSON."""
    try:
        deck = []
        
        # Validate total utility cards
        total_utility = (num_lands + num_rocks + num_land_ramp + 
                        num_immediate + num_per_turn + num_on_cast)
        if total_utility >= 100:
            raise ValueError(
                f"Too many utility cards specified: {total_utility} total "
                f"({num_lands} lands + {num_rocks + num_land_ramp} ramp + "
                f"{num_immediate + num_per_turn + num_on_cast} draw). "
                f"Need at least 1 card for the regular curve."
            )
        
        # Add lands
        deck.append({
            "name": "Basic Land",
            "cmc": 0,
            "quantity": num_lands,
            "is_land": True
        })
        
        # Add ramp package
        ramp_spells = generate_ramp_package(num_rocks, num_land_ramp)
        deck.extend(ramp_spells)
        
        # Add draw package
        draw_spells = generate_draw_package(num_immediate, num_per_turn, num_on_cast)
        deck.extend(draw_spells)
        
        # Calculate remaining cards
        total_utility = num_lands + len(ramp_spells) + len(draw_spells)
        remaining_cards = 100 - total_utility
        
        if remaining_cards < 0:
            raise ValueError(
                f"Too many utility cards specified: {total_utility} total "
                f"({num_lands} lands + {len(ramp_spells)} ramp + {len(draw_spells)} draw). "
                f"Need {-remaining_cards} fewer cards."
            )
        
        # Add regular spells following the curve
        curve_spells = generate_curve(remaining_cards, curve_center)
        deck.extend(curve_spells)
        
        # Ensure the output directory exists
        output_dir = os.path.dirname(os.path.abspath(output_file))
        os.makedirs(output_dir, exist_ok=True)
        
        # Save to JSON with explicit flush
        with open(output_file, 'w') as f:
            json.dump(deck, f, indent=4)
            f.flush()
            os.fsync(f.fileno())  # Force write to disk
            
        # Verify the file was created
        if not os.path.exists(output_file):
            raise ValueError(f"Failed to create deck file: {output_file}")
            
        return True
        
    except Exception as e:
        print(f"Error generating deck: {str(e)}", file=sys.stderr)
        return False

def get_parser():
    parser = argparse.ArgumentParser(description='Generate a Magic deck configuration')
    parser.add_argument('--lands', type=int, default=38, help='Number of lands')
    
    # Ramp package arguments
    parser.add_argument('--mana-rocks', type=int, default=4, help='Number of mana rock spells')
    parser.add_argument('--land-ramp', type=int, default=6, help='Number of land ramp spells')
    
    # Draw package arguments
    parser.add_argument('--immediate-draw', type=int, default=4, help='Number of immediate draw spells')
    parser.add_argument('--per-turn-draw', type=int, default=3, help='Number of per-turn draw spells')
    parser.add_argument('--on-cast-draw', type=int, default=3, help='Number of on-cast draw spells')
    
    parser.add_argument('--curve', type=float, default=3.5, help='Center of mana curve')
    parser.add_argument('--output', type=str, default='deck.json', help='Output file name')
    return parser

if __name__ == "__main__":
    parser = get_parser()
    args = parser.parse_args()
    
    try:
        generate_deck(
            num_lands=args.lands,
            num_rocks=args.mana_rocks,
            num_land_ramp=args.land_ramp,
            num_immediate=args.immediate_draw,
            num_per_turn=args.per_turn_draw,
            num_on_cast=args.on_cast_draw,
            curve_center=args.curve,
            output_file=args.output
        )
    except ValueError as e:
        print(f"Error: {e}")
        exit(1)
