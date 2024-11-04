#!/bin/bash
cd ..
python sweep_over_template.py \
--template kozilek/kozilek_template.json \
--deck_name kozilek \
--samples 1000 \
--simulations 1000 \
--num_turns 9 \

