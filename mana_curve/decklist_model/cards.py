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
            commander: Optional[bool] = None,
            goldfisher=None,
            index: Optional[int] = None,
            **kwargs,
        ):
        self.name = name
        self.quantity = quantity
        self.oracle_cmc = oracle_cmc
        self.cmc = cmc
        self.cost = cost.lower()
        self.text = text.lower()
        self.sub_types = sub_types if sub_types is not None else []
        self.super_types = super_types if super_types is not None else []
        self.types = types if types is not None else []
        self.identity = identity if identity is not None else []
        self.default_category = default_category
        self.user_category = user_category
        self.commander = commander
        self.goldfisher = goldfisher
        self.index = index

        self.sub_types = [t.lower() for t in self.sub_types]
        self.types = [t.lower() for t in self.types]
        self.super_types = [t.lower() for t in self.super_types]

        self.card_class = 'Card'
        self.zone = None
        self.spell = False
        self.permanent = False
        self.nonpermanent = False
        self.land = False
        for t in ['instant', 'sorcery']:
            if t in self.types:
                self.nonpermanent = True
        for t in ['creature', 'artifact', 'enchantment',  'planeswalker', 'battle']:
            if t in self.types:
                self.spell = True
                self.permanent = True
        if 'land' in self.types:
            self.permanent = True
            self.land = True
        self.mdfc = '//' in self.name

    def __lt__(self, other):
        return self.cmc < other.cmc

    def __eq__(self, other):
        return self.cmc == other.cmc

    def __str__(self):
        return f"{self.name}: {self.cost}"
    
    def change_zone(self, new_zone):
        self.zone.remove(self.index)
        self.zone = new_zone
        new_zone.append(self.index)

    def when_played(self):
        return self


class Cantrip(Card):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.card_class = 'Cantrip'

    def when_played(self):
        # self.goldfisher.draw()
        return self
    
class Land(Card):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.card_class = 'Land'

# Add other subclasses as needed

def card_factory(**kwargs) -> Card:
    card = Card(**kwargs)

    if card.name in [
        "Picklock Prankster // Free the Fae",
        "Frantic Search",
        "Brainstorm",
        "Consider",
        "Thought Scour",
        "Faithless Looting",
        "Gitaxian Probe",
        "Gamble",
        "Visions of Beyond",
        "Mystical Tutor",
    ]:
        print(f"Creating Cantrip: {card.name}")
        return Cantrip(**vars(card))
    
    if card.land:
        return Land(**vars(card))
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
