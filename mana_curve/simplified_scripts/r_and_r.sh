#!/bin/bash
python /Users/jmusiel/vscode_workspace/personal_projects/mana_curve/mana_curve/simplified.py \
--num_lands 38 \
--land_range 4 \
--step_size 1 \
--num_simulations 100000 \
--num_turns 10 \
--mulligan_max_lands 3 \
--mulligan_max_lands 5 \
--curve_after 2 \
--commanders 3 5 \
--num_cards 100 \
--mana_curve 0 6 13 19 17 4 2 1 0 \
--verbose \

# --mana_curve 0 6 13 19 16 4 2 1 0 \ # with farseek and steve and harmonize land cuts (39 lands) -> optimal according to simulations
# --mana_curve 0 6 13 19 17 4 2 1 0 \ # with farseek and steve land cuts (38 lands) (excludes MDFCs)
# --mana_curve 0 7 15 21 19 4 3 2 0 \ # base R&R connection (not excluding MDFCs)