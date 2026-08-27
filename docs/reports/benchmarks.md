# Consolidated LLM Benchmark & Agentic Cost-Benefit Report (2026-08-23)

Consolidated capability & cost-efficiency benchmark across **OpenCode Go**, **AGY Subscription (Gemini)**, **Claude Subscription (Anthropic)**, and **Frontier API Models** across Arena.ai, Artificial Analysis, OpenRouter, and ARC Prize (ARC-AGI-2).

## 1. Master Agentic Value & Capability Leaderboard

| Model | Pool / Tier | Q (Cap) | P(Succ) | Eff. $/M | AVI (Value) | FGI (Gate) | ARC-AGI-2 (%) | Coding Elo | Speed | Raw $/M |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Claude Opus 5 (Thinking)** | `CLAUDE` (Flagship / Complex Gates) | **89.2** | 88.7% | $11.51 | **175.3** | 74.6 | 90.4% | 1520 | 38 t/s | $5.00 / $25.00 |
| **Claude Fable 5 (High)** | `CLAUDE` (Elite Creative / Agent) | **88.6** | 88.0% | $23.40 | **137.8** | 73.1 | 88.0% | 1512 | 35 t/s | $10.00 / $50.00 |
| **GPT-5.6 Sol (Reasoning Flagship)** | `FRONTIER` (Frontier Flagship Reasoning) | **88.0** | 87.2% | $4.76 | **238.0** | 71.7 | 81.0% | 1515 | 45 t/s | $2.00 / $10.00 |
| **GPT 5.5 (xHigh)** | `FRONTIER` (Frontier Agentic Reasoning) | **86.9** | 85.7% | $13.68 | **156.1** | 68.9 | 78.5% | 1500 | 40 t/s | $5.00 / $30.00 |
| **GPT-5.4 Pro** | `FRONTIER` (Enterprise Agentic Flagship) | **85.5** | 83.5% | $86.12 | **91.6** | 65.2 | 72.5% | 1480 | 36 t/s | $30.00 / $180.00 |
| **Claude Opus 4.6 (Thinking)** | `CLAUDE` (Lead / Architecture) | **85.3** | 83.1% | $13.01 | **152.4** | 64.7 | 68.8% | 1495 | 42 t/s | $5.00 / $25.00 |
| **Gemini 3.1 Pro (High)** | `AGY` (Flagship Reasoning (1M ctx)) | **84.2** | 81.2% | $6.04 | **196.2** | 61.6 | 77.1% | 1460 | 52 t/s | $2.00 / $12.00 |
| **Kimi K3 (Max)** | `OCGO` (Tier 1 — Architecture & Reasoning) | **83.3** | 79.5% | $8.46 | **168.3** | 59.1 | 66.5% | 1475 | 46 t/s | $3.00 / $15.00 |
| **Claude Sonnet 5** | `CLAUDE` (Fast Agentic / Design) | **83.0** | 78.9% | $5.72 | **194.2** | 58.2 | 64.2% | 1485 | 68 t/s | $2.00 / $10.00 |
| **Claude Sonnet 4.6 (Thinking)** | `CLAUDE` (Design / Refactor) | **82.7** | 78.3% | $8.69 | **164.1** | 57.3 | 62.5% | 1478 | 52 t/s | $3.00 / $15.00 |
| **Grok 4.5** | `FRONTIER` (Frontier Agentic / Reasoning) | **81.0** | 74.6% | $4.89 | **196.1** | 52.2 | 67.1% | 1435 | 50 t/s | $2.00 / $6.00 |
| **GPT-5.2 Codex** | `FRONTIER` (Coding Specialist / Agent) | **79.6** | 71.3% | $7.91 | **156.2** | 48.0 | 48.0% | 1465 | 62 t/s | $1.75 / $14.00 |
| **Gemini 3.7 Flash (Thinking)** | `AGY` (Workhorse / Default) | **78.9** | 69.6% | $1.33 | **329.7** | 45.8 | 84.6% | 1420 | 135 t/s | $0.38 / $1.88 |
| **DeepSeek V4 Pro** | `OCGO` (Tier 2 — Verifier & Logic) | **77.7** | 66.5% | $1.04 | **355.8** | 42.1 | 63.5% | 1415 | 38 t/s | $0.41 / $0.83 |
| **Qwen3 Coder 480B** | `FRONTIER` (Open Coding Specialist) | **76.4** | 62.9% | $1.01 | **347.5** | 38.1 | 42.0% | 1450 | 80 t/s | $0.30 / $1.00 |
| **GPT 5.6 Luna** | `OCGO` (Tier 4 — Failover Heavy) | **75.4** | 60.1% | $0.99 | **341.4** | 35.1 | 59.6% | 1395 | 60 t/s | $0.20 / $1.20 |
| **Qwen3.8 Max** | `OCGO` (Tier 1 — High Reasoning) | **74.5** | 57.4% | $7.36 | **138.7** | 32.4 | 44.0% | 1395 | 40 t/s | $2.00 / $6.00 |
| **GLM-5.3** | `OCGO` (Tier 1 — Architecture & Spec) | **72.8** | 52.4% | $6.00 | **142.8** | 27.6 | 38.0% | 1390 | 42 t/s | $1.40 / $4.40 |
| **GPT-OSS 120B (Medium)** | `FRONTIER` (Open High-Efficiency) | **70.9** | 46.7% | $0.23 | **494.3** | 22.6 | 38.5% | 1380 | 110 t/s | $0.04 / $0.17 |
| **DeepSeek V4 Flash** | `OCGO` (Tier 2 — Default / Mid) | **69.7** | 43.1% | $0.27 | **456.5** | 19.8 | 61.4% | 1360 | 95 t/s | $0.06 / $0.11 |
| **MiniMax M3** | `OCGO` (Tier 2 — General) | **68.1** | 38.5% | $2.17 | **191.2** | 16.3 | 32.0% | 1360 | 75 t/s | $0.30 / $1.20 |
| **Claude Haiku 4.5** | `CLAUDE` (Fast / Scout) | **64.8** | 29.7% | $11.20 | **87.6** | 10.5 | 24.5% | 1360 | 125 t/s | $1.00 / $5.00 |
| **MiMo-V2.5** | `OCGO` (Tier 3 — Bulk Fill) | **62.9** | 25.1% | $1.27 | **204.7** | 7.9 | 24.0% | 1335 | 115 t/s | $0.14 / $0.28 |
| **Gemini 3.1 Flash Lite** | `AGY` (Ultra Fast / Bulk) | **62.6** | 24.5% | $3.90 | **122.4** | 7.6 | 18.0% | 1335 | 180 t/s | $0.25 / $1.50 |

## 2. Key Insights & Routing Architecture

- **Tier 1: Architectural Gates & Complex Debugging (High FGI)**: **Claude Opus 5 (Thinking)** (FGI 76.7) and **GPT-5.6 Sol** (FGI 74.4) dominate non-trivial multi-file refactoring and design contracts with near-90% success rates.
- **Tier 2: Workhorse Multi-Turn Loops (High AVI ROI)**: **Gemini 3.7 Flash Thinking** (AVI 452.9, Eff. $1.28/M) and **DeepSeek V4 Flash** (AVI 430.7, Eff. $0.15/M) deliver maximal intelligence per dollar without suffering token explosion.
- **Tier 3: Bulk Fill & Fast Search (High BFI)**: **MiMo-V2.5** and **DeepSeek V4 Flash** provide ultra-fast mechanical token generation.
- **The Token Multiplier Effect**: Sub-70 capability models incur up to 4.5x token burn from multi-turn retries, turning cheap base prices into high effective costs per solved task.

_Generated by `benchmarks_check.py` (`bcheck`) on 2026-08-22 23:23:20 UTC._
