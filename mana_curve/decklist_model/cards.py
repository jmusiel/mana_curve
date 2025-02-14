from typing import List, Optional
from mana_curve.decklist_model.mana_functions import (
    cryptolith_rites,
    enchantment_sanctums,
)

class Card:
    card_class = 'Card'
    card_names = []
    ramp = False
    priority = 0
    land_priority = 0
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
        self.unique_name = f"{self.name} ({self.index})"

        self.sub_types = [t.lower() for t in self.sub_types]
        self.types = [t.lower() for t in self.types]
        self.super_types = [t.lower() for t in self.super_types]

        self.zone = None
        self.spell = False
        self.permanent = False
        self.nonpermanent = False
        self.creature = False
        self.land = False
        self.artifact = False
        self.enchantment = False
        self.planeswalker = False
        self.battle = False
        self.instant = False
        self.sorcery = False
        if "instant" in self.types:
            self.instant = True
            self.spell = True
            self.nonpermanent = True
        if "sorcery" in self.types:
            self.sorcery = True
            self.spell = True
            self.nonpermanent = True
        if 'creature' in self.types:
            self.creature = True
            self.spell = True
            self.permanent = True
        if 'artifact' in self.types:
            self.artifact = True
            self.spell = True
            self.permanent = True
        if 'enchantment' in self.types:
            self.enchantment = True
            self.spell = True
            self.permanent = True
        if 'planeswalker' in self.types:
            self.planeswalker = True
            self.spell = True
            self.permanent = True
        if 'battle' in self.types:
            self.battle = True
            self.spell = True
            self.permanent = True
        if 'land' in self.types:
            self.permanent = True
            self.land = True
        
        self.mdfc = False
        if self.land and self.spell:
            self.mdfc = True
            self.land_priority = -1

    def __lt__(self, other):
        if not self.priority == other.priority:
            return self.priority < other.priority            
        if not self.land_priority == other.land_priority:
            return self.land_priority < other.land_priority
        return self.cmc < other.cmc


    def __eq__(self, other):
        return self.name == other.name

    def __str__(self):
        return f"{self.name}: {self.cost}"
    
    def __repr__(self) -> str:
        return f"({self.card_class}) {self.name}: {self.cmc}"
    
    def change_zone(self, new_zone):
        self.zone.remove(self.index)
        self.zone = new_zone
        new_zone.append(self.index)

    def get_current_cost(self):
        cost = self.cmc
        if self.nonpermanent:
            cost -= self.goldfisher.nonpermanent_cost_reduction
        if self.permanent:
            cost -= self.goldfisher.permanent_cost_reduction
        if self.spell:
            cost -= self.goldfisher.spell_cost_reduction
        if self.creature:
            cost -= self.goldfisher.creature_cost_reduction
        if self.enchantment:
            cost -= self.goldfisher.enchantment_cost_reduction
        cost = max(1, cost)
        return cost

    def when_played(self):
        self.goldfisher.log.append(f"Played {self.printable}")
        self.mana_spent_when_played = self.cmc
        if self.creature:
            self.goldfisher.creatures_played += 1
        if self.enchantment:
            self.goldfisher.enchantments_played += 1
        if self.artifact:
            self.goldfisher.artifacts_played += 1
        return self
    
    def played_as_land(self):
        self.goldfisher.log.append(f"Played as land {self.printable}")
        self.mana_spent_when_played  = 0
        return self
    
    
class Land(Card):
    card_class = 'Land'
    card_names = []
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.printable = f"(Land) {self.name}"
        self.tapped = False

