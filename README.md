# llm-benchyyyy

LLM benchmark aggregation, model catalog intelligence, free model ranking, and OpenRouter stealth model detection suite.

## Tools & Checkers

The project provides four primary CLI tools under `checkers/`:

### 1. `bcheck` — Multi-Source Benchmark Aggregator
Aggregates benchmark evaluations from **Artificial Analysis (Quality Index)**, **LiveBench (Reasoning/Coding/Math/Data)**, **LMArena (Coding Arena ELO)**, and **ARC-AGI-1 / ARC-AGI-2**:
```bash
# Run against cached snapshots
python3 -m checkers.llm_benchmark_aggregator

# Or using installed CLI entrypoint
bcheck

# Fetch fresh live data and update snapshots
bcheck --fetch
```

### 2. `ocheck` — OpenCode Go Cost-Benefit Analyzer
Analyzes OpenCode Go provider model pricing, token rates, and intelligence-to-cost tradeoffs:
```bash
# Analyze catalog and display CLI comparison table
ocheck

# Generate standalone HTML visualization report
ocheck --html docs/reports/ocgo_cost_benefit.html
```

### 3. `fcheck` — Free Model Ranker
Discovers and ranks zero-cost and free-tier models across OpenCode Zen/Go, Cline, and OpenRouter:
```bash
# Rank free models
fcheck

# Render HTML report
fcheck --html docs/reports/free_models.html
```

### 4. `scheck` — Stealth Model Detector
Detects and tracks stealth/preview models (`stealth/*` namespace) on OpenRouter:
```bash
# Inspect stealth models
scheck

# Render HTML report
scheck --html docs/reports/stealth_models.html
```

## Repository Structure

- `checkers/` — Core Python analysis tools and test suite:
  - `benchmark_common.py` — Shared utilities, variant conflict matchers, Pareto frontiers, atomic JSON storage.
  - `llm_benchmark_aggregator.py` — Benchmark consolidation (`bcheck`).
  - `opencode_cost_benefit_analyzer.py` — OpenCode Go cost-benefit analyzer (`ocheck`).
  - `free_model_ranker.py` — Free model ranker (`fcheck`).
  - `stealth_model_detector.py` — Stealth model tracker (`scheck`).
  - `test_*.py` — Unit tests.
- `docs/` — Datasets, models index, and generated reports:
  - `docs/data/` — Consolidated JSON databases (`benchmarks.json`, `ocgo_live.json`, `free_models.json`, `stealth_models.json`).
  - `docs/data/raw/` — Timestamped snapshot evaluations from LiveBench, LMArena, Artificial Analysis, ARC-AGI, and OpenRouter.
  - `docs/reports/` — Exported HTML, JSON, and Markdown reports.
  - `docs/models.md` — Reference documentation on models.
- `reviews/` — Architectural reviews and audit reports.

## Installation & Testing

No third-party dependencies required (pure Python 3.11+ standard library):

```bash
# Optional editable install for CLI shortcuts
python3 -m pip install -e .

# Run the full test suite
python3 -m unittest discover -s checkers -p "test_*.py"
```
