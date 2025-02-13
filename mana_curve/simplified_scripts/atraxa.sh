#!/bin/bash
python /Users/jmusiel/vscode_workspace/personal_projects/mana_curve/mana_curve/simplified.py \
--num_lands 35 \
--land_range 7 \
--step_size 1 \
--num_simulations 10000 \
--num_turns 10 \
--mulligan_max_lands 3 \
--mulligan_max_lands 5 \
--curve_after 1 \
--commanders 4 \
--num_cards 100 \
--mana_curve 0 4 7 18 17 9 5 2 1 \
--verbose \


# --mana_curve 0 4 7 18 17 9 5 2 1 \ # base (37 lands) 