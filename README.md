# llm-benchyyyy

LLM benchmark aggregation, model catalog intelligence, free model ranking, and OpenRouter stealth model detection suite.

## Tools & Checkers

The project provides four primary CLI tools under `checkers/`:

### 1. `bcheck` — Multi-Source Benchmark Aggregator
Aggregates benchmark evaluations from **Artificial Analysis (Quality Index)**, **LiveBench (Reasoning/Coding/Math/Data)**, and **LMArena (Coding Arena ELO)**:
```bash
# Run against cached snapshots
python3 -m checkers.llm_benchmark_aggregator

# Or using installed CLI entrypoint
bcheck

# Fetch fresh live data and update snapshots
bcheck --fetch
```

### 1b. `bsync` — Automated Daily Sync Daemon
Runs scheduled background syncs against upstream benchmark and documentation feeds, prunes historical raw cache, and refreshes all downstream catalogs:
```bash
# Run one-shot sync against all upstream sources
bsync --now

# Start daemon scheduled at 08:00 daily
bsync
```

### 2. `ocheck` — OpenCode Go Cost-Benefit Analyzer
Analyzes OpenCode Go provider model pricing, token rates, and intelligence-to-cost tradeoffs:
```bash
# Analyze catalog and display CLI comparison table
ocheck

# Generate standalone HTML visualization report
ocheck --html docs/reports/ocgo_cost_benefit.html
```

### 2b. `ccheck` — Command Code GOAT Cost-Benefit Analyzer
Checks the GOAT plan catalog (https://commandcode.ai/docs/plans/goat#usage-limits) against the same benchmark suite — per-model monthly credits ($20–$70), pooled caps ($14/5h · $35/wk · $70/mo), and docs-published request counts. Offline by default on `docs/data/raw/cc_goat_docs_*.html`.
```bash
ccheck
ccheck --fetch   # live-fetch GOAT docs + shared AA/LMArena/OpenRouter snapshots
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

### 5. `checkerz` — Interactive Capability TUI (Rust/ratatui)
Offline viewer over `docs/data/benchmarks.json` (refresh with `bcheck --fetch`):
```bash
cargo run --manifest-path checkerz/Cargo.toml
cargo run --manifest-path checkerz/Cargo.toml -- --all -n 30
```

## Repository Structure

- `checkers/` — Core Python analysis tools and test suite:
  - `benchmark_common.py` — Shared utilities, variant conflict matchers, Pareto frontiers, atomic JSON storage.
  - `llm_benchmark_aggregator.py` — Benchmark consolidation (`bcheck`).
  - `benchmark_sync_daemon.py` — Automated daily sync daemon (`bsync`).
  - `opencode_cost_benefit_analyzer.py` — OpenCode Go cost-benefit analyzer (`ocheck`).
  - `commandcode_cost_benefit_analyzer.py` — Command Code GOAT cost-benefit analyzer (`ccheck`).
  - `frontier_model_tracker.py` — Frontier model benchmark & pricing tracker (`fntcheck`).
  - `free_model_ranker.py` — Free model ranker (`fcheck`).
  - `stealth_model_detector.py` — Stealth model tracker (`scheck`).
  - `ocgo.py` / `ccgo.py` — Live quota and usage monitors (`ocgo`, `ccgo`).
- `checkerz/` — Rust ratatui TUI (`cargo test/run --manifest-path checkerz/Cargo.toml`).
- `docs/` — Datasets, models index, and generated reports:
  - `docs/data/` — Consolidated JSON databases (`benchmarks.json`, `ocgo_live.json`, `cc_live.json`, `free_models.json`, `stealth_models.json`, `frontier_models.json`).
  - `docs/data/raw/` — Timestamped snapshot evaluations from LiveBench, LMArena, Artificial Analysis, and OpenRouter (auto-pruned rolling window).
  - `docs/reports/` — Exported HTML, JSON, and Markdown reports.
  - `docs/models.md` — Reference documentation on models.

## Installation

Zero external runtime dependencies (pure Python 3.11+ standard library):

```bash
# Verify checkers offline check
python3 -m checkers.llm_benchmark_aggregator --check

# Run the Rust TUI
cargo run --manifest-path checkerz/Cargo.toml
```
