from typing import List, Optional

class Card:
    card_class = 'Card'
    card_names = []
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
        self.printable = name

        self.sub_types = [t.lower() for t in self.sub_types]
        self.types = [t.lower() for t in self.types]
        self.super_types = [t.lower() for t in self.super_types]

        self.zone = None
        self.spell = False
        self.permanent = False
        self.nonpermanent = False
        self.land = False
        for t in ['instant', 'sorcery']:
            if t in self.types:
                self.spell = True
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
    
    def __repr__(self) -> str:
        return f"({self.card_class}) {self.name}: {self.cmc}"
    
    def change_zone(self, new_zone):
        self.zone.remove(self.index)
        self.zone = new_zone
        new_zone.append(self.index)

    def when_played(self):
        if self.goldfisher.verbose:
            print(f"Played {self.printable}")
        return self
    
    
class Land(Card):
    card_class = 'Land'
    card_names = []
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.printable = f"(Land) {self.name}"

class ManaProducer(Card):
    card_class = 'ManaProducer'
    card_names = [
        "Sol Ring",
        "Relic of Sauron",
        "Arcane Signet",
        "Fellwar Stone",
    ]
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.name in [
            "Arcane Signet",
            "Fellwar Stone",
        ]:
            self.mana = 1
        elif self.name in [
            "Sol Ring",
            "Relic of Sauron",
        ]:
            self.mana = 2
        else:
            raise ValueError(f"Unknown mana producer {self.name}")
    
    def when_played(self):
        super().when_played()
        self.goldfisher.mana_production += self.mana
        return self
    
class ScalingManaProducer(Card):
    card_class = 'ScalingManaProducer'
    card_names = [
        "As Foretold",
        "Séance Board",
    ]
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # initial mana production
        if self.name in [
            "Séance Board",
            "As Foretold",
        ]:
            self.mana = 0
        else:
            raise ValueError(f"Unknown scaling mana producer {self.name}")
        
        # mana scaling rate
        if self.name in [
            "Séance Board",
            "As Foretold",
        ]:
            self.scaling_mana = 1
        else:
            raise ValueError(f"Unknown scaling mana producer {self.name}")
    
    def when_played(self):
        super().when_played()
        self.goldfisher.mana_production += self.mana
        return self
    
    def per_turn(self):
        self.goldfisher.mana_production += self.scaling_mana
        return self


class CostReducer_IS(Card):
    card_class = 'CostReducer_IS'
    card_names = []
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        

class Cantrip(Card):
    card_class = 'Cantrip'
    card_names = [
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
        "See the Truth",
    ]

    def when_played(self):
        super().when_played()
        self.goldfisher.draw()
        return self
    
class Draw(Card):
    card_class = 'Draw'
    card_names = [
        "Manifold Insights",
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.name in [
            "Manifold Insights",
        ]:
            self.draw = 3
        else:
            raise ValueError(f"Unknown draw {self.name}")

    def when_played(self):
        super().when_played()
        for i in range(self.draw):
            self.goldfisher.draw()
        return self
    
class DrawDiscard(Card):
    card_class = 'DrawDiscard'
    card_names = [
        "Windfall",
        "Unexpected Windfall",
        "Big Score",
        "Fact or Fiction",
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.firstdraw = 0
        self.discard = 0
        self.seconddraw = 0
        self.make_treasures = 0

        if self.name in [
            "Fact or Fiction",
        ]:
            self.firstdraw = 5
            self.discard = 2
            self.seconddraw = 0
            self.make_treasures = 0
        elif self.name in [
            "Windfall",
        ]:
            self.firstdraw = 0
            self.discard = 100
            self.seconddraw = 6
            self.make_treasures = 0
        elif self.name in [
            "Unexpected Windfall",
            "Big Score",
        ]:
            self.firstdraw = 0
            self.discard = 1
            self.seconddraw = 2
            self.make_treasures = 2
        else:
            raise ValueError(f"Unknown draw/discard {self.name}")
        
    def when_played(self):
        super().when_played()
        for i in range(self.firstdraw):
            self.goldfisher.draw()
        for i in range(self.discard):
            if len(self.goldfisher.hand) > 0:
                self.goldfisher.randomdiscard()
            else:
                break
        for i in range(self.seconddraw):
            self.goldfisher.draw()
        return self
    
class PerTurnDraw(Card):
    card_class = 'PerTurnDraw'
    card_names = [
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.name in [

        ]:
            self.draw = 3
        else:
            raise ValueError(f"Unknown draw {self.name}")

    def when_played(self):
        super().when_played()
        for i in range(self.draw):
            self.goldfisher.draw()
        return self
    
class PerCastDraw(Card):
    card_class = 'PerCastDraw'
    card_names = [
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.name in [

        ]:
            self.draw = 3
        else:
            raise ValueError(f"Unknown draw {self.name}")

    def when_played(self):
        super().when_played()
        for i in range(self.draw):
            self.goldfisher.draw()
        return self


# class New(Card):
#     card_class = ''
#     card_names = [
        
#     ]

#     def when_played(self):
#         super().when_played()
#         return self

# Add other subclasses as needed

CARD_CLASS_LOOKUP = {}
for subclass in Card.__subclasses__():
    for card_name in subclass.card_names:
        CARD_CLASS_LOOKUP[card_name] = subclass

def card_factory(**kwargs) -> Card:
    card = Card(**kwargs)

    if card.name in CARD_CLASS_LOOKUP:
        return CARD_CLASS_LOOKUP[card.name](**vars(card))
    
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

    subclasses = Card.__subclasses__()
    print(subclasses)
    for subclass in subclasses:
        print(subclass.__name__)
        print(subclass.card_names)
