from typing import List, Optional

class Card:
    def __init__(
            self,
            name: Optional[str] = None,
            quantity: Optional[int] = None,
            oracle_cmc: Optional[int] = None,
            cmc: Optional[int] = None,
            cost: Optional[str] = None,
            text: Optional[str] = None,
            sub_types: List[str] = None,
            super_types: List[str] = None,
            types: List[str] = None,
            identity: List[str] = None,
            default_category: Optional[str] = None,
            user_category: Optional[str] = None,
            **kwargs,
        ):
        self.name = name
        self.quantity = quantity
        self.oracle_cmc = oracle_cmc
        self.cmc = cmc
        self.cost = cost
        self.text = text
        self.sub_types = sub_types if sub_types is not None else []
        self.super_types = super_types if super_types is not None else []
        self.types = types if types is not None else []
        self.identity = identity if identity is not None else []
        self.default_category = default_category
        self.user_category = user_category

        self.card_class = 'Card'

    def __str__(self):
        return f"{self.name}: {self.cost}"

class Cantrip(Card):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.card_class = 'Cantrip'

    def draw_card_effect(self):
        return f"{self.name} has a draw card effect."

# Add other subclasses as needed

def card_factory(**kwargs) -> Card:
    card = Card(**kwargs)

    if 'draw a card' in card.text.lower():
        return Cantrip(**vars(card))
    # Add other conditions for different subclasses here

    return Card(**kwargs)

# Example usage
if __name__ == "__main__":
    card_data = {
        "name": "Example Card",
        "quantity": 1,
        "oracle_cmc": 2,
        "cmc": 2,
        "cost": "{1}{U}",
        "text": "When this card enters the battlefield, draw a card.",
        "sub_types": ["Wizard"],
        "super_types": ["Legendary"],
        "types": ["Creature"],
        "identity": ["U"],
        "default_category": "Main",
        "user_category": "Draw"
    }

    card = card_factory(**card_data)
    print(card)
    if isinstance(card, Cantrip):
        print(card.draw_card_effect())
