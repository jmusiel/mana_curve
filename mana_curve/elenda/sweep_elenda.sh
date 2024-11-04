#!/bin/bash
cd ..
python sweep_over_template.py \
--template elenda/elenda_template.json \
--deck_name elenda \
--samples 1000 \
--simulations 1000 \
--num_turns 8 \
--mana_threshold 7 \
--force_commander \
