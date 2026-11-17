# llm-benchyyyy

LLM benchmark aggregation, distinct thinking-level model intelligence, empirical $/task routing, free model ranking, and OpenRouter stealth model detection suite.

## Tools & Checkers

The project provides nine Python CLI entrypoints (`pyproject.toml`) under `checkers/` plus the `checkerz` Rust TUI:

### 1. `bcheck` — 7-Authority Benchmark & Task-Role Aggregator
Aggregates benchmark evaluations across **7 upstream authorities**, preserves **distinct thinking/effort levels** (`minimal`, `low`, `medium`, `high`, `xhigh`, `max`, `non-reasoning`) as separate rows, and computes **5 James-Stein shrunk z-score capability/economics axes** (`SHRINKAGE_LAMBDA = 0.20`) plus **4 declarative task-role scores**:

| Authority | Signal Legs Used | Snapshot / Endpoint |
| :--- | :--- | :--- |
| **CursorBench 4.0** | Score %, empirical $/task, tokens, steps | `cursor.com/evals` (`docs/data/raw/cursor_evals_*.json`) |
| **FrontierCode 2.0** | Score %, correctness %, empirical $/task, tokens | `cognition.com/frontiercode` (`docs/data/raw/frontiercode_*.json`) |
| **FrontierSWE** | Overall %, implementation %, perf %, research % | `frontierswe.com` (`docs/data/raw/frontierswe_*.html`) |
| **Artificial Analysis v5** | Intelligence Index, HLE, CritPt, TB-4, IFBench, LCR, Omniscience Non-Hallucination, GPQA, SciCode | `artificialanalysis.ai` (`docs/data/raw/artificial_analysis_*.html`) |
| **Vals Index** | Overall %, Vibe-Code %, TerminalBench % | `vals.ai` (`docs/data/raw/vals_index_*.html`) |
| **LMArena (HF)** | Overall Elo, Coding Elo, WebDev Elo | `lmarena-ai/arena-leaderboard-snapshot` (`docs/data/raw/lmarena_hf_*.json`) |
| **LiveBench** | Overall %, Agentic Coding %, Reasoning % | `livebench.ai` (`docs/data/raw/livebench_*.csv`) |

#### 5 Shrunk Axes & 4 Task Roles
- **5 Orthogonal Axes** (`0–99.9`, shrunk toward `0` when fewer legs are observed so thin single-source rows cannot outrank multi-authority models):
  - `reasoning` — HLE, CritPt, AA Intelligence, LiveBench Reasoning/Overall
  - `coding` — CursorBench 4.0, FrontierCode 2.0, FrontierSWE, AA TerminalBench-4, Vals Coding/Terminal, LMArena Coding, LiveBench Coding
  - `design` — LMArena WebDev Elo, AA IFBench, Vals Vibe-Code, LMArena Overall Elo
  - `research` — AA Omniscience Non-Hallucination, AA Long-Context Reasoning (LCR), FrontierSWE Research, AA GPQA/SciCode, Vals Overall
  - `economics` — Empirical geometric-mean `$/task` across CursorBench, FrontierCode 2.0, and AA (fallback: blended prompt/output cost) + generation throughput (`tok/s`)
- **4 Task-Role Scores** (`roles.*`):
  - `architecture` (`0.45 reasoning + 0.25 coding + 0.20 research + 0.10 economics`)
  - `software_dev` (`0.50 coding + 0.20 reasoning + 0.20 economics + 0.10 design`)
  - `design` (`0.50 design + 0.25 coding + 0.15 reasoning + 0.10 economics`)
  - `research` (`0.50 research + 0.30 reasoning + 0.10 coding + 0.10 economics`)

Rows carry a `Conf [k/7]` badge (`*` = single-source). Python (`checkers/benchmark_common.py`) is the **single scoring authority**; `docs/data/benchmarks.json` stores precomputed `effort`, `axes`, `roles`, `best_role`, `empirical_cost`, and `effective_cost` consumed directly by `checkerz`.

