#!/bin/bash
cd ..
python simulator.py \
--deck_file kess/top_decklists/deck_9.json \
--simulations 10000 \
--turns 9 \
--mana_threshold 7 \
--verbose \