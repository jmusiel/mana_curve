from mana_curve.decklist_model.decklist import get_deckpath
import numpy as np
from collections import defaultdict, Counter

def save_game_records(deck_name, game_records, decklist, commanders, land_count, sims):
    deckpath = get_deckpath(deck_name).replace(".json", f"_{land_count}_lands_record.txt")
    with open(deckpath, 'w') as f:
        f.write(f"Decklist: {deck_name}\n")
        f.write(f"Commanders: {', '.join(commanders)}\n")
        f.write(f"Land Count: {land_count}\n")
        f.write(f"Simulations: {sims}\n")
        f.write("\n")

        f.write(f"Decklist:\n")
        for card in decklist:
            f.write(f"{card}\n")
        f.write("\n")

        f.write(f"Game Records:\n")

        for quintile_name, record in game_records.items():
            f.write(f"=======================================================================\n")
            f.write(f"========================== {quintile_name} games ==========================\n")
            f.write(f"=======================================================================\n")
            f.write(f"num games in {quintile_name}: {len(record['mana'])}\n")
            f.write("\n")

            card_stats = {}
            for key, value in record.items():
                if not key == "logs":
                    if key in ["per turn effects", "cast triggers", "starting hand", "played cards"]:
                        superlist = []
                        for sublist in value:
                            superlist.extend(sublist)
                        card_stats[key] = Counter(superlist).most_common(10)
                    else:
                        f.write(f"{key}: {np.mean(value)}\n")
            f.write("\n")
            f.write("\n")
            for key, value in card_stats.items():
                f.write(f"most common {key}:\n")
                for card, count in value:
                    f.write(f"\t{count} {card}\n")
            f.write("\n")
            f.write("\n")
            for i, log in enumerate(record["logs"]):
                f.write(f"---------------- {quintile_name} example game #{i} ----------------\n")
                f.writelines(line + '\n' for line in log)
                f.write("\n")
                f.write("\n")
            f.write("\n")
            f.write("\n")
            f.write("\n")
            


        
