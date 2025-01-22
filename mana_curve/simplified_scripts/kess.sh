#!/bin/bash
python /Users/jmusiel/vscode_workspace/personal_projects/mana_curve/mana_curve/simplified.py \
--num_lands 34 \
--land_range 10 \
--step_size 1 \
--num_simulations 10000 \
--num_turns 10 \
--mulligan_max_lands 3 \
--mulligan_max_lands 5 \
--mulligan_at_least_one_spell 1 \
--curve_after 1 \
--commanders 4 \
--commander_effect kess \
--num_cards 100 \
--mana_curve 1 12 11 17 11 5 4 2 0 \
--verbose \

# --mana_curve 1 12 11 17 11 5 4 2 0 \ # (37 lands, signets cut, prismari and maestro) (MDFCs excluded) (cabal=0)
# --mana_curve 1 12 13 15 11 5 4 2 0 \ # (37 lands, signets cut) (MDFCs excluded) (cabal=0)
# --mana_curve 1 12 15 15 11 5 4 2 0 \ # base (35 lands) (MDFCs excluded) (cabal=0)