#!/bin/bash
cd ..
python simulator.py \
--deck_file kess/top_decklists/deck_1.json \
--simulations 1000 \
--turns 9 \
--mana_threshold 7 \
--verbose \