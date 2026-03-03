#!/usr/bin/env bash
# Run the autocard LLM labeling pipeline.
# Resume-safe: re-run to pick up where you left off.
#
# Usage:
#   ./scripts/run_labeling.sh                    # defaults: batch=10, concurrency=4, gemma3:12b
#   ./scripts/run_labeling.sh 20                 # batch_size=20
#   ./scripts/run_labeling.sh 10 4 llama3:8b     # batch=10, concurrency=4, custom model

set -euo pipefail
cd "$(dirname "$0")/.."

BATCH_SIZE="${1:-10}"
CONCURRENCY="${2:-4}"
MODEL="${3:-gemma3:12b}"

.venv/bin/python -c "
from auto_goldfish.autocard.scryfall import load_cards
from auto_goldfish.autocard.coverage import analyze_coverage
from auto_goldfish.autocard.labeler import label_cards

cards = load_cards()
report = analyze_coverage(cards)
unlabeled = [c for c in cards if c.name in report.unlabeled_names]
print(f'Labeling {len(unlabeled)} unlabeled cards (model=${MODEL}, batch_size=${BATCH_SIZE}, concurrency=${CONCURRENCY})...')
results = label_cards(unlabeled, model='${MODEL}', resume=True, concurrency=${CONCURRENCY}, batch_size=${BATCH_SIZE})
print(f'Done! {len(results)} cards labeled total.')
"
