#!/bin/bash
set -euo pipefail

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
suite_pids=()
suite_names=()
for arg in "$@"; do
    IFS=':' read -r harness model <<< "$arg"
    
    echo "🔍 Verifying configuration: Harness=$harness | Model=$model"
    if ! python3 -m engine verify --harness "$harness" --model "$model"; then
        echo "❌ Aborting benchmark due to verification failure for $harness:$model"
        exit 1
    fi
    
    echo "📦 Dispatching suite for: Harness=$harness | Model=$model"
    # Run all tasks natively in parallel using the python runner's thread pool, 
    # and background this entire process to run alongside other harnesses.
    python3 -m engine run \
        --task-glob "tasks/**/*.md" \
        --harness "$harness" \
        --model "$model" \
        --trials "$TRIALS" \
        --jobs "$JOBS_PER_HARNESS" &
    suite_pids+=("$!")
    suite_names+=("$harness:$model")
done

echo "⏳ All harness suites dispatched. Waiting for all sandboxes to finish..."
# A bare `wait` returns 0 no matter how the children exited — collect the PIDs
# and wait on each one so a failed suite cannot slip past into report generation.
failed=0
for i in "${!suite_pids[@]}"; do
    if ! wait "${suite_pids[$i]}"; then
        echo "❌ Suite failed: ${suite_names[$i]}" >&2
        failed=$((failed + 1))
    fi
done
if [ "$failed" -gt 0 ]; then
    echo "❌ $failed/${#suite_pids[@]} harness suite(s) failed — skipping report; see errors above." >&2
    exit 1
fi

echo "📊 All runs finished. Generating aggregate report..."
python3 -m engine report
echo "✅ Done! Run 'cat results/report.md' to view the final breakdown."
