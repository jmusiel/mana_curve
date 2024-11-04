#!/bin/bash
cd ..
python sweep_over_template.py \
--template kess/kess_template.json \
--deck_name kess \
--samples 1000 \
--simulations 1000 \
--num_turns 8 \
--mana_threshold 7 \
--force_commander \

