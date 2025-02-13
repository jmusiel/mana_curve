#!/bin/bash
cd ..
python simulator.py \
--deck_file elenda/top_decklists/deck_6.json \
--simulations 10000 \
--turns 9 \
--mana_threshold 7 \
--verbose \