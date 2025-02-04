from mana_curve.decklist_model.decklist import get_decklist, load_decklist
from mana_curve.decklist_model.cards import card_factory

class Goldfisher:
    def __init__(self, decklist_dict):
        self.decklist = [card_factory(**card) for card in decklist_dict]

        counts = {}
        for c in self.decklist:
            if c.card_class not in counts:
                counts[c.card_class] = 0
            counts[c.card_class] += 1
            if c.card_class == 'Cantrip':
                print(c.name)
        print(counts)

    def simulate(self):
        pass

if __name__ == "__main__":
    decklist = load_decklist("kess")
    goldfisher = Goldfisher(decklist)
    goldfisher.simulate()