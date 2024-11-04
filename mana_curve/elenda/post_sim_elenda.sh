#!/bin/bash
cd ..
python simulator.py \
--deck_file elenda/top_decklists/deck_1.json \
--simulations 1000 \
--turns 9 \
--mana_threshold 7 \
--verbose \