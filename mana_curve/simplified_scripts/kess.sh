#!/bin/bash
python /Users/jmusiel/vscode_workspace/personal_projects/mana_curve/mana_curve/simplified.py \
--num_lands 36 \
--land_range 7 \
--step_size 1 \
--num_simulations 100000 \
--num_turns 10 \
--mulligan_max_lands 3 \
--mulligan_max_lands 5 \
--curve_after 1 \
--commanders 4 \
--num_cards 100 \
--mana_curve 1 13 12 16 11 4 5 1 0 \
--verbose \
--commander_effect kess \
# --mulligan_at_least_one_spell 1 \

# --mana_curve 1 13 12 16 11 4 5 1 0 \ # (37 lands, excluding cabal, including lorien) (MDFCs excluded) (cabal=0, lorien=land, added bombardment)
# --mana_curve 1 13 11 17 11 4 4 2 0 \ # (37 lands, signets cut, prismari and maestro) (tor wauki cut for cantrip) (MDFCs excluded) (cabal=0) -> optimal according to simulations
# --mana_curve 1 12 11 17 11 5 4 2 0 \ # (37 lands, signets cut, prismari and maestro) (MDFCs excluded) (cabal=0)
# --mana_curve 1 12 13 15 11 5 4 2 0 \ # (37 lands, signets cut) (MDFCs excluded) (cabal=0)
# --mana_curve 1 12 15 15 11 5 4 2 0 \ # base (35 lands) (MDFCs excluded) (cabal=0)