```bash
# Run against cached snapshots (offline by default)
bcheck
bcheck --pool agy --one-shot
bcheck --sort arch   # sort: composite, arch, dev, design, research, cursor, fc2, fswe, empirical_cost, speed

# Fetch fresh live data across all 7 authorities and update baseline
bcheck --fetch

# Regenerate baseline + Markdown & HTML reports offline
bcheck --save-baseline --md docs/reports/benchmarks.md --html docs/reports/benchmarks.html
```

### 1b. `bsync` — Automated Daily Sync Daemon
Runs scheduled 08:00 background syncs against all upstream benchmark and pricing feeds (with fail-closed minimum byte & parsed-row gates), prunes historical raw cache, and refreshes all downstream catalogs:
```bash
bsync --status     # Inspect cache freshness across all 14 raw feeds & 6 JSON outputs
bsync --sync-now   # One-shot sync against all upstream sources
bsync              # Run continuous 08:00 daily sync daemon
```

### 2. `ocheck` — OpenCode Go Cost-Benefit Analyzer
Analyzes OpenCode Go provider model pricing, token rates, and intelligence-to-cost tradeoffs (offline cache by default):
```bash
ocheck
ocheck --limits    # Show multi-window pooled limits & per-model allowance
ocheck --fetch     # Live-fetch Go docs + API + shared snapshots
```

### 2b. `ccheck` — Command Code GOAT Cost-Benefit Analyzer
Checks the GOAT plan catalog (`commandcode.ai/docs/plans/goat`) — per-model monthly credits (`$20–$70`), pooled caps, and docs-published request counts:
```bash
ccheck
ccheck --fetch
```

### 3. `fcheck` & `scheck` — Free Model Ranker & Stealth Model Detector
```bash
fcheck --check     # Rank zero-cost & free-tier models across OpenCode Zen/Go, Cline, OpenRouter
scheck --check     # Detect and track stealth/preview models on OpenRouter
```

### 4. `fntcheck`, `ocgo`, `ccgo` — Frontier Tracker & Quota Monitors
- `fntcheck` (`checkers/frontier_model_tracker.py`) — Tracks OpenAI, Claude, and Gemini benchmark scores and API pricing (`--check`, `--json`).
- `ocgo` (`checkers/ocgo.py`) — Live OpenCode Go quota and usage monitor (`-s`, `-m`, `-j`).
- `ccgo` (`checkers/ccgo.py`) — Live Command Code quota and usage monitor (`-s`, `-j`).

### 5. `checkerz` — Interactive 7-Authority & 4-Role TUI (Rust/ratatui)
Fast offline terminal UI over `docs/data/benchmarks.json` consuming precomputed 5-axis & 4-role scores:
```bash
cargo run --manifest-path checkerz/Cargo.toml
cargo run --manifest-path checkerz/Cargo.toml -- --pool agy --sort arch
```

## Repository Structure

- `checkers/` — Core Python analysis tools:
  - `benchmark_common.py` — Single scoring authority (`score_five_axes_and_roles`), 7-authority parsers (`parse_aa`, `parse_vals_index`, `parse_frontiercode`, `parse_frontierswe`, `parse_cursor_evals`, LMArena HF), effort-tier normalization, Pareto frontiers, atomic I/O.
  - `llm_benchmark_aggregator.py` — 7-authority catalog builder, effort-strict matcher & exporter (`bcheck`).
  - `benchmark_sync_daemon.py` — Automated daily sync daemon (`bsync`).
  - `opencode_cost_benefit_analyzer.py` / `commandcode_cost_benefit_analyzer.py` — Subscription ROI analyzers (`ocheck`, `ccheck`).
  - `frontier_model_tracker.py` / `free_model_ranker.py` / `stealth_model_detector.py` — Specialized trackers (`fntcheck`, `fcheck`, `scheck`).
  - `ocgo.py` / `ccgo.py` — Live quota and usage monitors.
- `checkerz/` — Rust `ratatui` TUI (`cargo test/run --manifest-path checkerz/Cargo.toml`).
- `docs/data/` — Consolidated JSON databases (`benchmarks.json`, `ocgo_live.json`, `cc_live.json`, `free_models.json`, `stealth_models.json`, `frontier_models.json`) and `raw/` snapshots.
- `docs/reports/` — Exported HTML and Markdown reports.
