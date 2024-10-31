import json
from typing import List
from dataclasses import dataclass

@dataclass
class Card:
    name: str
    cmc: int
    quantity: int = 1
    is_land: bool = False
    is_ramp: bool = False
    ramp_type: str = ""  # "land" or "mana"
    ramp_amount: int = 0
    land_to_hand: int = 0  # For Cultivate-style effects
    is_draw: bool = False
    draw_type: str = ""  # "immediate", "per_turn", or "on_cast"
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