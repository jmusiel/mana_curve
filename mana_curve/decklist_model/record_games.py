from mana_curve.decklist_model.decklist import get_deckpath
import numpy as np
from collections import defaultdict, Counter
import matplotlib.pyplot as plt

def save_game_records(deck_name, game_records, decklist, commanders, land_count, sims, card_cast_turn_list, cmc_list):
    cast_turn_mean = []
    cast_turn_std = []
    cast_turn_median = []
    cast_turn_q1 = []
    cast_turn_q3 = []
    for cast_turn in card_cast_turn_list:
        if len(cast_turn) == 0:
            cast_turn_mean.append(np.nan)
            cast_turn_std.append(np.nan)
            cast_turn_median.append(np.nan)
            cast_turn_q1.append(np.nan)
            cast_turn_q3.append(np.nan)
        else:
            cast_turn_mean.append(np.mean(cast_turn))
            cast_turn_std.append(np.std(cast_turn))
            cast_turn_median.append(np.median(cast_turn))
            cast_turn_q1.append(np.percentile(cast_turn, 25))
            cast_turn_q3.append(np.percentile(cast_turn, 75))
    lower_error = [median - q1 for median, q1 in zip(cast_turn_median, cast_turn_q1)]
    upper_error = [q3 - median for median, q3 in zip(cast_turn_median, cast_turn_q3)]

    fig, ax = plt.subplots()
    # ax.errorbar(cmc_list, cast_turn_median, yerr=[lower_error, upper_error], fmt='o')
    ax.errorbar(cmc_list, cast_turn_mean, yerr=cast_turn_std, fmt='o')
    ax.set_xlabel("Mana Value")
    ax.set_ylabel("Cast Turn")
    ax.set_title(f"Card Cast Turn {deck_name} with {land_count} lands")
    fig.savefig(get_deckpath(deck_name).replace(".json", f"_mana_curve_{land_count}_lands.png"))
    plt.close(fig)

    deckpath = get_deckpath(deck_name).replace(".json", f"_record_{land_count}_lands.txt")
    with open(deckpath, 'w') as f:
        f.write(f"Decklist: {deck_name}\n")
        f.write(f"Commanders: {', '.join(commanders)}\n")
        f.write(f"Land Count: {land_count}\n")
        f.write(f"Simulations: {sims}\n")
        f.write("\n")

        f.write(f"Decklist:\n")
        f.write(f"Name | [class] | (cmc) | (cast turn)\n")
        for card, cmc, ct in zip(decklist, cmc_list, cast_turn_mean):
            f.write(f"{card.name} [{card.card_class}] ({cmc}) ({ct})\n")
        f.write("\n")

        f.write(f"Game Records:\n")

        for quantile, record in game_records.items():
            f.write(f"=======================================================================\n")
            f.write(f"========================== {quantile} games ==========================\n")
            f.write(f"=======================================================================\n")
            f.write(f"num games in {quantile}: {len(record['mana'])}\n")
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

        f.write("\n")
        f.write("\n")

        for quantile, record in game_records.items():
            f.write(f"=======================================================================\n")
            f.write(f"========================== {quantile} example games ===================\n")
            f.write(f"=======================================================================\n")
            for i, log in enumerate(record["logs"]):
                f.write(f"---------------- {quantile} example game #{i} ----------------\n")
                f.writelines(line + '\n' for line in log)
                f.write("\n")
                f.write("\n")
            f.write("\n")
            f.write("\n")
            f.write("\n")
            


        