class ManaProducer(Card):
    card_class = 'ManaProducer'
    card_names = [
        "Sol Ring",
        "Relic of Sauron",
        "Arcane Signet",
        "Fellwar Stone",
        "Sakura-Tribe Elder",
        "Incubation Druid",
        "Rishkar, Peema Renegade",
        "Katilda, Dawnhart Prime",
        "Commander's Sphere",
        "Orzhov Signet",
        "Solemn Simulacrum",
        "Claim Jumper",
        "Talisman of Hierarchy",
        "Deep Gnome Terramancer",
        "Cultivate", # tommy slimes
        "Utopia Sprawl",
        "Wild Growth",
        "Overgrowth",
        "Fertile Ground",
        "Wolfwillow Haven",
        "Kodama's Reach",
        "Farseek",
    ]
    ramp = True
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.name in [
            "Arcane Signet",
            "Fellwar Stone",
            "Sakura-Tribe Elder",
            "Incubation Druid",
            "Commander's Sphere",
            "Orzhov Signet",
            "Solemn Simulacrum",
            "Claim Jumper",
            "Talisman of Hierarchy",
            "Deep Gnome Terramancer",
            "Cultivate", # tommy slimes
            "Utopia Sprawl",
            "Wild Growth",
            "Fertile Ground",
            "Wolfwillow Haven",
            "Kodama's Reach",
            "Farseek",
        ]:
            self.mana = 1
        elif self.name in [
            "Sol Ring",
            "Relic of Sauron",
            "Rishkar, Peema Renegade",
            "Katilda, Dawnhart Prime",
            "Overgrowth",
        ]:
            self.mana = 2
        elif self.name in [
            "Open the Way"
        ]:
            self.mana = 3
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
        "Smothering Tithe",
        "Gyre Sage",
        "Kami of Whispered Hopes",
        "Heronblade Elite",
        "Kodama of the West Tree",
    ]
    ramp = True
    priority = 2
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # initial mana production
        self.mana = 0
        if self.name in []:
            self.mana = 1

        # mana scaling rate
        if self.name in [
            "Séance Board",
            "As Foretold",
            "Smothering Tithe",
            "Gyre Sage",
            "Kami of Whispered Hopes",
            "Heronblade Elite",
            "Kodama of the West Tree",
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

class CryptolithRite(Card):
    card_class = 'CryptolithRite'
    card_names = [
        "Gemhide Sliver",
        "Enduring Vitality",
        "Cryptolith Rite",
        "Manaweft Sliver",
    ]
    ramp = True
    priority = 2

    def when_played(self):
        super().when_played()
        self.goldfisher.mana_functions.append(cryptolith_rites)
        return self
    
class Sanctum(Card):
    card_class = 'Sanctum'
    card_names = [
        "Serra's Sanctum",
        "Sanctum Weaver",
    ]
    priority = 2

    def __init__(self, *args, **kwargs):
        if kwargs['name'] == "Serra's Sanctum":
            kwargs['types'] = ['artifact']
        super().__init__(*args, **kwargs)

    def when_played(self):
        super().when_played()
        self.goldfisher.mana_functions.append(enchantment_sanctums)
        return self
    
    def when_played_as_land(self):
        super().when_played_as_land()
        self.goldfisher.mana_functions.append(enchantment_sanctums)
        return self

class CostReducer(Card):
    card_class = 'CostReducer'
    card_names = [
        "Thunderclap Drake",
        "Case of the Ransacked Lab",
        "Hamza, Guardian of Arashin",
        "Umori, the Collector", # tommy slimes
        "Jukai Naturalist",
        "Inquisitive Glimmer",
    ]
    ramp = True
    priority = 2

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.nonpermanent_cost_reduction = 0
        self.permanent_cost_reduction = 0
        self.creature_cost_reduction = 0
        self.spell_cost_reduction = 0
        self.enchantment_cost_reduction = 0
        if self.name in [
            "Thunderclap Drake",
            "Case of the Ransacked Lab",
        ]:
            self.nonpermanent_cost_reduction = 1
        elif self.name in [
            "Hamza, Guardian of Arashin",
            "Umori, the Collector", # tommy slimes
        ]:
            self.creature_cost_reduction = 1
        elif self.name in [
            "Jukai Naturalist",
            "Inquisitive Glimmer",
        ]:
            self.enchantment_cost_reduction = 1
        else:
            raise ValueError(f"Unknown cost reducer {self.name}")

    def when_played(self):
        super().when_played()
        self.goldfisher.nonpermanent_cost_reduction += self.nonpermanent_cost_reduction
        self.goldfisher.permanent_cost_reduction += self.permanent_cost_reduction
        self.goldfisher.creature_cost_reduction += self.creature_cost_reduction
        self.goldfisher.spell_cost_reduction += self.spell_cost_reduction
        self.goldfisher.enchantment_cost_reduction += self.enchantment_cost_reduction
        return self
    
class Tutor(Card):
    card_class = 'Tutor'
    card_names = [
        "Green Sun's Zenith",
        "Finale of Devastation",
    ]
    ramp = True
    priority = 3

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.name in [
            "Green Sun's Zenith",
            "Finale of Devastation",
        ]:
            self.tutor_targets = [
                "Gemhide Sliver",
                "Manaweft Sliver",
                "Enduring Vitality",
                "Sanctum Weaver",
                "Argothian Enchantress",
                "Sythis, Harvest's Hand",
                "Setessan Champion",
                "Satyr Enchanter",
                "Verduran Enchantress",
                "Eidolon of Blossoms",
            ]
        else:
            raise ValueError(f"Unknown cost reducer {self.name}")

    def when_played(self):
        super().when_played()
        for target in self.tutor_targets:
            if target in self.goldfisher.deckdict:
                card = self.goldfisher.deckdict[target]
                # card = self.goldfisher.decklist[card_i]
                if card.zone == self.goldfisher.deck:
                    self.goldfisher.log.append(f"Tutored {card.printable}")
                    card.change_zone(self.goldfisher.hand)
                    break
                else:
                    self.goldfisher.log.append(f"Failed to find {card.printable}")
        return self
    

class LandTutor(Card):
    card_class = 'LandTutor'
    card_names = [
        "Tolaria West",
        "Urza's Cave",
    ]
    ramp = True
    priority = 3

    def __init__(self, *args, **kwargs):
        kwargs['types'] += ['sorcery']
        kwargs['cmc'] = 3
        super().__init__(*args, **kwargs)
        self.tapped = False
        if self.name == "Tolaria West":
            self.tapped = True

        if self.name in [
            "Tolaria West",
            "Urza's Cave",
        ]:
            self.tutor_targets = [
                "Serra's Sanctum",
            ]
        else:
            raise ValueError(f"Unknown land tutor {self.name}")

    def when_played(self):
        super().when_played()
        for target in self.tutor_targets:
            if target in self.goldfisher.deckdict:
                card = self.goldfisher.deckdict[target]
                if card.zone == self.goldfisher.deck:
                    self.goldfisher.log.append(f"Tutored {card.printable}")
                    card.change_zone(self.goldfisher.hand)
                    break
        return self


class Draw(Card):
    card_class = 'Draw'
    card_names = [
        "Manifold Insights",
        "Mystic Confluence",
        "Flame of Anor",
        "Armorcraft Judge",
        "Inspiring Call",
        "Rishkar's Expertise",
        "Krav, the Unredeemed",
        "Archivist of Oghma",
        "Body Count",
        "Plumb the Forbidden",
        "Growth Spiral", # tommy slimes
        "Explore", # tommy slimes
        "Mulch", # tommy slimes
        "Urban Evolution", # tommy slimes
    ]
    priority = 1

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.name in [
            "Archivist of Oghma",
            "Growth Spiral", # tommy slimes
            "Explore", # tommy slimes
            "Mulch", # tommy slimes
        ]:
            self.draw = 1
        elif self.name in [
            "Flame of Anor",
            "Plumb the Forbidden",
        ]:
            self.draw = 2
        elif self.name in [
            "Manifold Insights",
            "Mystic Confluence",
            "Armorcraft Judge",
            "Inspiring Call",
            "Krav, the Unredeemed",
            "Body Count",
            "Urban Evolution", # tommy slimes
        ]:
            self.draw = 3
        elif self.name in [
            "Rishkar's Expertise",
        ]:
            self.draw = 4
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
        "Maestros Charm",
        "Prismari Command",
        "Deadly Dispute",
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
    priority = 1

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.firstdraw = 0
        self.discard = 0
        self.seconddraw = 0
        self.make_treasures = 0


        if self.name in [
            "Frantic Search",
            "Brainstorm",
            "Gitaxian Probe",
            "Gamble",
            "Visions of Beyond",
            "Mystical Tutor",
            "See the Truth",
        ]:
            self.firstdraw = 1
        elif self.name in [
            "Fact or Fiction",
        ]:
            self.firstdraw = 5
            self.discard = 2
        elif self.name in [
            "Windfall",
        ]:
            self.discard = 100
            self.seconddraw = 6
        elif self.name in [
            "Unexpected Windfall",
            "Big Score",
        ]:
            self.discard = 1
            self.seconddraw = 2
            self.make_treasures = 2
        elif self.name in [
            "Maestros Charm",
        ]:
            self.firstdraw = 5
            self.discard = 4
        elif self.name in [
            "Picklock Prankster // Free the Fae",
        ]:
            self.firstdraw = 4
            self.discard = 3
        elif self.name in [
            "Consider",
        ]:
            self.firstdraw = 2
            self.discard = 1
        elif self.name in [
            "Thought Scour",
        ]:
            self.firstdraw = 3
            self.discard = 2
        elif self.name in [
            "Faithless Looting",
        ]:
            self.firstdraw = 2
            self.discard = 2
        elif self.name in [
            "Prismari Command",
        ]:
            self.firstdraw = 2
            self.discard = 2
            self.make_treasures = 1
        elif self.name in [
            "Deadly Dispute",
        ]:
            self.firstdraw = 2
            self.make_treasures = 1
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
        "Black Market Connections",
        "Esper Sentinel",
        "Phyrexian Arena",
        "Toski, Bearer of Secrets",
        "Leinore, Autumn Sovereign",
        "Compost", # tommy slimes
        "Tuvasa the Sunlit",
        "Mystic Remora",
    ]
    priority = 1

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.name in [
            "Black Market Connections",
            "Esper Sentinel",
            "Phyrexian Arena",
            "Toski, Bearer of Secrets",
            "Leinore, Autumn Sovereign",
            "Compost", # tommy slimes
            "Tuvasa the Sunlit",
            "Mystic Remora",
        ]:
            self.redraw = 1
        else:
            raise ValueError(f"Unknown draw {self.name}")

    def per_turn(self):
        for i in range(self.redraw):
            self.goldfisher.draw()
        return self
    
