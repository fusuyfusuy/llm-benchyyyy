#!/bin/bash
set -e
echo "Starting Agy benchmarks..."
python3 -m bench run --task tasks/agentic/ci-pipeline-recovery.md --harness antigravity --model gemini-3.7-flash-high --trials 3
python3 -m bench run --task tasks/coding/security-idor-vulnerability.md --harness antigravity --model gemini-3.7-flash-high --trials 3
python3 -m bench run --task tasks/reasoning/long-horizon-context-puzzle.md --harness antigravity --model gemini-3.7-flash-high --trials 3

echo "Starting Pi benchmarks..."
python3 -m bench run --task tasks/agentic/ci-pipeline-recovery.md --harness pi-agent --model x-preview-f-free --trials 3
python3 -m bench run --task tasks/coding/security-idor-vulnerability.md --harness pi-agent --model x-preview-f-free --trials 3
python3 -m bench run --task tasks/reasoning/long-horizon-context-puzzle.md --harness pi-agent --model x-preview-f-free --trials 3

echo "Generating report..."
python3 -m bench report > benchmark_output_summary.txt
echo "Done!"
