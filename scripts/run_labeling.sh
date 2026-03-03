#!/usr/bin/env bash
# Run the autocard LLM labeling pipeline.
# Resume-safe: re-run to pick up where you left off.
#
# Usage:
#   ./scripts/run_labeling.sh                           # defaults: batch=5, concurrency=4, gemma3:12b
#   ./scripts/run_labeling.sh 3                         # batch_size=3
#   ./scripts/run_labeling.sh 5 4 llama3:8b             # batch=5, concurrency=4, custom model
#
# Note: batch_size max ~5 due to Ollama JSON schema grammar limits with the
# expanded category schema. Larger batches will fail and fall back to single-card.

set -euo pipefail
cd "$(dirname "$0")/.."

BATCH_SIZE="${1:-5}"
CONCURRENCY="${2:-4}"
MODEL="${3:-gemma3:12b}"
CLI=".venv/bin/python -u -m auto_goldfish.autocard.cli"

CARDS_FILE="src/auto_goldfish/autocard/data/top_cards.json"

# Step 1: Fetch cards if not already cached
if [ ! -f "$CARDS_FILE" ]; then
    echo "top_cards.json not found, fetching from Scryfall..."
    $CLI fetch \
        --tags otag:draw otag:card-advantage otag:ramp \
        --query "-t:land f:commander"
fi

# Step 2: Label unlabeled cards
$CLI label \
    --model "$MODEL" \
    --batch-size "$BATCH_SIZE" \
    --concurrency "$CONCURRENCY" \
    --resume
