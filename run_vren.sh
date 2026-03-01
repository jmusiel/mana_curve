#!/usr/bin/env bash
# Run mana curve analysis for the Vren deck.
# Usage: ./run_vren.sh [extra args...]
#
# Examples:
#   ./run_vren.sh                        # default analysis
#   ./run_vren.sh --mulligan curve_aware  # use curve-aware mulligan
#   ./run_vren.sh --sims 50000           # more simulations

set -euo pipefail

DECK_NAME="vren"
DECK_URL="https://archidekt.com/decks/19226307/vrens_murine_marauders"
TURNS=10
SIMS=10000
MIN_LANDS=34
MAX_LANDS=40
SEED=42
WORKERS=0  # use all CPUs

python -m auto_goldfish.cli.main \
    --deck_name "$DECK_NAME" \
    --deck_url "$DECK_URL" \
    --turns "$TURNS" \
    --sims "$SIMS" \
    --min_lands "$MIN_LANDS" \
    --max_lands "$MAX_LANDS" \
    --seed "$SEED" \
    --workers "$WORKERS" \
    --mulligan default \
    "$@"
