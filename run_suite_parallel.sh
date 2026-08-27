#!/bin/bash
set -e

# Usage: ./run_suite_parallel.sh [harness:model] [harness:model] ...
# Example: ./run_suite_parallel.sh antigravity:gemini-3.7-flash pi-agent:x-preview-f-free

if [ "$#" -eq 0 ]; then
    echo "Usage: $0 <harness:model> [harness:model] ..."
    echo "Example: $0 antigravity:gemini-3.7-flash pi-agent:x-preview-f-free"
    exit 1
fi

# We can run 4 trials in parallel per harness. If you pass 4 harnesses, that's 16 parallel sandbox containers.
JOBS_PER_HARNESS="${JOBS_PER_HARNESS:-4}"
TRIALS="${TRIALS:-3}"

echo "🚀 Starting full suite parallel benchmark execution..."

for arg in "$@"; do
    IFS=':' read -r harness model <<< "$arg"
    
    echo "🔍 Verifying configuration: Harness=$harness | Model=$model"
    if ! python3 -m bench verify --harness "$harness" --model "$model"; then
        echo "❌ Aborting benchmark due to verification failure for $harness:$model"
        exit 1
    fi
    
    echo "📦 Dispatching suite for: Harness=$harness | Model=$model"
    # Run all tasks natively in parallel using the python runner's thread pool, 
    # and background this entire process to run alongside other harnesses.
    python3 -m bench run \
        --task-glob "tasks/**/*.md" \
        --harness "$harness" \
        --model "$model" \
        --trials "$TRIALS" \
        --jobs "$JOBS_PER_HARNESS" &
done

echo "⏳ All harness suites dispatched. Waiting for all sandboxes to finish..."
wait

echo "📊 All runs finished. Generating aggregate report..."
python3 -m bench report
echo "✅ Done! Run 'cat results/report.md' to view the final breakdown."
