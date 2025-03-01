import argparse
import pprint
pp = pprint.PrettyPrinter(indent=4)

import json
from tqdm import tqdm
from collections import defaultdict

def get_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--file",
        type=str, 
        default="bulk.json",
    )
    parser.add_argument(
        "--cards",
        type=str, 
        nargs="+",
        default=[],
        # default=[
        #     "Thornbite Staff",
        #     "Thermopod",
        #     "Goblin Bombardment",
        #     "Blasting Station",
        #     "Bartolomé del Presidio",
        #     "Ashnod's Altar",
        #     "Yahenni, Undying Partisan",
        #     "Woe Strider",
        #     "Viscera Seer",
        #     "Carrion Feeder",
        #     "Bloodflow Connoisseur",
        #     "Altar of Dementia",
        #     "Academy Manufactor",
        #     "Wispweaver Angel",
        #     "Krark-Clan Ironworks",
        #     "Phyrexian Altar",
        #     "Intruder Alarm",
        #     "Xenograft",
        #     "Rukarumel, Biologist",
        #     "Conspiracy",
        #     "Leyline of Transformation",
        #     "Arcane Adaptation",
        #     "Ruthless Technomancer",
        #     "Zirda, the Dawnwaker",
        #     "Underworld Breach",
        #     "Optimus Prime, Hero // Optimus Prime, Autobot Leader",
        #     "Sarcatog",
        #     "Ravenous Intruder",
        #     "Megatog",
        #     "Krark-Clan Grunt",
        #     "Grinding Station",
        #     "Atog",
        #     "Arcbound Ravager",
        #     "Time Sieve",
        #     "Abundance",
        #     "Emry, Lurker of the Loch",
        #     "Shield Sphere",
        #     "Phyrexian Walker",
        #     "Ornithopter",
        #     "Memnite",
        #     "Training Grounds",
        #     "Biomancer's Familiar",
        #     "Agatha of the Vile Cauldron",
        #     "Kiora's Follower",
        #     "Forensic Researcher",
        #     "Luminous Broodmoth",
        #     "Sakashima of a Thousand Faces",
        #     "Phyrexian Metamorph",
        #     "Sakashima's Student",
        #     "Clever Impersonator",
        #     "Encroaching Mycosynth",
        #     "Biotransference",
        #     "Cauldron of Souls",
        #     "Dross Scorpion",
        #     "Arsenal Thresher",
        #     "Mikaeus, the Unhallowed",
        #     "Lesser Masticore",
        #     "Wayta, Trainer Prodigy",
        #     "Bellowing Aegisaur",
        #     "Cacophodon",
        #     "Temple Altisaur",
        #     "Spark Double",
        #     "Sakashima the Impostor",
        #     "Quicksilver Gargantuan",
        #     "Progenitor Mimic",
        #     "Moritte of the Frost",
        #     "Mirror Image",
        #     "Vesuvan Shapeshifter",
        #     "Vesuvan Doppelganger",
        #     "Synth Infiltrator",
        #     "Pirated Copy",
        #     "Mercurial Pretender",
        #     "Glasspool Mimic // Glasspool Shore",
        #     "Flesh Duplicate",
        #     "Auton Soldier",
        #     "Vizier of Many Faces",
        #     "Undercover Operative",
        #     "Stunt Double",
        #     "Mirrorhall Mimic // Ghastly Mimicry",
        #     "Hulking Metamorph",
        #     "Gigantoplasm",
        #     "Evil Twin",
        #     "Dack's Duplicate",
        #     "Clone",
        #     "Altered Ego",
        #     "Deeproot Pilgrimage",
        #     "Captain Storm, Cosmium Raider",
        #     "The Master, Formed Anew",
        #     "Adarkar Valkyrie",
        #     "Thassa's Oracle",
        #     "Illusionist's Bracers",
        #     "Lightning Storm",
        #     "Stormchaser Drake",
        #     "Wheel of Sun and Moon",
        #     "Mirror-Mad Phantasm",
        #     "Chronomantic Escape",
        #     "Sphinx of the Second Sun",
        #     "Hoard Robber",
        #     "Judge of Currents",
        #     "Diligent Excavator",
        # ],
    )
    parser.add_argument(
        "--cuts",
        type=str, 
        nargs="+",
        default=[],
    )

    return parser

def main(config):
    pp.pprint(config)

    with open(config["file"], "r") as json_file:
        data = json.load(json_file)
    print("Data loaded successfully:")
    print(len(data['variants']))

    sample = data['variants'][0]
    pp.pprint(sample)

    card_graph = {}
    combo_graph = {}

    for i, combo in enumerate(tqdm(data['variants'])):
        if len(combo['uses']) > 1:
            for card in combo['uses']:
                cardname = card['card']['name']
                if cardname not in card_graph:
                    card_graph[cardname] = []
                if i not in combo_graph:
                    combo_graph[i] = []
                card_graph[cardname].append(i)
                combo_graph[i].append(cardname)

    if config["cards"]:
        to_prune = [card for card in card_graph if card not in config["cards"]]
        for card in to_prune:
            card_graph, combo_graph = prune(card, card_graph, combo_graph)


    connections_sorted_cards = sorted(card_graph.keys(), key=lambda k: len(get_connections(k, card_graph, combo_graph)))
    for card in connections_sorted_cards:
        if len(card_graph) < 10000:
            break
        if card in card_graph:
            card_graph, combo_graph = prune(card, card_graph, combo_graph)

    remaining_count = len(card_graph)

    while len(card_graph) > 30:
        if len(card_graph) < remaining_count:
            remaining_count =- 100
        print(f"remaining cards: {len(card_graph)} (ct {remaining_count})")
            
        connections_sorted_cards = sorted(card_graph.keys(), key=lambda k: len(get_connections(k, card_graph, combo_graph)))
        card = connections_sorted_cards[0]
        card_graph, combo_graph = prune(card, card_graph, combo_graph)
    
    for card in card_graph:
        print(f"{card}: {len(get_connections(card, card_graph, combo_graph))}")

    for combo in combo_graph:
        print(f"{combo}: {combo_graph[combo]}")

def get_connections(card, card_graph, combo_graph):
    connections = set()
    for combo in card_graph[card]:
        for card in combo_graph[combo]:
            connections.add(card)
    combos_len = len(card_graph[card])
    cards_len = len(connections)
    return cards_len, combos_len
            

def prune(card_to_prune, card_graph, combo_graph):
    if card_to_prune in card_graph:
        combos = [combo for combo in card_graph[card_to_prune]]
        for combo in combos:
            for card in combo_graph[combo]:
                card_graph[card].remove(combo)
                if len(card_graph[card]) == 0:
                    card_graph.pop(card)
            combo_graph.pop(combo)
    
    if card_to_prune in card_graph:
        raise Exception(f"card {card_to_prune} still in card_graph")

    return card_graph, combo_graph
        

if __name__ == "__main__":
    parser = get_parser()
    args = parser.parse_args()
    config = vars(args)
    main(config)
    print("done")