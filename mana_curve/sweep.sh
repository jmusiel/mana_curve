#!/bin/bash

python sweep_over_template.py \
--template elenda/elenda_template.json \
--deck_name elenda \
--samples 1000 \
--simulations 500 \
--num_turns 8 \
--force_commander \