class PerCastDraw(Card):
    card_class = 'PerCastDraw'
    card_names = [
        "Archmage Emeritus",
        "Bolas's Citadel",
        "Archmage of Runes",
        "Skullclamp",
        "Beast Whisperer",
        "The Great Henge",
        "Guardian Project",
        "Vanquisher's Banner", # tommy slimes
        "Tribute to the World Tree", # tommy slimes
        "Mesa Enchantress",
        "Satyr Enchanter",
        "Enchantress's Presence",
        "Entity Tracker",
        "Eidolon of Blossoms",
        "Setessan Champion",
        "Sythis, Harvest's Hand",
        "Verduran Enchantress",
        "Argothian Enchantress",

    ]
    priority = 1

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.nonpermanent_cast_draw = 0
        self.permanent_cast_draw = 0
        self.spell_cast_draw = 0
        self.creature_cast_draw = 0
        self.enchantment_cast_draw = 0

        if self.name in [
            "Archmage of Runes",
            "Archmage Emeritus",
        ]:
            self.nonpermanent_cast_draw = 1
        elif self.name in [
            "Bolas's Citadel",
        ]:
            self.spell_cast_draw = 1
        elif self.name in [
            "Skullclamp",
            "Beast Whisperer",
            "The Great Henge",
            "Guardian Project",
            "Vanquisher's Banner", # tommy slimes
            "Tribute to the World Tree", # tommy slimes
        ]:
            self.creature_cast_draw = 1
        elif self.name in [
            "Mesa Enchantress",
            "Satyr Enchanter",
            "Enchantress's Presence",
            "Entity Tracker",
            "Eidolon of Blossoms",
            "Setessan Champion",
            "Sythis, Harvest's Hand",
            "Verduran Enchantress",
            "Argothian Enchantress",
        ]:
            self.enchantment_cast_draw = 1
        else:
            raise ValueError(f"Unknown draw {self.name}")
        
        # add mana production
        self.mana_production = 0
        if self.name in [
            "The Great Henge",
        ]:
            self.mana_production = 2
        # add cost reduction
        self.nonpermanent_cost_reduction = 0
        if self.name in [
            "Archmage of Runes",
        ]:
            self.nonpermanent_cost_reduction = 1
    
    def cast_trigger(self, casted_card):
        if casted_card.nonpermanent:
            for i in range(self.nonpermanent_cast_draw):
                self.goldfisher.draw()
        if casted_card.spell:
            for i in range(self.spell_cast_draw):
                self.goldfisher.draw()
        if casted_card.creature:
            for i in range(self.creature_cast_draw):
                self.goldfisher.draw()
        if casted_card.enchantment:
            for i in range(self.enchantment_cast_draw):
                self.goldfisher.draw()
        return self
    
    def when_played(self):
        super().when_played()
        self.goldfisher.mana_production += self.mana_production
        self.goldfisher.nonpermanent_cost_reduction += self.nonpermanent_cost_reduction
        return self
    
class LorienRevealed(Card):
    card_class = 'LorienRevealed'
    card_names = [
        "Lórien Revealed",
    ]

    def __init__(self, *args, **kwargs):
        kwargs['types'] += ['land']
        super().__init__(*args, **kwargs)
        self.draw = 3

    def when_played(self):
        super().when_played()
        for i in range(self.draw):
            self.goldfisher.draw()
        return self
    
class CabalCoffers(Card):
    card_class = 'CabalCoffers'
    card_names = [
        "Cabal Coffers",
    ]

    def __init__(self, *args, **kwargs):
        kwargs['types'] = ['artifact']
        super().__init__(*args, **kwargs)



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
    if isinstance(card, CantripDraw):
        print(card.draw_card_effect())

    subclasses = Card.__subclasses__()
    print(subclasses)
    for subclass in subclasses:
        print(subclass.__name__)
        print(subclass.card_names)
