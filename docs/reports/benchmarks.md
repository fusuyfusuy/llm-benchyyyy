# Consolidated LLM Benchmark & Agentic Cost-Benefit Report (2026-09-09)

Consolidated capability & cost-efficiency benchmark across **LiveBench** (https://livebench.ai), **LMArena / Arena.ai**, **Artificial Analysis**, **AGY Subscription (Gemini)**, **Claude Subscription (Anthropic)**, and **Frontier API Models**.

## 1. Tri-Verified Master Leaderboard (All 3 Benchmarks Verified)
_Showing top 30 of 50 tri-verified models._

| Model | Pool / Tier | Q (Cap) | P(Succ) | Eff. $/M | AVI (Value) | FGI (Gate) | LiveBench (%) | Arena Elo | AA Quality | Raw $/M |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Claude Fable-5-1-max** | `API` (Arena Model) | **98.5** | 96.0% | — | — | 92.6 | 83.8% | 1764 | 53.4 | —/— |
| ⭐ **GPT-6 Astra (xhigh)** | `API` (Upstream API) | **98.3** | 95.9% | $19.62 | **182.6** | 92.3 | 83.0% | 1796 | 52.5 | $10/$50 |
| ⭐ **Claude Fable 5.1 (Adaptive Reasoning, Low Effort, Default Fallback)** | `API` (Upstream API) | **96.5** | 95.0% | $20.16 | **173.9** | 89.4 | 83.8% | 1764 | 47.0 | $10/$50 |
| **Claude Opus 5 (Thinking)** | `CLAUDE` (Flagship Reasoning / Complex Gates) | **95.1** | 94.1% | $10.26 | **210.1** | 86.8 | 80.5% | 1661 | 50.7 | $5/$25 |
| **Claude Fable 5 (High)** | `CLAUDE` (Elite Creative / Agent) | **94.9** | 94.0% | $20.52 | **166.7** | 86.5 | 83.4% | 1628 | 49.7 | $10/$50 |
| ⭐ **Muse Spark 1.3 (Max)** | `API` (Elite Fast Frontier / High TPS) | **94.2** | 93.5% | $0.67 | **654.6** | 85.2 | 82.4% | 1625 | 48.2 | $0.35/$1.5 |
| **GPT-5.6 Sol (Reasoning)** | `FRONTIER` (Frontier Flagship Reasoning) | **93.9** | 93.3% | $4.18 | **289.9** | 84.6 | 81.7% | 1617 | 47.1 | $2/$10 |
| **Kimi K3 (Max)** | `API` (Architecture & Reasoning) | **93.1** | 92.6% | $6.37 | **239.5** | 83.0 | 79.5% | 1674 | 43.8 | $3/$15 |
| **Kimi K3 (NVIDIA NIM)** | `NVIDIA` (Frontier Long-Context Reasoning) | **93.1** | 92.6% | $1.51 | **448.5** | 83.0 | 79.5% | 1674 | 43.8 | $0.80/$3.2 |
| **Grok 4.6 (Reasoning)** | `FRONTIER` (Frontier Agentic Reasoning) | **92.4** | 92.0% | $3.33 | **308.6** | 81.5 | 79.0% | 1624 | 44.4 | $2/$6 |
| **Qwen3.8 Max** | `API` (Tier 1 — High Reasoning) | **91.6** | 91.3% | $3.39 | **300.4** | 79.9 | 79.5% | 1670 | 40.3 | $2/$6 |
| ⭐ **Qwen3.8-Flash-Next** | `API` (Ultra-Fast Reasoning) | **90.9** | 90.6% | $0.14 | **947.8** | 78.4 | 77.3% | 1631 | 42.2 | $0.08/$0.24 |
| **GLM-5.3** | `API` (Tier 1 — Architecture & Spec) | **90.9** | 90.6% | $2.46 | **340.7** | 78.4 | 76.7% | 1613 | 44.9 | $1.4/$4.4 |
| **Gemini 3.7 Flash (Thinking)** | `AGY` (Workhorse / Default) | **90.6** | 90.3% | $0.84 | **547.5** | 77.7 | 79.9% | 1587 | 39.4 | $0.38/$1.88 |
| **GPT-5.6 Terra (Reasoning)** | `FRONTIER` (Frontier High-Capacity) | **90.3** | 90.0% | $3.35 | **292.7** | 77.1 | 78.6% | 1521 | 42.3 | $1.5/$7.5 |
| **Gemini 3.8 Flash** | `AGY` (Next-Gen Workhorse / Agentic Coding) | **90.2** | 89.9% | $0.85 | **539.5** | 76.9 | 77.5% | 1568 | 41.2 | $0.38/$1.88 |
| **Claude Opus 4.8 (Thinking)** | `CLAUDE` (Lead Architecture / Reasoning) | **89.8** | 89.4% | $11.34 | **178.8** | 75.9 | 77.2% | 1540 | 42.0 | $5/$25 |
| **GPT 5.5 (xHigh)** | `FRONTIER` (Frontier Agentic Reasoning) | **89.7** | 89.3% | $12.60 | **172.1** | 75.7 | 80.8% | 1510 | 38.6 | $5/$30 |
| ⭐ **Muse Spark 1.2 (Contributor)** | `API` (Fast Contributor Specialist) | **89.7** | 89.3% | $0.15 | **909.3** | 75.7 | 78.9% | 1534 | 39.8 | $0.10/$0.20 |
| **Claude Opus 4.7 (Thinking)** | `CLAUDE` (Lead Architecture / Reasoning) | **89.4** | 89.0% | $11.43 | **176.6** | 75.1 | 77.0% | 1557 | 40.7 | $5/$25 |
| **Grok 4.5** | `FRONTIER` (Frontier Agentic / Reasoning) | **88.9** | 88.4% | $3.61 | **273.7** | 73.9 | 77.0% | 1556 | 39.1 | $2/$6 |
| **Claude Sonnet 5** | `CLAUDE` (Fast Agentic / Design) | **88.5** | 87.9% | $4.68 | **242.7** | 72.9 | 76.6% | 1538 | 38.4 | $2/$10 |
| ⭐ **DeepSeek V4 Flash** | `API` (Ultra-Fast Verifier) | **87.9** | 87.1% | $0.09 | **939.1** | 71.5 | 77.7% | 1582 | 34.5 | $0.06/$0.11 |
| **Muse Spark 1.1 (xhigh)** | `API` (Upstream API) | **87.2** | 86.1% | $2.52 | **307.6** | 69.7 | 76.0% | 1541 | 34.3 | $1.25/$4.25 |
| **Muse Spark 1.2 Contributor** | `API` (Benchmark Model) | **87.2** | 86.1% | — | — | 69.7 | 76.0% | 1541 | 34.3 | —/— |
| **GLM-5.3 Flash** | `API` (Fast Executor) | **87.1** | 86.0% | $0.30 | **726.2** | 69.5 | 71.1% | 1605 | 41.9 | $0.15/$0.50 |
| **GLM-5.2** | `API` (Tier 1 — Architecture) | **86.7** | 85.4% | $2.76 | **291.5** | 68.4 | 73.4% | 1589 | 38.6 | $1.4/$4.4 |
| **GPT 5.6 Luna** | `API` (High-Efficiency Failover) | **86.7** | 85.4% | $0.55 | **588.6** | 68.4 | 73.7% | 1520 | 37.5 | $0.20/$1.2 |
| **Qwen3.8 27B** | `API` (Fast Executor) | **86.5** | 85.1% | $1.28 | **411.2** | 67.9 | 75.8% | 1591 | 33.9 | $0.40/$3 |
| **DeepSeek V4 Pro** | `API` (Tier 2 — Verifier & Logic) | **86.5** | 85.1% | $0.69 | **536.3** | 67.9 | 78.2% | 1446 | 36.3 | $0.41/$0.83 |

## 2. Models with Partial / Missing Benchmark Evaluations

### 2.1 Top 10 — Missing LiveBench (Arena.ai + AA Evaluated)

| Rank | Model | Pool / Tier | Q (Cap) | P(Succ) | Eff. $/M | LiveBench (%) | Arena Elo | AA Quality | Raw $/M |
| :---: | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| #1 | **Qwen3.6 Max Preview** | `API` (Upstream API) | **85.6** | 83.6% | $3.72 | — | 1479 | 28.4 | $1.3/$7.8 |
| #2 | **GLM-5.1 (Reasoning)** | `API` (Upstream API) | **85.4** | 83.3% | $2.65 | — | 1508 | 27.4 | $1.2/$4.4 |
| #3 | **GPT-5.2 (xhigh)** | `API` (Upstream API) | **84.8** | 82.3% | $6.17 | — | 1417 | 30.4 | $1.75/$14 |
| #4 | **GLM-5 (Reasoning)** | `API` (Upstream API) | **84.2** | 81.2% | $2.17 | — | 1436 | 27.9 | $1/$3.2 |
| #5 | **Hy3-preview (Reasoning)** | `API` (Upstream API) | **83.9** | 80.7% | $0.14 | — | 1510 | 22.7 | $0.06/$0.21 |
| #6 | **Inkling Small** | `API` (Upstream API) | **82.7** | 78.3% | $0.77 | — | 1406 | 26.1 | $0.30/$1.2 |
| #7 | **Solar Pro 4** | `API` (Upstream API) | **82.6** | 78.1% | $0.78 | — | 1371 | 28.2 | $0.30/$1.2 |
| #8 | **MiMo-V2.5** | `API` (Bulk Fill) | **82.4** | 77.7% | $0.27 | — | 1437 | 22.3 | $0.14/$0.28 |
| #9 | **Kimi K2.5 (Reasoning)** | `API` (Upstream API) | **81.8** | 76.4% | $1.73 | — | 1436 | 23.5 | $0.60/$2.75 |
| #10 | **Gemini 3 Pro Preview (low)** | `API` (Upstream API) | **81.8** | 76.4% | $6.72 | — | 1439 | 22.3 | $2/$12 |

### 2.2 Top 10 — Missing LMArena (LiveBench + AA Evaluated)

| Rank | Model | Pool / Tier | Q (Cap) | P(Succ) | Eff. $/M | LiveBench (%) | Arena Elo | AA Quality | Raw $/M |
| :---: | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| #1 | **Qwen3.7 Max** | `API` (Upstream API) | **84.7** | 82.1% | $5.18 | 74.1% | — | 29.9 | $2.5/$7.5 |
| #2 | **Qwen3.7 Max** | `API` (Benchmark Model) | **84.7** | 82.1% | $3.06 | 74.1% | — | 29.9 | $1.48/$4.42 |
| #3 | **GPT 5.4-nano-xhigh** | `API` (Benchmark Model) | **79.5** | 71.1% | — | 70.8% | — | 21.2 | —/— |
| #4 | **Qwen3.6-27b** | `API` (Benchmark Model) | **75.0** | 58.9% | $1.63 | 64.2% | — | 21.9 | $0.30/$2 |

### 2.3 Top 10 — Missing Artificial Analysis (LiveBench + Arena Evaluated)

| Rank | Model | Pool / Tier | Q (Cap) | P(Succ) | Eff. $/M | LiveBench (%) | Arena Elo | AA Quality | Raw $/M |
| :---: | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| #1 | **GPT-5.4 Pro** | `FRONTIER` (Enterprise Agentic Flagship) | **82.1** | 77.1% | $99.00 | 78.8% | 1463 | — | $30/$180 |

### 2.4 Top 10 — Single-Benchmark / Emerging Models (1 Evaluator Only)

| Rank | Model | Pool / Tier | Q (Cap) | P(Succ) | Eff. $/M | LiveBench (%) | Arena Elo | AA Quality | Raw $/M |
| :---: | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| #1 | **Qwen3.8 2.4T A95B** | `API` (Upstream API) | **95.4** | 94.3% | $3.16 | — | — | 40.0 | $2/$6 |
| #2 | **Qwen3-8 Max-0902** | `API` (Arena Model) | **93.4** | 92.9% | — | — | 1685 | — | —/— |
| #3 | **GPT-5.3 Codex (xhigh)** | `API` (Upstream API) | **92.7** | 92.3% | $4.96 | — | — | 32.5 | $1.75/$14 |
| #4 | **Agnes 2.5 Pro Beta** | `API` (Upstream API) | **91.7** | 91.4% | $0.17 | — | — | 35.2 | $0.10/$0.30 |
| #5 | **Motif 3** | `API` (Upstream API) | **91.0** | 90.7% | — | — | — | 33.6 | —/— |
| #6 | **K2 Horizon 375B A23B** | `API` (Upstream API) | **90.9** | 90.6% | — | — | — | 33.9 | —/— |
| #7 | **Motif 3 (Beta)** | `API` (Upstream API) | **90.2** | 89.9% | — | — | — | 32.3 | —/— |
| #8 | **Claude Opus 4.5 (Reasoning)** | `API` (Upstream API) | **90.0** | 89.7% | $11.25 | — | — | 29.1 | $5/$25 |
| #9 | **Hunyuan 4 Preview** | `API` (Frontier Reasoning) | **89.7** | 89.3% | $1.47 | — | 1623 | — | $0.83/$2.50 |
| #10 | **Muse Spark** | `API` (Upstream API) | **89.2** | 88.7% | — | — | — | 31.3 | —/— |


### ⚠️ Unmatched Catalog Models (0 Upstream Benchmark Evaluations)
> **See Something, Say Something**: The following models configured in the catalog did not match any verified evaluation on LiveBench, LMArena, or Artificial Analysis:

| Model | Pool | Checked LiveBench Aliases | Checked LMArena Aliases |
| :--- | :---: | :--- | :--- |
| EXAONE 4.5 33B (Non-reasoning) | `[API]` | `exaone-4-5-33b-non-reasoning` | `exaone-4-5-33b-non-reasoning` |
| GPT-4o mini Realtime (Dec '24) | `[API]` | `gpt-4o-mini-realtime-dec-2024` | `gpt-4o-mini-realtime-dec-2024` |
| GPT-5.4 Pro (xhigh) | `[API]` | `gpt-5-4-pro` | `gpt-5-4-pro` |
| GPT-3.5 Turbo (0613) | `[API]` | `gpt-3-5-turbo-0613` | `gpt-3-5-turbo-0613` |
| Gemini 3 Deep Think | `[API]` | `gemini-3-deep-think` | `gemini-3-deep-think` |
| Mi:dm K 2.5 Pro Preview | `[API]` | `midm-250-pro-rsnsft` | `midm-250-pro-rsnsft` |
| GPT-4o Realtime (Dec '24) | `[API]` | `gpt-4o-realtime-dec-2024` | `gpt-4o-realtime-dec-2024` |
| GPT-5.5 Pro (xhigh) | `[API]` | `gpt-5-5-pro` | `gpt-5-5-pro` |
| Cogito v2.1 (Reasoning) | `[API]` | `cogito-v2-1-reasoning` | `cogito-v2-1-reasoning` |


## 3. Column Winners & Podium Leaders (1st 🥇 · 2nd 🥈 · 3rd 🥉)

| Metric / Column | 🥇 1st Place (Gold) | 🥈 2nd Place (Silver) | 🥉 3rd Place (Bronze) |
| :--- | :--- | :--- | :--- |
| **Q(Cap) — Composite Capability** | **Claude Fable-5-1-max** `[API]` (98.5) | **GPT-6 Astra (xhigh)** `[API]` (98.3) | **Claude Fable 5.1 (Adaptive Reasoning, Low Effort, Default Fallback)** `[API]` (96.5) |
| **FGI — Architectural Gate Index** | **Claude Fable-5-1-max** `[API]` (92.6) | **GPT-6 Astra (xhigh)** `[API]` (92.3) | **Claude Fable 5.1 (Adaptive Reasoning, Low Effort, Default Fallback)** `[API]` (89.4) |
| **AVI — Agentic Value Index (ROI)** | **Qwen3.8-Flash-Next** `[API]` (947.8) | **DeepSeek V4 Flash** `[API]` (939.1) | **Muse Spark 1.2 (Contributor)** `[API]` (909.3) |
| **LiveBench (%) — Decontaminated** | **Claude Fable-5-1-max** `[API]` (83.8%) | **Claude Fable 5.1 (Adaptive Reasoning, Low Effort, Default Fallback)** `[API]` (83.8%) | **Claude Fable 5 (High)** `[CLD]` (83.4%) |
| **Arena.ai Elo — Global Arena** | **GPT-6 Astra (xhigh)** `[API]` (1796) | **Claude Fable-5-1-max** `[API]` (1764) | **Claude Fable 5.1 (Adaptive Reasoning, Low Effort, Default Fallback)** `[API]` (1764) |
| **Coding Elo — LMSYS Arena** | — | — | — |
| **Speed — Generation Throughput** | **Gemini 3.5 Flash-Lite** `[API]` (356 t/s) | **Gemini 3.5-flash-lite-high** `[API]` (356 t/s) | **Gemini 3.7 Flash (Thinking)** `[AGY]` (304 t/s) |
| **Eff $/M — Real Solved Task Cost** | **DeepSeek V4 Flash** `[API]` ($0.09) | **Qwen3.8-Flash-Next** `[API]` ($0.14) | **Muse Spark 1.2 (Contributor)** `[API]` ($0.15) |
| **Price — Blended Raw Cost** | **DeepSeek V4 Flash** `[API]` ($0.07) | **Qwen3.8-Flash-Next** `[API]` ($0.11) | **Muse Spark 1.2 (Contributor)** `[API]` ($0.12) |
| **P(Succ) (%) — 1-Turn Pass Rate** | **Claude Fable-5-1-max** `[API]` (96.0%) | **GPT-6 Astra (xhigh)** `[API]` (95.9%) | **Claude Fable 5.1 (Adaptive Reasoning, Low Effort, Default Fallback)** `[API]` (95.0%) |

## 4. Dynamic Function & Role Recommendations (Weighted Scoring)

### Dynamic Function & Role Recommendations (Weighted Scoring)

| Function / Role | 🥇 Recommended Winner | 🥈 Runner-Up | Tactical Guidance |
| :--- | :--- | :--- | :--- |
| 🏗️ **System Architecture & Complex Design** | **GPT-6 Astra** `[API]` *(Score: 90.9)* | **Claude Fable-5-1-max** `[API]` *(90.7)* | Deep reasoning & high FGI gates. Use for contracts, spec lock, and hard debugging. |
| 💻 **Pair Programming & Code Editing** | **Claude Fable-5-1-max** `[API]` *(Score: 90.1)* | **Claude Fable 5.1** `[API]` *(88.0)* | Surgical diffs, coding Elo & multi-turn alignment without drift. |
| 🔄 **Daily Driver (High ROI Workhorse)** | **Qwen3.8-Flash-Next** `[API]` *(Score: 93.9)* | **DeepSeek V4 Flash** `[API]` *(93.1)* | Top AVI & cost-efficiency. Autonomous loops without token explosion. |
| ⚡ **Fast Boilerplate & Mechanical Fill** | **Muse Spark 1.2** `[API]` *(Score: 99.9)* | **DeepSeek V4 Flash** `[API]` *(93.4)* | High throughput (TPS/BFI) for mechanical generation and test scaffolding. |

## 5. Key Insights & Routing Architecture

- **⭐ Pareto Frontier Models**: Undefeated efficiency and top cost-to-capability curve (e.g. Claude Opus 5, GPT-5.6 Sol, Gemini 3.7 Flash, DeepSeek V4 Flash, GPT-OSS 120B).
- **Tier 1: Architectural Gates & Complex Debugging (High FGI)**: **Claude Fable 5** (LiveBench 83.4%), **Claude Opus 5 (Thinking)** (LiveBench 80.5%), and **Gemini 3.7 Flash Thinking** (LiveBench 79.9%) lead uncontaminated general coding and reasoning.
- **Tier 2: Workhorse Multi-Turn Loops (High AVI ROI)**: **Gemini 3.7 Flash Thinking** (AVI 421.9, Eff. $1.04/M) and **DeepSeek V4 Flash** (AVI 538.9, Eff. $0.21/M) deliver maximal intelligence per dollar without suffering token explosion.
- **Tier 3: Bulk Fill & Fast Search (High BFI)**: **MiMo-V2.5** and **DeepSeek V4 Flash** provide ultra-fast mechanical token generation.
- **The Token Multiplier Effect**: Sub-70 capability models incur up to 4.5x token burn from multi-turn retries, turning cheap base prices into high effective costs per solved task.

_Generated by `benchmarks_check.py` (`bcheck`) on 2026-09-09 12:29:52 UTC._