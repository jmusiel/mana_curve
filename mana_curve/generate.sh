#!/bin/bash

python deck_generator.py \
    --lands 38 \
    --mana-rocks 4 \
    --land-ramp 6 \
    --immediate-draw 15 \
    --per-turn-draw 3 \
    --on-cast-draw 3 \
    --curve 3.5 \
    --output deck.json \