# Consolidated LLM Benchmark & Agentic Cost-Benefit Report (2026-08-31)

Consolidated capability & cost-efficiency benchmark across **OpenCode Go**, **AGY Subscription (Gemini)**, **Claude Subscription (Anthropic)**, and **Frontier API Models** across Arena.ai, LiveBench (https://livebench.ai), and Artificial Analysis.

## 1. Master Agentic Value & Capability Leaderboard

| Model | Pool / Tier | Q (Cap) | P(Succ) | Eff. $/M | AVI (Value) | FGI (Gate) | LiveBench (%) | Coding Elo | Speed | Raw $/M |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| ⭐ **Claude Fable 5 (High)** | `CLAUDE` (Elite Creative / Agent) | **88.5** | 87.9% | $23.40 | **137.5** | 72.9 | 83.4% | 1512 | 65 t/s | $10.00 / $50.00 |
| ⭐ **Claude Opus 5 (Thinking)** | `CLAUDE` (Flagship / Complex Gates) | **86.7** | 85.4% | $12.42 | **160.5** | 68.4 | 80.5% | 1520 | 54 t/s | $5.00 / $25.00 |
| ⭐ **GPT-5.6 Sol (Reasoning Flagship)** | `FRONTIER` (Frontier Flagship Reasoning) | **86.3** | 84.8% | $5.00 | **223.4** | 67.4 | 81.7% | 1515 | 79 t/s | $2.00 / $10.00 |
| **GPT 5.5 (xHigh)** | `FRONTIER` (Frontier Agentic Reasoning) | **85.8** | 84.0% | $14.20 | **150.0** | 66.1 | 80.8% | 1500 | 92 t/s | $5.00 / $30.00 |
| **Kimi K3 (Max)** | `OCGO` (Tier 1 — Architecture & Reasoning) | **85.6** | 83.6% | $7.72 | **184.9** | 65.4 | 79.5% | 1475 | 40 t/s | $3.00 / $15.00 |
| ⭐ **Gemini 3.1 Pro (High)** | `AGY` (Flagship Reasoning (1M ctx)) | **84.5** | 81.8% | $5.96 | **198.7** | 62.5 | 78.0% | 1460 | 52 t/s | $2.00 / $12.00 |
| ⭐ **Gemini 3.7 Flash (Thinking)** | `AGY` (Workhorse / Default) | **83.8** | 80.5% | $1.04 | **420.6** | 60.5 | 79.9% | 1445 | 315 t/s | $0.38 / $1.88 |
| **GPT-5.4 Pro** | `FRONTIER` (Enterprise Agentic Flagship) | **83.6** | 80.1% | $93.00 | **85.7** | 59.9 | — | 1480 | 36 t/s | $30.00 / $180.00 |
| **Grok 4.5** | `FRONTIER` (Frontier Agentic / Reasoning) | **82.5** | 77.9% | $4.54 | **210.6** | 56.7 | 77.0% | 1435 | 53 t/s | $2.00 / $6.00 |
| **Qwen3.8 Max** | `OCGO` (Tier 1 — High Reasoning) | **81.9** | 76.6% | $4.68 | **204.7** | 54.9 | 79.5% | 1395 | 38 t/s | $2.00 / $6.00 |
| **Claude Opus 4.6 (Thinking)** | `CLAUDE` (Lead / Architecture) | **81.8** | 76.4% | $15.12 | **132.3** | 54.6 | 75.1% | 1495 | 37 t/s | $5.00 / $25.00 |
| **Claude Sonnet 5** | `CLAUDE` (Fast Agentic / Design) | **81.8** | 76.4% | $6.05 | **183.9** | 54.6 | 76.6% | 1485 | 80 t/s | $2.00 / $10.00 |
| **Claude Sonnet 4.6 (Thinking)** | `CLAUDE` (Design / Refactor) | **80.3** | 73.0% | $9.77 | **147.4** | 50.1 | 75.6% | 1478 | 43 t/s | $3.00 / $15.00 |
| ⭐ **DeepSeek V4 Pro** | `OCGO` (Tier 2 — Verifier & Logic) | **79.6** | 71.3% | $0.93 | **394.3** | 47.9 | 72.5% | 1415 | 61 t/s | $0.41 / $0.83 |
| **GLM-5.3** | `OCGO` (Tier 1 — Architecture & Spec) | **78.5** | 68.6% | $4.02 | **198.8** | 44.6 | 76.7% | 1390 | 74 t/s | $1.40 / $4.40 |
| **GPT-5.2 Codex** | `FRONTIER` (Coding Specialist / Agent) | **77.2** | 65.1% | $9.16 | **138.3** | 40.5 | 74.0% | 1465 | 62 t/s | $1.75 / $14.00 |
| ⭐ **GPT 5.6 Luna** | `OCGO` (Tier 4 — Failover Heavy) | **76.9** | 64.3% | $0.89 | **372.5** | 39.6 | 73.7% | 1395 | 128 t/s | $0.20 / $1.20 |
| **Qwen3 Coder 480B** | `FRONTIER` (Open Coding Specialist) | **75.9** | 61.5% | $1.05 | **336.8** | 36.6 | — | 1450 | 80 t/s | $0.30 / $1.00 |
| ⭐ **DeepSeek V4 Flash** | `OCGO` (Tier 2 — Default / Mid) | **74.5** | 57.4% | $0.18 | **583.4** | 32.4 | 66.0% | 1360 | 103 t/s | $0.06 / $0.11 |
| **GLM-5.2** | `OCGO` (Tier 2 — General Executor) | **74.4** | 57.2% | $1.86 | **249.0** | 32.2 | 73.4% | 1360 | 70 t/s | $0.50 / $1.50 |
| **MiMo V2.5 Pro** | `OCGO` (Tier 2 — General Executor) | **74.2** | 56.6% | $1.88 | **246.3** | 31.6 | — | 1360 | 34 t/s | $0.50 / $1.50 |
| **Hunyuan 3** | `OCGO` (Tier 2 — General Executor) | **73.5** | 54.5% | $1.99 | **235.1** | 29.6 | — | 1360 | 95 t/s | $0.50 / $1.50 |
| **MiniMax M3** | `OCGO` (Tier 2 — General) | **73.1** | 53.3% | $1.41 | **271.8** | 28.4 | 67.5% | 1360 | 150 t/s | $0.30 / $1.20 |
| **Qwen3.7 Plus** | `OCGO` (Tier 2 — General Executor) | **72.5** | 51.5% | $2.15 | **220.2** | 26.8 | — | 1360 | 56 t/s | $0.50 / $1.50 |
| **Kimi K2.7 Code** | `OCGO` (Tier 2 — General Executor) | **71.1** | 47.3% | $2.42 | **199.9** | 23.1 | 68.8% | 1360 | 45 t/s | $0.50 / $1.50 |
| **Gemini 3.1 Flash Lite** | `AGY` (Ultra Fast / Bulk) | **70.2** | 44.6% | $1.86 | **219.1** | 20.9 | 62.1% | 1395 | 180 t/s | $0.25 / $1.50 |
| **MiMo-V2.5** | `OCGO` (Tier 3 — Bulk Fill) | **69.4** | 42.3% | $0.67 | **334.2** | 19.1 | — | 1335 | 115 t/s | $0.14 / $0.28 |
| **Claude Haiku 4.5** | `CLAUDE` (Fast / Scout) | **64.9** | 29.9% | $11.09 | **88.2** | 10.6 | — | 1360 | 125 t/s | $1.00 / $5.00 |
| **LongCat 2.0 (Meituan)** | `OCGO` (Tier 3 — Long-Context / Bulk Fill) | **64.5** | 28.9% | $3.08 | **144.8** | 10.0 | — | 1340 | 39 t/s | $0.30 / $1.20 |
| **GPT-OSS 120B (Medium)** | `FRONTIER` (Open High-Efficiency) | **60.8** | 20.7% | $0.62 | **257.6** | 5.7 | 46.4% | 1380 | 187 t/s | $0.04 / $0.17 |

## 2. Column Winners & Podium Leaders (1st 🥇 · 2nd 🥈 · 3rd 🥉)

| Metric / Column | 🥇 1st Place (Gold) | 🥈 2nd Place (Silver) | 🥉 3rd Place (Bronze) |
| :--- | :--- | :--- | :--- |
| **Q(Cap) — Composite Capability** | **Claude Fable 5 (High)** `[CLD]` (88.5) | **Claude Opus 5 (Thinking)** `[CLD]` (86.7) | **GPT-5.6 Sol (Reasoning Flagship)** `[FRT]` (86.3) |
| **FGI — Architectural Gate Index** | **Claude Fable 5 (High)** `[CLD]` (72.9) | **Claude Opus 5 (Thinking)** `[CLD]` (68.4) | **GPT-5.6 Sol (Reasoning Flagship)** `[FRT]` (67.4) |
| **AVI — Agentic Value Index (ROI)** | **DeepSeek V4 Flash** `[OCG]` (583.4) | **Gemini 3.7 Flash (Thinking)** `[AGY]` (420.6) | **DeepSeek V4 Pro** `[OCG]` (394.3) |
| **LiveBench (%) — Decontaminated** | **Claude Fable 5 (High)** `[CLD]` (83.4%) | **GPT-5.6 Sol (Reasoning Flagship)** `[FRT]` (81.7%) | **GPT 5.5 (xHigh)** `[FRT]` (80.8%) |
| **Arena.ai Elo — Global Arena** | **Claude Fable 5 (High)** `[CLD]` (1507) | **Claude Opus 4.6 (Thinking)** `[CLD]` (1497) | **Gemini 3.7 Flash (Thinking)** `[AGY]` (1490) |
| **Coding Elo — LMSYS Arena** | **Claude Opus 5 (Thinking)** `[CLD]` (1520) | **GPT-5.6 Sol (Reasoning Flagship)** `[FRT]` (1515) | **Claude Fable 5 (High)** `[CLD]` (1512) |
| **Speed — Generation Throughput** | **Gemini 3.7 Flash (Thinking)** `[AGY]` (315 t/s) | **GPT-OSS 120B (Medium)** `[FRT]` (186 t/s) | **Gemini 3.1 Flash Lite** `[AGY]` (180 t/s) |
| **Eff $/M — Real Solved Task Cost** | **DeepSeek V4 Flash** `[OCG]` ($0.18) | **GPT-OSS 120B (Medium)** `[FRT]` ($0.62) | **MiMo-V2.5** `[OCG]` ($0.67) |
| **Price — Blended Raw Cost** | **DeepSeek V4 Flash** `[OCG]` ($0.07) | **GPT-OSS 120B (Medium)** `[FRT]` ($0.07) | **MiMo-V2.5** `[OCG]` ($0.17) |
| **P(Succ) (%) — 1-Turn Pass Rate** | **Claude Fable 5 (High)** `[CLD]` (87.9%) | **Claude Opus 5 (Thinking)** `[CLD]` (85.4%) | **GPT-5.6 Sol (Reasoning Flagship)** `[FRT]` (84.8%) |

## 3. Dynamic Function & Role Recommendations (Weighted Scoring)

### Dynamic Function & Role Recommendations (Weighted Scoring)

| Function / Role | 🥇 Recommended Winner | 🥈 Runner-Up | Tactical Guidance |
| :--- | :--- | :--- | :--- |
| 🏗️ **System Architecture & Complex Design** | **Claude Fable 5** `[CLD]` *(Score: 90.3)* | **Claude Opus 5** `[CLD]` *(89.3)* | Deep reasoning & high FGI gates. Use for contracts, spec lock, and hard debugging. |
| 💻 **Pair Programming & Code Editing** | **GPT-5.6 Sol** `[FRT]` *(Score: 87.5)* | **Claude Fable 5** `[CLD]` *(87.0)* | Surgical diffs, coding Elo & multi-turn alignment without drift. |
| 🔄 **Daily Driver (High ROI Workhorse)** | **DeepSeek V4 Flash** `[OCG]` *(Score: 93.8)* | **Gemini 3.7 Flash** `[AGY]` *(89.3)* | Top AVI & cost-efficiency. Autonomous loops without token explosion. |
| ⚡ **Fast Boilerplate & Mechanical Fill** | **Gemini 3.7 Flash** `[AGY]` *(Score: 95.4)* | **DeepSeek V4 Flash** `[OCG]` *(91.1)* | High throughput (TPS/BFI) for mechanical generation and test scaffolding. |

## 4. Key Insights & Routing Architecture

- **⭐ Pareto Frontier Models**: Undefeated efficiency and top cost-to-capability curve (e.g. Claude Opus 5, GPT-5.6 Sol, Gemini 3.7 Flash, DeepSeek V4 Flash, GPT-OSS 120B).
- **Tier 1: Architectural Gates & Complex Debugging (High FGI)**: **Claude Fable 5** (LiveBench 83.4%), **Claude Opus 5 (Thinking)** (LiveBench 80.5%), and **Gemini 3.7 Flash Thinking** (LiveBench 79.9%) lead uncontaminated general coding and reasoning.
- **Tier 2: Workhorse Multi-Turn Loops (High AVI ROI)**: **Gemini 3.7 Flash Thinking** (AVI 421.9, Eff. $1.04/M) and **DeepSeek V4 Flash** (AVI 538.9, Eff. $0.21/M) deliver maximal intelligence per dollar without suffering token explosion.
- **Tier 3: Bulk Fill & Fast Search (High BFI)**: **MiMo-V2.5** and **DeepSeek V4 Flash** provide ultra-fast mechanical token generation.
- **The Token Multiplier Effect**: Sub-70 capability models incur up to 4.5x token burn from multi-turn retries, turning cheap base prices into high effective costs per solved task.

_Generated by `benchmarks_check.py` (`bcheck`) on 2026-08-31 19:33:52 UTC._