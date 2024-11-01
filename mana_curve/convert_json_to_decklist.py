import json
import argparse

def get_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--deck_file",
        type=str,
        default="top_decklists/deck_1_score_72.json",
        help="Path to the JSON deck file"
    )
    return parser

def get_category_name(card):
    """Generate the appropriate category name based on card attributes"""
    if card['is_commander']:
        return "Commander"
    
    prefix = "~"
    
    # Determine the main category
    if card['is_land']:
        return f"{prefix}/land"
    elif card['is_value']:
        return f"{prefix}/value"
    elif card['is_ramp']:
        return f"{prefix}/ramp/{card['ramp_type']}/{card['ramp_amount']}"
    elif card['is_draw']:
        return f"{prefix}/draw/{card['draw_type']}/{card['draw_amount']}"
    
    return prefix  # fallback

def main(config):
    # Read the JSON deck file
    with open(config['deck_file'], 'r') as f:
        deck_list = json.load(f)

    if 'decklist' in deck_list:
        deck_list = deck_list['decklist']
    # Create category-based organization
    categories = {}
    for card in deck_list:
        category = get_category_name(card)
        if category not in categories:
            categories[category] = []
        categories[category].append(f"{card['quantity']} {card['name']}")
    
    # Output the decklist in Archidekt format
    for category, cards in categories.items():
        # print(f"// {category}")
        for card in cards:
            print(f"{card} [{category}]")
        print()

if __name__ == "__main__":
    parser = get_parser()
    args = parser.parse_args()
    config = vars(args)
    main(config)
