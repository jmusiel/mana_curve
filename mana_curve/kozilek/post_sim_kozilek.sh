#!/bin/bash
cd ..
python simulator.py \
--deck_file kozilek/top_decklists/deck_1.json \
--simulations 10000 \
--turns 9 \
--mana_threshold 7 \
--verbose \