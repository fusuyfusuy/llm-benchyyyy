#!/usr/bin/env python3
"""
benchmarks_check.py — Multi-source benchmark consolidation across subscription pools

Consolidates LLM intelligence & capability metrics across:
- OpenCode Go catalog (GLM-5.3, DeepSeek-V4, MiMo-V2.5, GPT-5.6 Luna, Kimi-K3, etc.)
- AGY subscription models (Gemini 3.7 Flash, Gemini 3.1 Pro, Flash Thinking)
- Claude subscription models (Claude Opus 5, Fable 5, Sonnet 5, Opus 4.6, Sonnet 4.6)
- Frontier & High-Ranking API models (OpenAI GPT-5.6 Sol, GPT-5.5, GPT-5.4 Pro, DeepSeek R1, Grok-4.5)

Ingests & synthesizes:
1. Arena.ai / LMSYS Arena (Overall Elo, Coding Elo, Hard Prompts Elo, Agent/Code Leaderboard)
2. Artificial Analysis (Quality Index, Coding Index, Math & Reasoning Index, Speed tok/s, Price $/M)
3. OpenRouter Benchmarks & Metrics (Latency, Throughput, Pricing)

Zero-dependency Python 3 standard library.
"""
import argparse
import datetime as dt
import glob
import html
import json
import math
import os
import pathlib
import re
import shutil
import statistics
import sys
import urllib.error
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
ROOT = HERE.parent
for _p in (HERE.parent, HERE.parent.parent, HERE.parent.parent.parent):
    if (_p / "setup.sh").exists() or (_p / ".git").exists():
        ROOT = _p
        break

DATA = ROOT / "docs" / "data"
RAW = DATA / "raw"
OUT = ROOT / "docs" / "reports"

import benchmark_common as bc
from benchmark_common import (
    C_RESET, C_BOLD, C_DIM,
    BG_EVEN, BG_ODD, BG_HEADER,
    C_GOLD, C_SILVER, C_BRONZE,
    C_GREEN, C_CYAN, C_YELLOW, C_MAGENTA, C_WHITE, C_GRAY, C_RED,
    norm_model_slug,
    compute_capability_q, compute_p_success, compute_token_multiplier,
    compute_effective_cost, compute_avi, compute_fgi, compute_bfi,
    compute_pareto_frontier,
    parse_livebench, parse_lmarena, parse_aa,
    display_len, color_cell, medal_badge, pool_badge,
    compute_column_medals, render_banner_box, render_metric_guide_cli,
    score_color_q, score_color_p, score_color_avi, score_color_fgi,
    HTML_CSS_COMMON, HTML_SORT_SCRIPT,
    compute_role_recommendations, render_role_recommendations_cli,
    render_role_recommendations_md, render_role_recommendations_html,
    load_previous_snapshot, diff_model_catalog, render_removed_models_cli,
)

UA = bc.UA

# ==============================================================================
# 1. CATALOG SPECIFICATION & SUBSCRIPTION POOLS
# ==============================================================================
# Subscription Pools & Model Definitions
# pool: 'ocgo' | 'agy' | 'claude' | 'frontier'
MODELS_CATALOG = {
    # --- Anthropic Claude Subscription Pool ---
    "claude-opus-5": {
        "display": "Claude Opus 5 (Thinking)",
        "provider": "Anthropic",
        "pool": "claude",
        "tier": "Flagship / Complex Gates",
        "sub_cost": "Claude Pro / Team / Max",
        "price_in": 5.00,
        "price_out": 25.00,
        "aa_slug": "claude-opus-5",
        "lm_slug": "claude-opus-5",
        "or_slug": "anthropic/claude-opus-5",
        "base_metrics": {
            "lm_elo": 1435,
            "lm_coding": 1520,
            "lm_hard": 1465,
            "aa_quality": 96.0,
            "aa_coding": 97.0,
            "aa_reasoning": 97.5,
            "speed_tps": 38.0,
        },
    },
    "claude-fable-5": {
        "display": "Claude Fable 5 (High)",
        "provider": "Anthropic",
        "pool": "claude",
        "tier": "Elite Creative / Agent",
        "sub_cost": "API ($10.00 / $50.00)",
        "price_in": 10.00,
        "price_out": 50.00,
        "aa_slug": "claude-fable-5",
        "lm_slug": "claude-fable-5",
        "or_slug": "anthropic/claude-fable-5",
        "base_metrics": {
            "lm_elo": 1432,
            "lm_coding": 1512,
            "lm_hard": 1460,
            "aa_quality": 95.9,
            "aa_coding": 96.8,
            "aa_reasoning": 97.0,
            "speed_tps": 35.0,
        },
    },
    "claude-opus-4-6": {
        "display": "Claude Opus 4.6 (Thinking)",
        "provider": "Anthropic",
        "pool": "claude",
        "tier": "Lead / Architecture",
        "sub_cost": "Claude Pro / AGY Bridge",
        "price_in": 5.00,
        "price_out": 25.00,
        "aa_slug": "claude-opus-4-6",
        "lm_slug": "claude-opus-4-6",
        "or_slug": "anthropic/claude-opus-4.6",
        "base_metrics": {
            "lm_elo": 1420,
            "lm_coding": 1495,
            "lm_hard": 1445,
            "aa_quality": 94.5,
            "aa_coding": 95.8,
            "aa_reasoning": 96.0,
            "speed_tps": 42.0,
        },
    },
    "claude-sonnet-5": {
        "display": "Claude Sonnet 5",
        "provider": "Anthropic",
        "pool": "claude",
        "tier": "Fast Agentic / Design",
        "sub_cost": "Claude Pro ($20/mo) / Team",
        "price_in": 2.00,
        "price_out": 10.00,
        "aa_slug": "claude-sonnet-5",
        "lm_slug": "claude-sonnet-5",
        "or_slug": "anthropic/claude-sonnet-5",
        "base_metrics": {
            "lm_elo": 1410,
            "lm_coding": 1485,
            "lm_hard": 1430,
            "aa_quality": 93.0,
            "aa_coding": 94.5,
            "aa_reasoning": 93.5,
            "speed_tps": 68.0,
        },
    },
    "claude-sonnet-4-6": {
        "display": "Claude Sonnet 4.6 (Thinking)",
        "provider": "Anthropic",
        "pool": "claude",
        "tier": "Design / Refactor",
        "sub_cost": "Claude Pro / AGY Bridge",
        "price_in": 3.00,
        "price_out": 15.00,
        "aa_slug": "claude-sonnet-4-6",
        "lm_slug": "claude-sonnet-4-6",
        "or_slug": "anthropic/claude-sonnet-4.6",
        "base_metrics": {
            "lm_elo": 1398,
            "lm_coding": 1478,
            "lm_hard": 1425,
            "aa_quality": 92.8,
            "aa_coding": 95.0,
            "aa_reasoning": 95.2,
            "speed_tps": 52.0,
        },
    },
    "claude-haiku-4-5": {
        "display": "Claude Haiku 4.5",
        "provider": "Anthropic",
        "pool": "claude",
        "tier": "Fast / Scout",
        "sub_cost": "Claude Pro / API ($1.00 / $5.00)",
        "price_in": 1.00,
        "price_out": 5.00,
        "aa_slug": "claude-haiku-4-5",
        "lm_slug": "claude-haiku-4-5",
        "or_slug": "anthropic/claude-haiku-4.5",
        "base_metrics": {
            "lm_elo": 1320,
            "lm_coding": 1360,
            "lm_hard": 1300,
            "aa_quality": 82.0,
            "aa_coding": 84.5,
            "aa_reasoning": 80.0,
            "speed_tps": 125.0,
        },
    },
    # --- Google Antigravity / Gemini Subscription Pool ---
    "gemini-3.1-pro": {
        "display": "Gemini 3.1 Pro (High)",
        "provider": "Google",
        "pool": "agy",
        "tier": "Flagship Reasoning (1M ctx)",
        "sub_cost": "AGY Sub (1B tokens/wk + 300M/5h)",
        "price_in": 2.00,
        "price_out": 12.00,
        "aa_slug": "gemini-3-1-pro",
        "lm_slug": "gemini-3.1-pro",
        "or_slug": "google/gemini-3.1-pro-preview",
        "base_metrics": {
            "lm_elo": 1486,
            "lm_coding": 1460,
            "lm_hard": 1445,
            "aa_quality": 93.5,
            "aa_coding": 94.0,
            "aa_reasoning": 95.5,
            "speed_tps": 52.0,
        },
    },
    "gemini-3.7-flash-thinking": {
        "display": "Gemini 3.7 Flash (Thinking)",
        "provider": "Google",
        "pool": "agy",
        "tier": "Workhorse / Default",
        "sub_cost": "AGY Sub (1B tokens/wk + 300M/5h)",
        "price_in": 0.38,
        "price_out": 1.88,
        "aa_slug": "gemini-3-7-flash",
        "lm_slug": "gemini-3.7-flash",
        "or_slug": "google/gemini-3.7-flash",
        "base_metrics": {
            "lm_elo": 1490,
            "lm_coding": 1445,
            "lm_hard": 1465,
            "aa_quality": 89.0,
            "aa_coding": 91.0,
            "aa_reasoning": 92.0,
            "speed_tps": 135.0,
        },
    },
    "gemini-3.1-flash-lite": {
        "display": "Gemini 3.1 Flash Lite",
        "provider": "Google",
        "pool": "agy",
        "tier": "Ultra Fast / Bulk",
        "sub_cost": "AGY Sub (1B tokens/wk + 300M/5h)",
        "price_in": 0.25,
        "price_out": 1.50,
        "aa_slug": "gemini-3-1-flash-lite",
        "lm_slug": "gemini-3.1-flash-lite",
        "or_slug": "google/gemini-3.1-flash-lite",
        "base_metrics": {
            "lm_elo": 1432,
            "lm_coding": 1395,
            "lm_hard": 1360,
            "aa_quality": 81.0,
            "aa_coding": 82.0,
            "aa_reasoning": 80.0,
            "speed_tps": 180.0,
        },
    },
    # --- OpenCode Go Subscription Pool ($12/5h · $30/wk · $60/mo pooled) ---
    "glm-5.3": {
        "display": "GLM-5.3",
        "provider": "Zhipu AI",
        "pool": "ocgo",
        "tier": "Tier 1 — Architecture & Spec",
        "sub_cost": "OC Go ($15 usage / 198 req/5h)",
        "price_in": 1.40,
        "price_out": 4.40,
        "aa_slug": "glm-5-3",
        "lm_slug": "glm-5.3",
        "or_slug": "z-ai/glm-5.3",
        "base_metrics": {
            "lm_elo": 1362,
            "lm_coding": 1390,
            "lm_hard": 1370,
            "aa_quality": 87.5,
            "aa_coding": 89.0,
            "aa_reasoning": 88.5,
            "speed_tps": 42.0,
        },
    },
    "kimi-k3": {
        "display": "Kimi K3 (Max)",
        "provider": "Moonshot",
        "pool": "ocgo",
        "tier": "Tier 1 — Architecture & Reasoning",
        "sub_cost": "OC Go ($15 usage / 120 req/5h)",
        "price_in": 3.00,
        "price_out": 15.00,
        "aa_slug": "kimi-k3",
        "lm_slug": "kimi-k3",
        "or_slug": "moonshot/kimi-k3",
        "base_metrics": {
            "lm_elo": 1410,
            "lm_coding": 1475,
            "lm_hard": 1430,
            "aa_quality": 93.0,
            "aa_coding": 94.5,
            "aa_reasoning": 95.0,
            "speed_tps": 46.0,
        },
    },
    "deepseek-v4-pro": {
        "display": "DeepSeek V4 Pro",
        "provider": "DeepSeek",
        "pool": "ocgo",
        "tier": "Tier 2 — Verifier & Logic",
        "sub_cost": "OC Go ($15 usage / 1,044 req/5h)",
        "price_in": 0.41,
        "price_out": 0.83,
        "aa_slug": "deepseek-v4-pro",
        "lm_slug": "deepseek-v4-pro",
        "or_slug": "deepseek/deepseek-v4-pro",
        "base_metrics": {
            "lm_elo": 1375,
            "lm_coding": 1415,
            "lm_hard": 1395,
            "aa_quality": 89.0,
            "aa_coding": 91.0,
            "aa_reasoning": 92.0,
            "speed_tps": 38.0,
        },
    },
    "deepseek-v4-flash": {
        "display": "DeepSeek V4 Flash",
        "provider": "DeepSeek",
        "pool": "ocgo",
        "tier": "Tier 2 — Default / Mid",
        "sub_cost": "OC Go ($30 usage / 7,558 req/5h)",
        "price_in": 0.06,
        "price_out": 0.11,
        "aa_slug": "deepseek-v4-flash",
        "lm_slug": "deepseek-v4-flash",
        "or_slug": "deepseek/deepseek-v4-flash",
        "base_metrics": {
            "lm_elo": 1335,
            "lm_coding": 1360,
            "lm_hard": 1330,
            "aa_quality": 83.0,
            "aa_coding": 85.0,
            "aa_reasoning": 84.0,
            "speed_tps": 95.0,
        },
    },
    "mimo-v2.5": {
        "display": "MiMo-V2.5",
        "provider": "Xiaomi",
        "pool": "ocgo",
        "tier": "Tier 3 — Bulk Fill",
        "sub_cost": "OC Go ($60 usage / 30,075 req/5h)",
        "price_in": 0.14,
        "price_out": 0.28,
        "aa_slug": "mimo-v2-5",
        "lm_slug": "mimo-v2.5",
        "or_slug": "xiaomi/mimo-v2.5",
        "base_metrics": {
            "lm_elo": 1315,
            "lm_coding": 1335,
            "lm_hard": 1300,
            "aa_quality": 80.5,
            "aa_coding": 82.0,
            "aa_reasoning": 79.5,
            "speed_tps": 115.0,
        },
    },
    "gpt-5.6-luna": {
        "display": "GPT 5.6 Luna",
        "provider": "OpenAI / Zen",
        "pool": "ocgo",
        "tier": "Tier 4 — Failover Heavy",
        "sub_cost": "OC Go ($15 usage / 2,049 req/5h)",
        "price_in": 0.20,
        "price_out": 1.20,
        "aa_slug": "gpt-5-6-luna",
        "lm_slug": "gpt-5.6-luna",
        "or_slug": "openai/gpt-5.6-luna",
        "base_metrics": {
            "lm_elo": 1365,
            "lm_coding": 1395,
            "lm_hard": 1375,
            "aa_quality": 88.0,
            "aa_coding": 89.5,
            "aa_reasoning": 90.0,
            "speed_tps": 60.0,
        },
    },
    "qwen3.8-max": {
        "display": "Qwen3.8 Max",
        "provider": "Alibaba",
        "pool": "ocgo",
        "tier": "Tier 1 — High Reasoning",
        "sub_cost": "OC Go ($15 usage / 162 req/5h)",
        "price_in": 2.00,
        "price_out": 6.00,
        "aa_slug": "qwen3-8-max",
        "lm_slug": "qwen3.8-max",
        "or_slug": "qwen/qwen3.8-max",
        "base_metrics": {
            "lm_elo": 1368,
            "lm_coding": 1395,
            "lm_hard": 1375,
            "aa_quality": 88.2,
            "aa_coding": 89.8,
            "aa_reasoning": 90.5,
            "speed_tps": 40.0,
        },
    },
    "minimax-m3": {
        "display": "MiniMax M3",
        "provider": "MiniMax",
        "pool": "ocgo",
        "tier": "Tier 2 — General",
        "sub_cost": "OC Go ($60 usage / 3,208 req/5h)",
        "price_in": 0.30,
        "price_out": 1.20,
        "aa_slug": "minimax-m3",
        "lm_slug": "minimax-m3",
        "or_slug": "minimax/minimax-m3",
        "base_metrics": {
            "lm_elo": 1338,
            "lm_coding": 1360,
            "lm_hard": 1340,
            "aa_quality": 84.0,
            "aa_coding": 85.5,
            "aa_reasoning": 85.0,
            "speed_tps": 75.0,
        },
    },
    "mimo-v2.5-pro": {
        "display": "MiMo V2.5 Pro",
        "provider": "MiniMax",
        "pool": "ocgo",
        "tier": "Tier 2 — General Executor",
        "sub_cost": "OC Go ($15 usage / 198 req/5h)",
        "price_in": 0.50,
        "price_out": 1.50,
        "aa_slug": "mimo-v2-5-pro",
        "lm_slug": "mimo-v2.5-pro",
        "or_slug": "minimax/mimo-v2.5-pro",
        "base_metrics": {
            "lm_elo": 1350,
            "lm_coding": 1360,
            "lm_hard": 1340,
            "aa_quality": 85.0,
            "aa_coding": 85.0,
            "aa_reasoning": 85.0,
            "speed_tps": 60.0,
        },
    },
    "qwen3.7-plus": {
        "display": "Qwen3.7 Plus",
        "provider": "Alibaba",
        "pool": "ocgo",
        "tier": "Tier 2 — General Executor",
        "sub_cost": "OC Go ($15 usage / 198 req/5h)",
        "price_in": 0.50,
        "price_out": 1.50,
        "aa_slug": "qwen3-7-plus",
        "lm_slug": "qwen3.7-plus",
        "or_slug": "qwen/qwen3.7-plus",
        "base_metrics": {
            "lm_elo": 1350,
            "lm_coding": 1360,
            "lm_hard": 1340,
            "aa_quality": 85.0,
            "aa_coding": 85.0,
            "aa_reasoning": 85.0,
            "speed_tps": 60.0,
        },
    },
    "kimi-k2.7-code": {
        "display": "Kimi K2.7 Code",
        "provider": "Moonshot AI",
        "pool": "ocgo",
        "tier": "Tier 2 — General Executor",
        "sub_cost": "OC Go ($15 usage / 198 req/5h)",
        "price_in": 0.50,
        "price_out": 1.50,
        "aa_slug": "kimi-k2-7-code",
        "lm_slug": "kimi-k2.7-code",
        "or_slug": "moonshot/kimi-k2.7-code",
        "base_metrics": {
            "lm_elo": 1350,
            "lm_coding": 1360,
            "lm_hard": 1340,
            "aa_quality": 85.0,
            "aa_coding": 85.0,
            "aa_reasoning": 85.0,
            "speed_tps": 60.0,
        },
    },
    "hy3": {
        "display": "Hunyuan 3",
        "provider": "Tencent",
        "pool": "ocgo",
        "tier": "Tier 2 — General Executor",
        "sub_cost": "OC Go ($15 usage / 198 req/5h)",
        "price_in": 0.50,
        "price_out": 1.50,
        "aa_slug": "hy3",
        "lm_slug": "hy3",
        "or_slug": "tencent/hy3",
        "base_metrics": {
            "lm_elo": 1350,
            "lm_coding": 1360,
            "lm_hard": 1340,
            "aa_quality": 85.0,
            "aa_coding": 85.0,
            "aa_reasoning": 85.0,
            "speed_tps": 60.0,
        },
    },
    "glm-5.2": {
        "display": "GLM-5.2",
        "provider": "Zhipu AI",
        "pool": "ocgo",
        "tier": "Tier 2 — General Executor",
        "sub_cost": "OC Go ($15 usage / 198 req/5h)",
        "price_in": 0.50,
        "price_out": 1.50,
        "aa_slug": "glm-5-2",
        "lm_slug": "glm-5.2",
        "or_slug": "z-ai/glm-5.2",
        "base_metrics": {
            "lm_elo": 1350,
            "lm_coding": 1360,
            "lm_hard": 1340,
            "aa_quality": 85.0,
            "aa_coding": 85.0,
            "aa_reasoning": 85.0,
            "speed_tps": 60.0,
        },
    },
    "longcat-2.0": {
        "display": "LongCat 2.0 (Meituan)",
        "provider": "Meituan",
        "pool": "ocgo",
        "tier": "Tier 3 — Long-Context / Bulk Fill",
        "sub_cost": "OC Go ($60 usage / 11.4k req/5h)",
        "price_in": 0.30,
        "price_out": 1.20,
        "aa_slug": "longcat-2-0",
        "lm_slug": "longcat-2.0",
        "or_slug": "meituan/longcat-2.0",
        "base_metrics": {
            "lm_elo": 1335,
            "lm_coding": 1340,
            "lm_hard": 1310,
            "aa_quality": 81.0,
            "aa_coding": 82.0,
            "aa_reasoning": 80.0,
            "speed_tps": 42.0,
        },
    },
    # --- Other Frontier & High-Ranking Models ---
    "gpt-5.6-sol": {
        "display": "GPT-5.6 Sol (Reasoning Flagship)",
        "provider": "OpenAI",
        "pool": "frontier",
        "tier": "Frontier Flagship Reasoning",
        "sub_cost": "API ($2.00 / $10.00)",
        "price_in": 2.00,
        "price_out": 10.00,
        "aa_slug": "gpt-5-6-sol",
        "lm_slug": "gpt-5.6-sol",
        "or_slug": "openai/gpt-5.6-sol",
        "base_metrics": {
            "lm_elo": 1430,
            "lm_coding": 1515,
            "lm_hard": 1460,
            "aa_quality": 95.8,
            "aa_coding": 96.8,
            "aa_reasoning": 97.2,
            "speed_tps": 45.0,
        },
    },
    "gpt-5.4-pro": {
        "display": "GPT-5.4 Pro",
        "provider": "OpenAI",
        "pool": "frontier",
        "tier": "Enterprise Agentic Flagship",
        "sub_cost": "API ($30.00 / $180.00)",
        "price_in": 30.00,
        "price_out": 180.00,
        "aa_slug": "gpt-5-4-pro",
        "lm_slug": "gpt-5.4-pro",
        "or_slug": "openai/gpt-5.4-pro",
        "base_metrics": {
            "lm_elo": 1425,
            "lm_coding": 1480,
            "lm_hard": 1440,
            "aa_quality": 95.0,
            "aa_coding": 95.5,
            "aa_reasoning": 95.8,
            "speed_tps": 36.0,
        },
    },
    "gpt-5.2-codex": {
        "display": "GPT-5.2 Codex",
        "provider": "OpenAI",
        "pool": "frontier",
        "tier": "Coding Specialist / Agent",
        "sub_cost": "API ($1.75 / $14.00)",
        "price_in": 1.75,
        "price_out": 14.00,
        "aa_slug": "gpt-5-2-codex",
        "lm_slug": "gpt-5.2-codex",
        "or_slug": "openai/gpt-5.2-codex",
        "base_metrics": {
            "lm_elo": 1390,
            "lm_coding": 1465,
            "lm_hard": 1410,
            "aa_quality": 91.5,
            "aa_coding": 94.0,
            "aa_reasoning": 92.0,
            "speed_tps": 62.0,
        },
    },
    "gpt-oss-120b": {
        "display": "GPT-OSS 120B (Medium)",
        "provider": "OpenAI / Open-Weights",
        "pool": "frontier",
        "tier": "Open High-Efficiency",
        "sub_cost": "Open-Weights / API ($0.04 / $0.17)",
        "price_in": 0.04,
        "price_out": 0.17,
        "aa_slug": "gpt-oss-120b",
        "lm_slug": "gpt-oss-120b",
        "or_slug": "openai/gpt-oss-120b",
        "base_metrics": {
            "lm_elo": 1350,
            "lm_coding": 1380,
            "lm_hard": 1345,
            "aa_quality": 86.5,
            "aa_coding": 87.5,
            "aa_reasoning": 86.0,
            "speed_tps": 110.0,
        },
    },
    "gpt-5.5": {
        "display": "GPT 5.5 (xHigh)",
        "provider": "OpenAI",
        "pool": "frontier",
        "tier": "Frontier Agentic Reasoning",
        "sub_cost": "API ($5.00 / $30.00)",
        "price_in": 5.00,
        "price_out": 30.00,
        "aa_slug": "gpt-5-5",
        "lm_slug": "gpt-5-5-xhigh",
        "or_slug": "openai/gpt-5.5",
        "base_metrics": {
            "lm_elo": 1428,
            "lm_coding": 1500,
            "lm_hard": 1450,
            "aa_quality": 95.5,
            "aa_coding": 96.0,
            "aa_reasoning": 96.5,
            "speed_tps": 40.0,
        },
    },
    "grok-4.5": {
        "display": "Grok 4.5",
        "provider": "xAI",
        "pool": "frontier",
        "tier": "Frontier Agentic / Reasoning",
        "sub_cost": "API ($2.00 / $6.00)",
        "price_in": 2.00,
        "price_out": 6.00,
        "aa_slug": "grok-4-5",
        "lm_slug": "grok-4.5",
        "or_slug": "x-ai/grok-4.5",
        "base_metrics": {
            "lm_elo": 1395,
            "lm_coding": 1435,
            "lm_hard": 1415,
            "aa_quality": 92.0,
            "aa_coding": 93.0,
            "aa_reasoning": 94.0,
            "speed_tps": 50.0,
        },
    },
    "qwen3-coder": {
        "display": "Qwen3 Coder 480B",
        "provider": "Alibaba",
        "pool": "frontier",
        "tier": "Open Coding Specialist",
        "sub_cost": "Open-Weights / API ($0.30 / $1.00)",
        "price_in": 0.30,
        "price_out": 1.00,
        "aa_slug": "qwen3-coder",
        "lm_slug": "qwen3-coder",
        "or_slug": "qwen/qwen3-coder",
        "base_metrics": {
            "lm_elo": 1372,
            "lm_coding": 1450,
            "lm_hard": 1390,
            "aa_quality": 89.5,
            "aa_coding": 93.0,
            "aa_reasoning": 88.5,
            "speed_tps": 80.0,
        },
    },
}

# ==============================================================================
# 2. LIVE FETCHERS, SNAPSHOTS & PARSERS
# ==============================================================================

LIVEBENCH_URL = "https://livebench.ai"
LIVEBENCH_CSV_URL = "https://livebench.ai/table_2026_06_25.csv"
LIVEBENCH_CAT_URL = "https://livebench.ai/categories_2026_06_25.json"
LMARENA_URL = "https://arena.ai/leaderboard"
AA_URL = "https://artificialanalysis.ai/leaderboards/models"
CACHE_TTL_H = bc.CACHE_TTL_H  # canonical 24h freshness window lives in benchmark_common (rule 7)


# Trailing effort/tier hyphen-tokens stripped for LiveBench base-name matching
# (LiveBench lists one row per effort tier). Deliberately EXCLUDES model-variant
# tokens (pro/mini/nano/lite/codex/...) — those are distinct models, not tiers.
LIVEBENCH_TIER_TOKENS = frozenset({
    "effort", "max", "xhigh", "high", "medium", "low", "minimal",
    "nothinking", "thinking", "preview", "auto", "base",
})


def livebench_base_name(s):
    """Strip trailing effort/tier tokens: 'claude-opus-5-max-effort' -> 'claude-opus-5'."""
    toks = (s or "").split("-")
    while toks and toks[-1] in LIVEBENCH_TIER_TOKENS:
        toks.pop()
    return "-".join(toks)


def find_livebench(model_id_or_dict, live_map):
    """Version-safe matching for LiveBench models.

    Stages per candidate slug, first hit wins:
      1. Exact normalized match.
      2. Tier-base match: LiveBench lists many flagships ONLY under effort/tier
         suffixes (-max-effort, -preview-high); link via the tier-stripped base
         name, best overall per base.
      3. Variant fallback: shared token-safe matcher (S2-C2).
    Miss at every stage => caller keeps the static catalog value.
    """
    if not live_map:
        return None
    if isinstance(model_id_or_dict, dict):
        cands = [
            model_id_or_dict.get("lm_slug"),
            model_id_or_dict.get("aa_slug"),
            model_id_or_dict.get("or_slug"),
            model_id_or_dict.get("display"),
        ]
    else:
        cands = [model_id_or_dict]

    base_map = {}
    for k, v in live_map.items():
        kb = norm_model_slug(livebench_base_name(k))
        if not kb or v.get("overall") is None:
            continue
        cur = base_map.get(kb)
        if cur is None or v["overall"] > cur["overall"]:
            base_map[kb] = v

    for c in cands:
        if not c:
            continue
        cn = norm_model_slug(c)
        if not cn:
            continue
        # 1. Exact match
        for k, v in live_map.items():
            if norm_model_slug(k) == cn:
                return v
        # 2. Tier-base match (best overall per stripped base)
        rec = base_map.get(cn)
        if rec is not None:
            return rec
        # 3. Variant fallback: shared token-safe matcher (S2-C2); None => static value kept.
        qn = bc.norm_id(c)
        for k, v in live_map.items():
            if not bc.variant_conflict(qn, bc.norm_id(k)) and v.get("overall") is not None:
                return v
    return None


def find_lmarena(model_id_or_dict, lm_map):
    """Version-safe matching for LMArena / Arena.ai models."""
    if not lm_map:
        return None
    if isinstance(model_id_or_dict, dict):
        cands = [
            model_id_or_dict.get("lm_slug"),
            model_id_or_dict.get("aa_slug"),
            model_id_or_dict.get("or_slug"),
            model_id_or_dict.get("display"),
        ]
    else:
        cands = [model_id_or_dict]

    for c in cands:
        if not c:
            continue
        cn = norm_model_slug(c)
        if not cn:
            continue
        # 1. Exact match
        for k, v in lm_map.items():
            if norm_model_slug(k) == cn:
                return v
        # 2. Variant fallback: shared token-safe matcher (S2-C2); None => static value kept.
        qn = bc.norm_id(c)
        for k, v in lm_map.items():
            if not bc.variant_conflict(qn, bc.norm_id(k)) and v.get("elo") is not None:
                return v
    return None


def find_aa(model_id_or_dict, aa_map):
    """Version-safe matching for Artificial Analysis models."""
    if not aa_map:
        return None
    if isinstance(model_id_or_dict, dict):
        cands = [
            model_id_or_dict.get("aa_slug"),
            model_id_or_dict.get("lm_slug"),
            model_id_or_dict.get("or_slug"),
            model_id_or_dict.get("display"),
        ]
    else:
        cands = [model_id_or_dict]

    for c in cands:
        if not c:
            continue
        cn = norm_model_slug(c)
        if not cn:
            continue
        # 1. Exact match
        for k, v in aa_map.items():
            if norm_model_slug(k) == cn:
                return v
        # 2. Variant fallback: shared token-safe matcher (S2-C2); None => static value kept.
        qn = bc.norm_id(c)
        for k, v in aa_map.items():
            if not bc.variant_conflict(qn, bc.norm_id(k)) and v.get("intelligenceIndex") is not None:
                return v
    return None


def fetch_url(url, timeout=15):
    """Fetch URL with browser user agent."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception:
        return None


def load_livebench_data(verbose=False, fetch=False):
    """Load LiveBench from the 24h response cache (docs/data/raw/) — no network by default.

    fetch: pull the live CSV + categories and save them to data/raw/ as
    livebench_YYYYMMDD.csv / livebench_categories_YYYYMMDD.json (skipped when
    today's snapshot already exists).
    """
    out = {}
    csv_matches = sorted(glob.glob(str(RAW / "*livebench*20*.csv")))
    for p_csv in csv_matches:
        if "cost" in p_csv:
            continue
        try:
            p = pathlib.Path(p_csv)
            date_part = "".join(filter(str.isdigit, p.stem))
            cat_p = RAW / f"livebench_categories_{date_part}.json"
            cat_json = cat_p.read_text(encoding="utf-8", errors="ignore") if cat_p.exists() else None
            data = parse_livebench(p.read_text(encoding="utf-8", errors="ignore"), categories_json=cat_json)
            out.update(data)
        except Exception:
            pass
    if fetch:
        try:
            csv_text = fetch_url(LIVEBENCH_CSV_URL)
            cat_text = fetch_url(LIVEBENCH_CAT_URL)
            if csv_text:
                if fetch:
                    stamp = dt.date.today().isoformat().replace("-", "")
                    s_csv = RAW / f"livebench_{stamp}.csv"
                    if not s_csv.exists():
                        bc.atomic_write_text(s_csv, csv_text)
                        print(f"  saved LiveBench -> {s_csv.relative_to(ROOT)} ({len(csv_text)} bytes)")
                    if cat_text:
                        s_cat = RAW / f"livebench_categories_{stamp}.json"
                        if not s_cat.exists():
                            bc.atomic_write_text(s_cat, cat_text)
                            print(f"  saved LiveBench categories -> {s_cat.relative_to(ROOT)} ({len(cat_text)} bytes)")
                live_data = parse_livebench(csv_text, categories_json=cat_text, verbose=verbose)
                out.update(live_data)
        except Exception as e:  # noqa: BLE001 — never swallow silently (S2-C1)
            print(f"  WARN LiveBench fetch/save failed: {e}", file=sys.stderr)
    return out


def load_lmarena_data(verbose=False, fetch=False):
    """Load LMArena / Arena.ai data from the 24h response cache (data/raw/), or live with fetch=True."""
    out = {}
    matches = sorted(glob.glob(str(RAW / "*lmarena*20*.html")))
    for p_html in matches:
        try:
            p = pathlib.Path(p_html)
            data = parse_lmarena(p.read_text(encoding="utf-8", errors="ignore"), verbose=verbose)
            out.update(data)
        except Exception:
            pass
    if fetch:
        try:
            html_txt = fetch_url(LMARENA_URL)
            if html_txt:
                if fetch:
                    stamp = dt.date.today().isoformat().replace("-", "")
                    s = RAW / f"lmarena_{stamp}.html"
                    if not s.exists():
                        bc.atomic_write_text(s, html_txt)
                        print(f"  saved LMArena -> {s.relative_to(ROOT)} ({len(html_txt)} bytes)")
                live_data = parse_lmarena(html_txt, verbose=verbose)
                out.update(live_data)
        except Exception as e:  # noqa: BLE001 — never swallow silently (S2-C1)
            print(f"  WARN LMArena fetch/save failed: {e}", file=sys.stderr)
    return out


def load_aa_data(verbose=False, fetch=False):
    """Load Artificial Analysis data from the 24h response cache (data/raw/), or live with fetch=True."""
    out = {}
    matches = sorted(glob.glob(str(RAW / "*artificial_analysis*20*.html")))
    for p_html in matches:
        try:
            p = pathlib.Path(p_html)
            data = parse_aa(p.read_text(encoding="utf-8", errors="ignore"), verbose=verbose)
            out.update(data)
        except Exception:
            pass
    if fetch:
        try:
            html_txt = fetch_url(AA_URL)
            if html_txt:
                if fetch:
                    stamp = dt.date.today().isoformat().replace("-", "")
                    s = RAW / f"artificial_analysis_{stamp}.html"
                    if not s.exists():
                        bc.atomic_write_text(s, html_txt)
                        print(f"  saved Artificial Analysis -> {s.relative_to(ROOT)} ({len(html_txt)} bytes)")
                live_data = parse_aa(html_txt, verbose=verbose)
                out.update(live_data)
        except Exception as e:  # noqa: BLE001 — never swallow silently (S2-C1)
            print(f"  WARN Artificial Analysis fetch/save failed: {e}", file=sys.stderr)
    return out


def newest_snapshot_age_h(pattern):
    """Hours since the newest docs/data/raw/ snapshot matching `pattern`; None when none exists.

    Age keys on the _YYYYMMDD date embedded in the filename when present — a
    fresh clone/checkout rewrites mtimes and would mask weeks-old data (S2-M2);
    mtime is only the fallback for date-less files.
    """
    matches = glob.glob(str(RAW / pattern))
    if not matches:
        return None
    return min(bc.snapshot_age_hours(p) for p in matches)


def cache_staleness_note():
    """Staleness warning for the default offline run: sources with no cache or cache older than CACHE_TTL_H."""
    parts = []
    for name, pat in (
        ("LiveBench", "*livebench*20*.csv"),
        ("LMArena", "*lmarena*20*.html"),
        ("Artificial Analysis", "*artificial_analysis*20*.html"),
    ):
        age = newest_snapshot_age_h(pat)
        if age is None:
            parts.append(f"{name} missing")
        elif age > CACHE_TTL_H:
            parts.append(f"{name} {age:.0f}h old")
    if not parts:
        return ""
    return "cached responses >24h — run with --fetch: " + ", ".join(parts)


def _z_scores(values: list) -> list:
    """Z-scores with None passthrough: missing stays None (never cohort-mean 0.0).

    Callers renormalize the weighted sum over present signals only, so a model
    without a signal is scored on what it actually has instead of banking the
    cohort mean at full weight.
    """
    valid = [v for v in values if isinstance(v, (int, float))]
    if len(valid) < 2:
        return [0.0 if isinstance(v, (int, float)) else None for v in values]
    mean_val = statistics.mean(valid)
    std_val = statistics.stdev(valid)
    if std_val == 0.0:
        std_val = 1.0
    return [(v - mean_val) / std_val if isinstance(v, (int, float)) else None for v in values]


def calculate_composite_scores(models_dict):
    """
    Computes:
      1. Normalized Composite Capability Q ∈ [40.0, 99.9] across Arena, AA, and LiveBench.
      2. Task Success Probability P_succ(Q) modeling the capability threshold floor.
      3. Hidden Token Multiplier T_mult(Q) accounting for retry / debug token burn.
      4. Effective Cost E_cost ($/M) per successfully verified task.
      5. Multi-Tier Value Indices:
         - AVI (Agentic Value Index): Balanced capability vs effective cost ROI.
         - FGI (Frontier Gate Index): High-difficulty architectural gating.
         - BFI (Bulk Fill Index): Throughput & raw cost efficiency on bounded tasks.

    Missing signals are EXCLUDED from the weighted sum and the surviving weights
    renormalized — never banked at the cohort mean.
    """
    keys = list(models_dict.keys())
    m_list = [models_dict[k] for k in keys]

    # AA live intelligenceIndex/codingIndex use a NEW scale vs the static catalog's
    # retired old-AA-Quality-Index seeds (~93-96): never mix the two cohorts in one
    # z-distribution. Prefer the live cohort when any live match exists; fall back
    # to the uniform static cohort only when the whole catalog is offline-static.
    # ponytail: AA live/static cohort split <- old-vs-new scale drift -> remove split when AA restores a unified live quality index
    live_q = [m.get("aa_live_quality") for m in m_list]
    if any(v is not None for v in live_q):
        z_aa_qual = _z_scores(live_q)
    else:
        z_aa_qual = _z_scores([m["base_metrics"].get("aa_quality") for m in m_list])
    live_c = [m.get("aa_live_coding") for m in m_list]
    if any(v is not None for v in live_c):
        z_aa_cod = _z_scores(live_c)
    else:
        z_aa_cod = _z_scores([m["base_metrics"].get("aa_coding") for m in m_list])
    z_lm_elo = _z_scores([m["base_metrics"].get("lm_elo") for m in m_list])
    z_lm_cod = _z_scores([m["base_metrics"].get("lm_coding") for m in m_list])
    z_aa_reas = _z_scores([m["base_metrics"].get("aa_reasoning") for m in m_list])  # static for ALL: no live AA equivalent, uniform scale
    z_live = _z_scores([
        m.get("livebench", {}).get("overall") if isinstance(m.get("livebench"), dict) else (m.get("livebench") if isinstance(m.get("livebench"), (int, float)) else None)
        for m in m_list
    ])

    signals = (
        (0.125, z_lm_elo),
        (0.125, z_lm_cod),
        (0.150, z_aa_qual),
        (0.125, z_aa_cod),
        (0.125, z_aa_reas),
        (0.175, z_live),
    )

    for i, k in enumerate(keys):
        m = models_dict[k]
        num = 0.0
        den = 0.0
        for weight, zs in signals:
            z = zs[i]
            if z is None:
                continue
            num += weight * z
            den += weight
        cz = num / den if den else 0.0
        q_score = compute_capability_q(cz)
        m["composite_score"] = q_score
        m["capability_q"] = q_score

        p_succ_pct = compute_p_success(q_score)
        m["p_success"] = p_succ_pct

        t_mult = compute_token_multiplier(p_succ_pct)
        m["token_multiplier"] = t_mult

        pin = float(m.get("price_in", 0.0))
        pout = float(m.get("price_out", 0.0))
        blended_price = (0.80 * pin) + (0.20 * pout)
        m["blended_price"] = round(blended_price, 2)
        effective_cost = compute_effective_cost(blended_price, t_mult)
        m["effective_cost"] = effective_cost

        m["avi_score"] = compute_avi(q_score, effective_cost)
        m["fgi_score"] = compute_fgi(q_score, p_succ_pct)

        speed = float(m["base_metrics"].get("speed_tps", 60.0))
        m["bfi_score"] = compute_bfi(q_score, speed, blended_price)


def format_compact_price(p_in, p_out):
    """Format prompt and completion price compactly e.g. $5/$25 or $0.41/$0.83."""
    def fmt(v):
        if v is None:
            return "—"
        if v == 0:
            return "$0"
        if v >= 1.0:
            return f"${v:.0f}" if v.is_integer() else f"${v:.1f}" if round(v * 10, 2).is_integer() else f"${v:.2f}"
        return f"${v:.2f}"
    return f"{fmt(p_in)}/{fmt(p_out)}"


BCHECK_COL_MEDAL_KEYS = {
    "q": (lambda m: m.get("capability_q", 0), True, None),
    "psucc": (lambda m: m.get("p_success", 0), True, None),
    "eff_cost": (lambda m: m.get("effective_cost", 999), False, None),
    "avi": (lambda m: m.get("avi_score", 0), True, None),
    "fgi": (lambda m: m.get("fgi_score", 0), True, None),
    "live": (lambda m: m.get("livebench", {}).get("overall", 0) if isinstance(m.get("livebench"), dict) and isinstance(m.get("livebench", {}).get("overall"), (int, float)) else 0, True, lambda m: isinstance(m.get("livebench"), dict) and isinstance(m.get("livebench", {}).get("overall"), (int, float))),
    "arena": (lambda m: m["base_metrics"].get("lm_elo", 0), True, lambda m: isinstance(m["base_metrics"].get("lm_elo"), (int, float))),
    "speed": (lambda m: m["base_metrics"].get("speed_tps", 0), True, lambda m: isinstance(m["base_metrics"].get("speed_tps"), (int, float))),
    "price": (lambda m: m.get("blended_price", 999), False, None),
}


def render_cli_table(models_list, color=None, slim=None, wide=False, pareto_ids=None, added_ids=None, removed_models=None, stale_note=None):
    """Render structured TUI table with adaptive terminal width and alternating row zebra striping."""
    if color is None:
        color = not os.getenv("NO_COLOR")

    if pareto_ids is None:
        pareto_ids = compute_pareto_frontier(models_list)

    if added_ids is None:
        added_ids = set()
    if removed_models is None:
        removed_models = []

    col_medals = compute_column_medals(models_list, BCHECK_COL_MEDAL_KEYS, id_key="display")

    # Adaptive width detection (detect split panes or small windows)
    term_cols = shutil.get_terminal_size((120, 24)).columns
    is_slim = slim if slim is not None else (term_cols < 120 and not wide)

    out = []

    # Table Column Dimensions
    if is_slim:
        headers = [
            ("Rank", 4, "^"),
            ("Model", 20, "<"),
            ("Pool", 5, "^"),
            ("Q(Cap)", 6, ">"),
            ("P(Succ)", 7, ">"),
            ("Eff $/M", 8, ">"),
            ("AVI", 6, ">"),
            ("FGI", 5, ">"),
            ("Live%", 6, ">"),
        ]
    else:
        headers = [
            ("Rank", 4, "^"),
            ("Model", 22, "<"),
            ("Pool", 5, "^"),
            ("Q(Cap)", 6, ">"),
            ("P(Succ)", 7, ">"),
            ("Eff $/M", 8, ">"),
            ("AVI", 6, ">"),
            ("FGI", 5, ">"),
            ("Live%", 6, ">"),
            ("Arena", 6, ">"),
            ("Speed", 7, ">"),
            ("Price", 12, ">"),
        ]

    total_models = len(models_list)
    top_frontier = max(models_list, key=lambda m: m.get("fgi_score", 0)) if models_list else None
    top_avi = max(models_list, key=lambda m: m.get("avi_score", 0)) if models_list else None
    top_speed = max(models_list, key=lambda m: m["base_metrics"].get("speed_tps", 0)) if models_list else None

    # Total inner width between outer box borders
    inner_w = sum(w + 2 for _, w, _ in headers) + len(headers) - 1

    # 1. Executive Summary Banner
    title_str = "⚡ AGENTIC BENCHMARK & COST-BENEFIT RADAR (Arena.ai · LiveBench · AA)"
    f_info = f"Frontier: {top_frontier['display'][:14]} (FGI {top_frontier.get('fgi_score', 0):.1f})" if top_frontier else ""
    v_info = f"Top ROI: {top_avi['display'][:14]} (AVI {top_avi.get('avi_score', 0):.1f})" if top_avi else ""
    s_info = f"Fastest: {top_speed['display'][:12]} ({top_speed['base_metrics'].get('speed_tps', 0):.0f}t/s)" if top_speed else ""
    if is_slim:
        summary_str = f" Tracked: {total_models} models │ {f_info} │ {v_info}"
    else:
        summary_str = f" Tracked: {total_models} models │ {f_info} │ {v_info} │ {s_info}"

    diff_notices = []
    diff_parts = []
    if added_ids:
        diff_notices.append(f"{C_BOLD}{C_GREEN}✨ New (+{len(added_ids)}): {', '.join(sorted(added_ids))}{C_RESET}")
        diff_parts.append(f"[+NEW (+{len(added_ids)}): {', '.join(sorted(added_ids))}]")
    if removed_models:
        rem_names = [m.get("display") or m.get("model_id", "unknown") for m in removed_models]
        diff_notices.append(f"{C_BOLD}{C_RED}🔻 Removed (-{len(removed_models)}): {', '.join(rem_names)}{C_RESET}")
        diff_parts.append(f"[-REMOVED (-{len(removed_models)}): {', '.join(rem_names)}]")
    if stale_note:
        diff_notices.append(f"{C_BOLD}{C_YELLOW}⚠ {stale_note}{C_RESET}")
        diff_parts.append(f"[!] {stale_note}")

    out.extend(render_banner_box(
        title_str,
        summary_lines=[summary_str],
        diff_notices=diff_notices,
        inner_w=inner_w,
        color=color,
        plain_title_line=f" AGENTIC BENCHMARK & COST-BENEFIT RADAR (LiveBench · Arena · AA) — Tracked: {total_models} models",
        plain_diff_parts=diff_parts,
    ))

    # Border templates
    if color:
        top_border = "┌" + "┬".join("─" * (w + 2) for _, w, _ in headers) + "┐"
        mid_border = "├" + "┼".join("─" * (w + 2) for _, w, _ in headers) + "┤"
        bot_border = "└" + "┴".join("─" * (w + 2) for _, w, _ in headers) + "┘"

        out.append(f"{C_DIM}{top_border}{C_RESET}")
        hdr_cells = [color_cell(h, C_BOLD + C_WHITE, width=w, align=a, bg=BG_HEADER) for h, w, a in headers]
        out.append(f"{BG_HEADER}{C_DIM}│{C_RESET}" + f"{BG_HEADER}{C_DIM}│{C_RESET}".join(hdr_cells) + f"{BG_HEADER}{C_DIM}│{C_RESET}")
        out.append(f"{C_DIM}{mid_border}{C_RESET}")
    else:
        out.append("-" * (inner_w + 2))
        hdr_str = " ".join([f"{h:^{w}}" if a == "^" else (f"{h:>{w}}" if a == ">" else f"{h:<{w}}") for h, w, a in headers])
        out.append(hdr_str)
        out.append("-" * (inner_w + 2))

    # 3. Data Rows with Alternating Zebra Striping
    for idx, m in enumerate(models_list):
        rank_num = idx + 1
        bg = BG_ODD if (idx % 2 == 1) else BG_EVEN

        if rank_num == 1:
            rank_str = "🥇#1"
        elif rank_num == 2:
            rank_str = "🥈#2"
        elif rank_num == 3:
            rank_str = "🥉#3"
        else:
            rank_str = f" #{rank_num}"

        bm = m["base_metrics"]
        m_name_w = 20 if is_slim else 22
        is_added = (m.get("display") in added_ids) or (m.get("model_id") in added_ids) or (m.get("or_slug") in added_ids) or (m.get("aa_slug") in added_ids)
        raw_mid = m["display"]
        mid = f"+{raw_mid}"[:m_name_w] if is_added else raw_mid[:m_name_w]
        pool = m["pool"].upper()
        pool_badge_str = pool_badge(m["pool"], color=color)

        is_pareto = (m.get("display") in pareto_ids) or (m.get("aa_slug") in pareto_ids) or (raw_mid in pareto_ids)

        meds = col_medals.get(m["display"], {})
        q_badge = medal_badge(meds.get("q"), color=color)
        psucc_badge = medal_badge(meds.get("psucc"), color=color)
        eff_badge = medal_badge(meds.get("eff_cost"), color=color)
        avi_badge = medal_badge(meds.get("avi"), color=color)
        fgi_badge = medal_badge(meds.get("fgi"), color=color)
        live_badge = medal_badge(meds.get("live"), color=color)
        arena_badge = medal_badge(meds.get("arena"), color=color)
        speed_badge = medal_badge(meds.get("speed"), color=color)
        price_badge = medal_badge(meds.get("price"), color=color)

        q_val = m.get("capability_q", 0)
        p_val = m.get("p_success", 0)
        eff_cost = m.get("effective_cost", 0)
        avi = m.get("avi_score", 0)
        fgi = m.get("fgi_score", 0)
        lb = m.get("livebench", {})
        lb_res = lb.get("overall") if isinstance(lb, dict) else (lb if isinstance(lb, (int, float)) else None)
        lcod = bm.get("lm_coding", "-")
        elo = bm.get("lm_elo", "-")
        spd = bm.get("speed_tps", "-")
        pin = m.get("price_in", 0.0)
        pout = m.get("price_out", 0.0)
        price_str = format_compact_price(pin, pout)

        q_disp = f"{q_val:.1f}" + q_badge
        p_disp = f"{p_val:.1f}%" + psucc_badge
        eff_disp = f"${eff_cost:.2f}" + eff_badge
        avi_disp = f"{avi:.1f}" + avi_badge
        fgi_disp = f"{fgi:.1f}" + fgi_badge
        lb_disp = (f"{lb_res:.1f}%" if isinstance(lb_res, (int, float)) else "—") + live_badge
        elo_disp = (f"{int(elo)}" if isinstance(elo, (int, float)) else f"{elo}") + arena_badge
        spd_disp = (f"{spd:.0f}t/s" if isinstance(spd, (int, float)) else f"{spd}") + speed_badge
        price_disp = price_str + price_badge

        if color:
            if is_added:
                mid_color = C_BOLD + C_GREEN
            elif is_pareto:
                mid_color = (C_BOLD + C_GOLD)
            else:
                mid_color = C_WHITE

            q_color = score_color_q(q_val)
            p_color = score_color_p(p_val)
            eff_color = C_GREEN if eff_cost < 2.0 else (C_CYAN if eff_cost < 10.0 else (C_YELLOW if eff_cost < 25.0 else C_MAGENTA))
            avi_color = score_color_avi(avi)
            fgi_color = score_color_fgi(fgi)
            lb_color = C_GREEN if (isinstance(lb_res, (int, float)) and lb_res >= 78.0) else (C_CYAN if (isinstance(lb_res, (int, float)) and lb_res >= 70.0) else (C_YELLOW if (isinstance(lb_res, (int, float)) and lb_res >= 60.0) else C_GRAY))
            elo_color = C_GREEN if (isinstance(elo, (int, float)) and elo >= 1480) else (C_CYAN if (isinstance(elo, (int, float)) and elo >= 1440) else (C_YELLOW if (isinstance(elo, (int, float)) and elo >= 1400) else C_GRAY))
            spd_color = C_GREEN if (isinstance(spd, (int, float)) and spd >= 100) else (C_CYAN if (isinstance(spd, (int, float)) and spd >= 60) else C_WHITE)

            row_cells = [
                color_cell(rank_str, C_BOLD + (C_GOLD if rank_num == 1 else (C_SILVER if rank_num == 2 else (C_BRONZE if rank_num == 3 else C_WHITE))), width=4, align="^", bg=bg),
                color_cell(mid, mid_color, width=m_name_w, align="<", bg=bg),
                color_cell(pool_badge_str, "", width=5, align="^", bg=bg),
                color_cell(q_disp, q_color, width=6, align=">", bg=bg),
                color_cell(p_disp, p_color, width=7, align=">", bg=bg),
                color_cell(eff_disp, eff_color, width=8, align=">", bg=bg),
                color_cell(avi_disp, avi_color, width=6, align=">", bg=bg),
                color_cell(fgi_disp, fgi_color, width=5, align=">", bg=bg),
                color_cell(lb_disp, lb_color, width=6, align=">", bg=bg),
            ]
            if not is_slim:
                row_cells.extend([
                    color_cell(elo_disp, elo_color, width=6, align=">", bg=bg),
                    color_cell(spd_disp, spd_color, width=7, align=">", bg=bg),
                    color_cell(price_disp, C_DIM, width=12, align=">", bg=bg),
                ])
            out.append(f"{bg}{C_DIM}│{C_RESET}" + f"{bg}{C_DIM}│{C_RESET}".join(row_cells) + f"{bg}{C_DIM}│{C_RESET}")
        else:
            row_items = [
                f"{rank_str:^4}",
                f"{mid:<{m_name_w}}",
                f"{pool_badge_str:^5}",
                f"{q_disp:>6}",
                f"{p_disp:>7}",
                f"{eff_disp:>8}",
                f"{avi_disp:>6}",
                f"{fgi_disp:>5}",
                f"{lb_disp:>6}",
            ]
            if not is_slim:
                row_items.extend([
                    f"{elo_disp:>6}",
                    f"{spd_disp:>7}",
                    f"{price_disp:>12}",
                ])
            out.append(" ".join(row_items))

    if color:
        out.append(f"{C_DIM}{bot_border}{C_RESET}")
    else:
        out.append("-" * (inner_w + 2))

    # Removed models display
    if removed_models:
        out.append("")
        out.extend(render_removed_models_cli(removed_models, color=color, is_slim=is_slim, id_key="display"))

    out.append("")
    out.extend(render_metric_guide_cli(
        "Metric Decision Guide",
        [
            ("Gold Bold", "Pareto Frontier (undefeated capability vs cost curve).", C_GOLD),
            ("Green (+)", "Newly added benchmark model vs previous baseline snapshot.", C_GREEN),
            ("Badges ¹²³", "🥇/🥈/🥉 place leaders in respective column.", C_YELLOW),
            ("Q(Cap)", "Capability (40–99.9) across Arena, LiveBench, AA.", C_GREEN),
            ("FGI", "Frontier Gate Index (Q·P^1.5): High-stakes plan/architect gates.", C_GREEN),
            ("AVI", "Agentic Value Index (Q^2.2 / log Cost): Daily-driver loop ROI.", C_GREEN),
            ("Eff $/M", "Real Cost/Task: Price × retry multiplier (T_mult).", C_GREEN),
            ("P(Succ)", "Estimated 1-turn pass rate (<40% = high multi-file risk).", C_GREEN),
            ("Live", "LiveBench coding % · decontaminated overall.", C_GREEN),
        ],
        color=color,
    ))

    role_recs = compute_role_recommendations(models_list, context="bcheck")
    if role_recs:
        out.append("")
        out.extend(render_role_recommendations_cli(role_recs, color=color, is_slim=is_slim, width=inner_w))

    return "\n".join(out)


def render_podium_table(models_list, color=None):
    """Render top 3 winners podium table across all key columns and metrics."""
    if color is None:
        color = not os.getenv("NO_COLOR")

    cols = [
        ("Q(Cap) — Capability", lambda m: m.get("capability_q", 0), True, None, lambda m: f"{m.get('capability_q', 0):.1f}"),
        ("FGI — Architectural Gate", lambda m: m.get("fgi_score", 0), True, None, lambda m: f"{m.get('fgi_score', 0):.1f}"),
        ("AVI — Daily Driver ROI", lambda m: m.get("avi_score", 0), True, None, lambda m: f"{m.get('avi_score', 0):.1f}"),
        ("LiveBench — Decontam.", lambda m: m.get("livebench", {}).get("overall", 0) if isinstance(m.get("livebench"), dict) and isinstance(m.get("livebench", {}).get("overall"), (int, float)) else 0, True, lambda m: isinstance(m.get("livebench"), dict) and isinstance(m.get("livebench", {}).get("overall"), (int, float)), lambda m: f"{m.get('livebench', {}).get('overall'):.1f}%"),
        ("Arena.ai — Global Elo", lambda m: m["base_metrics"].get("lm_elo", 0), True, lambda m: isinstance(m["base_metrics"].get("lm_elo"), (int, float)), lambda m: f"{int(m['base_metrics'].get('lm_elo'))}"),
        ("Coding Elo — LMSYS Arena", lambda m: m["base_metrics"].get("lm_coding", 0), True, lambda m: isinstance(m["base_metrics"].get("lm_coding"), (int, float)), lambda m: f"{int(m['base_metrics'].get('lm_coding'))}"),
        ("Speed — Throughput", lambda m: m["base_metrics"].get("speed_tps", 0), True, lambda m: isinstance(m["base_metrics"].get("speed_tps"), (int, float)), lambda m: f"{int(m['base_metrics'].get('speed_tps'))} t/s"),
        ("Eff $/M — Real Task Cost", lambda m: m.get("effective_cost", 999), False, None, lambda m: f"${m.get('effective_cost', 0):.2f}"),
        ("Price — Blended $/M", lambda m: m.get("blended_price", 999), False, None, lambda m: f"${m.get('blended_price', 0):.2f}"),
        ("P(Succ) — Pass Rate", lambda m: m.get("p_success", 0), True, None, lambda m: f"{m.get('p_success', 0):.1f}%"),
    ]

    headers = [
        ("Metric / Column", 26, "<"),
        ("🥇 1st Place (Gold)", 30, "<"),
        ("🥈 2nd Place (Silver)", 30, "<"),
        ("🥉 3rd Place (Bronze)", 30, "<"),
    ]
    inner_w = sum(w + 2 for _, w, _ in headers) + len(headers) - 1

    out = []
    if color:
        top_box = f"{C_GOLD}╭" + ("─" * inner_w) + f"╮{C_RESET}"
        bot_box = f"{C_GOLD}╰" + ("─" * inner_w) + f"╯{C_RESET}"
        title = "🏆 COLUMN WINNERS & PODIUM LEADERS (1st 🥇 · 2nd 🥈 · 3rd 🥉)"
        out.append(top_box)
        clean_title = title + (" " * max(0, inner_w - 2 - display_len(title)))
        out.append(f"{C_GOLD}│{C_RESET} {C_BOLD}{C_WHITE}{clean_title}{C_RESET} {C_GOLD}│{C_RESET}")
        out.append(bot_box)
        out.append("")

        top_border = "┌" + "┬".join("─" * (w + 2) for _, w, _ in headers) + "┐"
        mid_border = "├" + "┼".join("─" * (w + 2) for _, w, _ in headers) + "┤"
        bot_border = "└" + "┴".join("─" * (w + 2) for _, w, _ in headers) + "┘"

        out.append(f"{C_DIM}{top_border}{C_RESET}")
        hdr_cells = [color_cell(h, C_BOLD + C_WHITE, width=w, align=a, bg=BG_HEADER) for h, w, a in headers]
        out.append(f"{BG_HEADER}{C_DIM}│{C_RESET}" + f"{BG_HEADER}{C_DIM}│{C_RESET}".join(hdr_cells) + f"{BG_HEADER}{C_DIM}│{C_RESET}")
        out.append(f"{C_DIM}{mid_border}{C_RESET}")

        for idx, (col_label, key_fn, rev, filt, fmt_fn) in enumerate(cols):
            bg = BG_ODD if (idx % 2 == 1) else BG_EVEN
            valid = [m for m in models_list if filt(m)] if filt else models_list
            sorted_m = sorted(valid, key=key_fn, reverse=rev)[:3]

            row_cells = [color_cell(col_label, C_BOLD + C_CYAN, width=26, align="<", bg=bg)]
            medal_colors = [C_GOLD, C_SILVER, C_BRONZE]
            for pos in range(3):
                if pos < len(sorted_m):
                    m = sorted_m[pos]
                    val = fmt_fn(m)
                    p_badge = pool_badge(m["pool"], color=False)
                    disp_name = m["display"][:16]
                    txt = f"{disp_name} {p_badge} ({val})"
                    colr = medal_colors[pos]
                else:
                    txt = "—"
                    colr = C_GRAY
                row_cells.append(color_cell(txt, colr, width=30, align="<", bg=bg))

            out.append(f"{bg}{C_DIM}│{C_RESET}" + f"{bg}{C_DIM}│{C_RESET}".join(row_cells) + f"{bg}{C_DIM}│{C_RESET}")
        out.append(f"{C_DIM}{bot_border}{C_RESET}")
    else:
        out.append("=" * (inner_w + 2))
        out.append(" COLUMN WINNERS & PODIUM LEADERS (1st 🥇 · 2nd 🥈 · 3rd 🥉)")
        out.append("=" * (inner_w + 2))
        hdr_str = " ".join([f"{h:<{w}}" for h, w, a in headers])
        out.append(hdr_str)
        out.append("-" * (inner_w + 2))
        for idx, (col_label, key_fn, rev, filt, fmt_fn) in enumerate(cols):
            valid = [m for m in models_list if filt(m)] if filt else models_list
            sorted_m = sorted(valid, key=key_fn, reverse=rev)[:3]
            row_items = [f"{col_label:<26}"]
            for pos in range(3):
                if pos < len(sorted_m):
                    m = sorted_m[pos]
                    val = fmt_fn(m)
                    p_badge = pool_badge(m["pool"], color=False)
                    disp_name = m["display"][:16]
                    txt = f"{disp_name} {p_badge} ({val})"
                else:
                    txt = "—"
                row_items.append(f"{txt:<30}")
            out.append(" ".join(row_items))
    return "\n".join(out)


def render_markdown_report(models_list, title=None, pareto_ids=None):
    """Render detailed Markdown report."""
    if pareto_ids is None:
        pareto_ids = compute_pareto_frontier(models_list)

    if not title:
        title = f"Consolidated LLM Benchmark & Agentic Cost-Benefit Report ({dt.date.today().isoformat()})"

    lines = [
        f"# {title}\n",
        f"Consolidated capability & cost-efficiency benchmark across **OpenCode Go**, **AGY Subscription (Gemini)**, **Claude Subscription (Anthropic)**, and **Frontier API Models** across Arena.ai, LiveBench (https://livebench.ai), and Artificial Analysis.",
        "",
        "## 1. Master Agentic Value & Capability Leaderboard",
        "",
        "| Model | Pool / Tier | Q (Cap) | P(Succ) | Eff. $/M | AVI (Value) | FGI (Gate) | LiveBench (%) | Coding Elo | Speed | Raw $/M |",
        "| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]

    for m in models_list:
        bm = m["base_metrics"]
        mid_raw = m['display']
        is_pareto = (mid_raw in pareto_ids) or (m.get("aa_slug") in pareto_ids) or (mid_raw[:22] in pareto_ids) or (mid_raw[:20] in pareto_ids)
        mid = f"⭐ **{mid_raw}**" if is_pareto else f"**{mid_raw}**"
        sub = f"`{m['pool'].upper()}` ({m['tier']})"
        q = f"**{m.get('capability_q', 0):.1f}**"
        psucc = f"{m.get('p_success', 0):.1f}%"
        eff_cost = f"${m.get('effective_cost', 0):.2f}"
        avi = f"**{m.get('avi_score', 0):.1f}**"
        fgi = f"{m.get('fgi_score', 0):.1f}"
        lb = m.get("livebench", {})
        lb_res = lb.get("overall") if isinstance(lb, dict) else (lb if isinstance(lb, (int, float)) else None)
        lb_str = f"{lb_res:.1f}%" if isinstance(lb_res, (int, float)) else "—"
        lcod = f"{bm.get('lm_coding', '—')}"
        spd = f"{bm.get('speed_tps', '—'):.0f} t/s" if isinstance(bm.get('speed_tps'), (int, float)) else "—"
        cost = f"${m['price_in']:.2f} / ${m['price_out']:.2f}"

        lines.append(
            f"| {mid} | {sub} | {q} | {psucc} | {eff_cost} | {avi} | {fgi} | {lb_str} | {lcod} | {spd} | {cost} |"
        )

    podium_cols = [
        ("Q(Cap) — Composite Capability", lambda m: m.get("capability_q", 0), True, None, lambda m: f"{m.get('capability_q', 0):.1f}"),
        ("FGI — Architectural Gate Index", lambda m: m.get("fgi_score", 0), True, None, lambda m: f"{m.get('fgi_score', 0):.1f}"),
        ("AVI — Agentic Value Index (ROI)", lambda m: m.get("avi_score", 0), True, None, lambda m: f"{m.get('avi_score', 0):.1f}"),
        ("LiveBench (%) — Decontaminated", lambda m: m.get("livebench", {}).get("overall", 0) if isinstance(m.get("livebench"), dict) and isinstance(m.get("livebench", {}).get("overall"), (int, float)) else 0, True, lambda m: isinstance(m.get("livebench"), dict) and isinstance(m.get("livebench", {}).get("overall"), (int, float)), lambda m: f"{m.get('livebench', {}).get('overall'):.1f}%"),
        ("Arena.ai Elo — Global Arena", lambda m: m["base_metrics"].get("lm_elo", 0), True, lambda m: isinstance(m["base_metrics"].get("lm_elo"), (int, float)), lambda m: f"{int(m['base_metrics'].get('lm_elo'))}"),
        ("Coding Elo — LMSYS Arena", lambda m: m["base_metrics"].get("lm_coding", 0), True, lambda m: isinstance(m["base_metrics"].get("lm_coding"), (int, float)), lambda m: f"{int(m['base_metrics'].get('lm_coding'))}"),
        ("Speed — Generation Throughput", lambda m: m["base_metrics"].get("speed_tps", 0), True, lambda m: isinstance(m["base_metrics"].get("speed_tps"), (int, float)), lambda m: f"{int(m['base_metrics'].get('speed_tps'))} t/s"),
        ("Eff $/M — Real Solved Task Cost", lambda m: m.get("effective_cost", 999), False, None, lambda m: f"${m.get('effective_cost', 0):.2f}"),
        ("Price — Blended Raw Cost", lambda m: m.get("blended_price", 999), False, None, lambda m: f"${m.get('blended_price', 0):.2f}"),
        ("P(Succ) (%) — 1-Turn Pass Rate", lambda m: m.get("p_success", 0), True, None, lambda m: f"{m.get('p_success', 0):.1f}%"),
    ]

    lines.extend([
        "",
        "## 2. Column Winners & Podium Leaders (1st 🥇 · 2nd 🥈 · 3rd 🥉)",
        "",
        "| Metric / Column | 🥇 1st Place (Gold) | 🥈 2nd Place (Silver) | 🥉 3rd Place (Bronze) |",
        "| :--- | :--- | :--- | :--- |",
    ])
    for col_label, key_fn, rev, filt, fmt_fn in podium_cols:
        valid = [m for m in models_list if filt(m)] if filt else models_list
        sorted_m = sorted(valid, key=key_fn, reverse=rev)[:3]
        places = []
        for pos in range(3):
            if pos < len(sorted_m):
                m = sorted_m[pos]
                val = fmt_fn(m)
                p_badge = pool_badge(m["pool"], color=False)
                places.append(f"**{m['display']}** `{p_badge}` ({val})")
            else:
                places.append("—")
        lines.append(f"| **{col_label}** | {places[0]} | {places[1]} | {places[2]} |")

    role_recs = compute_role_recommendations(models_list, context="bcheck")
    if role_recs:
        lines.extend([
            "",
            "## 3. Dynamic Function & Role Recommendations (Weighted Scoring)",
            "",
            render_role_recommendations_md(role_recs),
        ])

    lines.extend([
        "",
        "## 4. Key Insights & Routing Architecture",
        "",
        "- **⭐ Pareto Frontier Models**: Undefeated efficiency and top cost-to-capability curve (e.g. Claude Opus 5, GPT-5.6 Sol, Gemini 3.7 Flash, DeepSeek V4 Flash, GPT-OSS 120B).",
        "- **Tier 1: Architectural Gates & Complex Debugging (High FGI)**: **Claude Fable 5** (LiveBench 83.4%), **Claude Opus 5 (Thinking)** (LiveBench 80.5%), and **Gemini 3.7 Flash Thinking** (LiveBench 79.9%) lead uncontaminated general coding and reasoning.",
        "- **Tier 2: Workhorse Multi-Turn Loops (High AVI ROI)**: **Gemini 3.7 Flash Thinking** (AVI 421.9, Eff. $1.04/M) and **DeepSeek V4 Flash** (AVI 538.9, Eff. $0.21/M) deliver maximal intelligence per dollar without suffering token explosion.",
        "- **Tier 3: Bulk Fill & Fast Search (High BFI)**: **MiMo-V2.5** and **DeepSeek V4 Flash** provide ultra-fast mechanical token generation.",
        "- **The Token Multiplier Effect**: Sub-70 capability models incur up to 4.5x token burn from multi-turn retries, turning cheap base prices into high effective costs per solved task.",
        "",
        f"_Generated by `benchmarks_check.py` (`bcheck`) on {dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}._",
    ])
    return "\n".join(lines)


def render_html_report(models_list, pareto_ids=None, added_ids=None, removed_models=None, stale_note=None):
    """Render standalone HTML dashboard."""
    if pareto_ids is None:
        pareto_ids = compute_pareto_frontier(models_list)

    if added_ids is None:
        added_ids = set()
    if removed_models is None:
        removed_models = []

    role_recs = compute_role_recommendations(models_list, context="bcheck")
    role_recs_html = render_role_recommendations_html(role_recs) if role_recs else ""

    trs = []
    for m in models_list:
        bm = m["base_metrics"]
        mid_raw = m['display']
        is_added = (mid_raw in added_ids) or (m.get("model_id") in added_ids) or (m.get("or_slug") in added_ids) or (m.get("aa_slug") in added_ids)
        is_pareto = (mid_raw in pareto_ids) or (m.get("aa_slug") in pareto_ids) or (mid_raw[:22] in pareto_ids) or (mid_raw[:20] in pareto_ids)
        pool_cls = {"claude": "badge-cld", "agy": "badge-agy", "ocgo": "badge-ocg", "frontier": "badge-frt"}.get(m["pool"], "")

        lb = m.get("livebench", {})
        lb_res = lb.get("overall") if isinstance(lb, dict) else (lb if isinstance(lb, (int, float)) else None)
        lb_str = f"{lb_res:.1f}%" if isinstance(lb_res, (int, float)) else "—"

        name_html = html.escape(m['display'])
        if is_added:
            name_html = f"<span style='color:#10b981; font-weight:700;'>+{name_html}</span> <span class='badge badge-new'>+NEW</span>"
        elif is_pareto:
            name_html = f"<span style='color:#d29922; font-weight:700;'>{name_html}</span> <span style='background:rgba(210,153,34,0.18); color:#d29922; border:1px solid #d29922; padding:1px 5px; border-radius:3px; font-size:10px; font-weight:600;'>PARETO</span>"

        row_cls_parts = []
        if is_added:
            row_cls_parts.append("added")
        if is_pareto:
            row_cls_parts.append("pareto")
        row_cls = f" class='{' '.join(row_cls_parts)}'" if row_cls_parts else ""

        trs.append(f"""
        <tr{row_cls}>
            <td style="font-weight:600;">{name_html}</td>
            <td><span class="badge {pool_cls}">{m['pool'].upper()}</span></td>
            <td>{html.escape(m['tier'])}</td>
            <td style="font-weight:700; color:#2563eb;">{m.get('capability_q', 0):.1f}</td>
            <td>{m.get('p_success', 0):.1f}%</td>
            <td>${m.get('effective_cost', 0):.2f}</td>
            <td style="font-weight:700; color:#10b981;">{m.get('avi_score', 0):.1f}</td>
            <td style="font-weight:700; color:#8b5cf6;">{m.get('fgi_score', 0):.1f}</td>
            <td style="font-weight:600; color:#f59e0b;">{lb_str}</td>
            <td>{bm.get('lm_coding', '—')}</td>
            <td>{bm.get('speed_tps', '—')} t/s</td>
            <td>${m['price_in']:.2f} / ${m['price_out']:.2f}</td>
        </tr>
        """)

    podium_cols = [
        ("Q(Cap) — Capability", lambda m: m.get("capability_q", 0), True, None, lambda m: f"{m.get('capability_q', 0):.1f}"),
        ("FGI — Architectural Gate", lambda m: m.get("fgi_score", 0), True, None, lambda m: f"{m.get('fgi_score', 0):.1f}"),
        ("AVI — Daily Driver ROI", lambda m: m.get("avi_score", 0), True, None, lambda m: f"{m.get('avi_score', 0):.1f}"),
        ("LiveBench — Decontam.", lambda m: m.get("livebench", {}).get("overall", 0) if isinstance(m.get("livebench"), dict) and isinstance(m.get("livebench", {}).get("overall"), (int, float)) else 0, True, lambda m: isinstance(m.get("livebench"), dict) and isinstance(m.get("livebench", {}).get("overall"), (int, float)), lambda m: f"{m.get('livebench', {}).get('overall'):.1f}%"),
        ("Arena.ai — Global Elo", lambda m: m["base_metrics"].get("lm_elo", 0), True, lambda m: isinstance(m["base_metrics"].get("lm_elo"), (int, float)), lambda m: f"{int(m['base_metrics'].get('lm_elo'))}"),
        ("Coding Elo — LMSYS Arena", lambda m: m["base_metrics"].get("lm_coding", 0), True, lambda m: isinstance(m["base_metrics"].get("lm_coding"), (int, float)), lambda m: f"{int(m['base_metrics'].get('lm_coding'))}"),
        ("Speed — Throughput", lambda m: m["base_metrics"].get("speed_tps", 0), True, lambda m: isinstance(m["base_metrics"].get("speed_tps"), (int, float)), lambda m: f"{int(m['base_metrics'].get('speed_tps'))} t/s"),
        ("Eff $/M — Real Task Cost", lambda m: m.get("effective_cost", 999), False, None, lambda m: f"${m.get('effective_cost', 0):.2f}"),
        ("Price — Blended $/M", lambda m: m.get("blended_price", 999), False, None, lambda m: f"${m.get('blended_price', 0):.2f}"),
        ("P(Succ) — Pass Rate", lambda m: m.get("p_success", 0), True, None, lambda m: f"{m.get('p_success', 0):.1f}%"),
    ]

    podium_trs = []
    for col_label, key_fn, rev, filt, fmt_fn in podium_cols:
        valid = [m for m in models_list if filt(m)] if filt else models_list
        sorted_m = sorted(valid, key=key_fn, reverse=rev)[:3]
        cells = []
        for pos in range(3):
            if pos < len(sorted_m):
                m = sorted_m[pos]
                val = fmt_fn(m)
                p_badge = pool_badge(m["pool"], color=False)
                cells.append(f"<b>{html.escape(m['display'])}</b> <small style='color:#94a3b8;'>{p_badge}</small> <span style='color:#f59e0b;'>({val})</span>")
            else:
                cells.append("—")
        podium_trs.append(f"""
        <tr>
            <td style="font-weight:600; color:#38bdf8;">{col_label}</td>
            <td>{cells[0]}</td>
            <td>{cells[1]}</td>
            <td>{cells[2]}</td>
        </tr>
        """)

    removed_html = ""
    if removed_models:
        rem_tags = []
        for rm in removed_models:
            rm_id = html.escape(rm.get("display") or rm.get("model_id", "unknown"))
            pool_str = rm.get("pool", "").upper()
            fgi = rm.get("fgi_score") or rm.get("benchmarks", {}).get("fgi_score")
            fgi_s = f"FGI {fgi:.1f}" if isinstance(fgi, (int, float)) else "FGI —"
            avi = rm.get("avi_score") or rm.get("benchmarks", {}).get("avi_score")
            avi_s = f"AVI {avi:.1f}" if isinstance(avi, (int, float)) else "AVI —"
            rem_tags.append(f'<span class="removed-tag">❌ <b>{rm_id}</b> <span class="mid">({pool_str}, {fgi_s}, {avi_s})</span></span>')
        removed_html = f"""
        <div class="removed-section">
          <div class="removed-title">🔻 Removed / Deprecated Benchmark Models ({len(removed_models)})</div>
          <div class="sub" style="margin-bottom:8px;">These models were present in the previous benchmark catalog snapshot but are no longer active in the current benchmark leaderboard:</div>
          <div>{''.join(rem_tags)}</div>
        </div>
        """

    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Consolidated LLM Benchmark & Agentic Cost-Benefit Dashboard</title>
    <style>{HTML_CSS_COMMON}</style>
</head>
<body>
<div class="wrap">
    <h1>Consolidated LLM Benchmark & Agentic Cost-Benefit Dashboard</h1>
    <div class="sub">Arena.ai · LiveBench (https://livebench.ai) · Agentic Value Index (AVI)</div>
    {f'<div class="legend">⚠ {html.escape(stale_note)}</div>' if stale_note else ""}

    <h2>1. Master Agentic Value Leaderboard</h2>
    <table id="tbl">
        <thead>
            <tr>
                <th>Model</th>
                <th>Pool</th>
                <th>Role / Tier</th>
                <th>Q (Cap)</th>
                <th>P(Succ)</th>
                <th>Eff $/M</th>
                <th>AVI (ROI)</th>
                <th>FGI (Gate)</th>
                <th>LiveBench</th>
                <th>Coding Elo</th>
                <th>Speed</th>
                <th>Price In/Out</th>
            </tr>
        </thead>
        <tbody>
            {''.join(trs)}
        </tbody>
    </table>

    <h2>2. Column Winners & Podium Leaders (1st 🥇 · 2nd 🥈 · 3rd 🥉)</h2>
    <table>
        <thead>
            <tr>
                <th>Metric / Column</th>
                <th>🥇 1st Place (Gold)</th>
                <th>🥈 2nd Place (Silver)</th>
                <th>🥉 3rd Place (Bronze)</th>
            </tr>
        </thead>
        <tbody>
            {''.join(podium_trs)}
        </tbody>
    </table>

    {removed_html}

    {role_recs_html}
</div>
{HTML_SORT_SCRIPT}
</body>
</html>
"""


def save_baseline(models_list, catalog_diff, path=None):
    """Persist the NEW/REMOVED baseline (with first_seen) that drives the 7-day green window."""
    p = pathlib.Path(path) if path else (DATA / "benchmarks.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "catalog_diff": {
            "added": sorted(str(x) for x in catalog_diff["added_ids"]),
            "removed": sorted(str(x) for x in catalog_diff["removed_ids"]),
            "total_current": len(models_list),
        },
        "models": models_list,
    }
    bc.atomic_write_text(p, json.dumps(payload, indent=2))
    return p


# ==============================================================================
# 4. MAIN CLI LOGIC
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Consolidate benchmarks across OpenCode Go, AGY, Claude, and Frontier models."
    )
    parser.add_argument(
        "--pool",
        choices=["all", "accessible", "my-pools", "post-claude", "ocgo", "agy", "claude", "frontier"],
        default="all",
        help="Filter by subscription ecosystem (default: all)",
    )
    parser.add_argument(
        "--sort",
        choices=["avi", "fgi", "bfi", "composite", "coding", "reasoning", "live", "speed", "price", "effective_cost"],
        default="composite",
        help="Sort criterion (default: composite)",
    )
    parser.add_argument("--podium", "--winners", action="store_true", help="Display top 3 winners podium table across every metric/column")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    parser.add_argument("--md", type=str, nargs="?", const="stdout", help="Output Markdown report")
    parser.add_argument("--html", type=str, nargs="?", const="docs/reports/benchmarks.html", help="Generate HTML dashboard")
    parser.add_argument("--fetch", "--refresh", action="store_true",
                        help="Refresh the 24h response cache now: fetch LiveBench/LMArena/Artificial Analysis live, save dated snapshots to docs/data/raw/, and update the benchmarks.json NEW baseline. Default runs fully offline on cache.")
    parser.add_argument("--plain", "--no-color", action="store_true", help="Disable ANSI colors and box drawing")
    parser.add_argument("--slim", action="store_true", help="Force compact 95-column table layout (for split panes)")
    parser.add_argument("--wide", action="store_true", help="Force full 125-column table layout")

    args = parser.parse_args()

    do_fetch = bool(args.fetch)

    # Load LiveBench from 24h response cache (or live + refresh cache with --fetch)
    live_map = load_livebench_data(fetch=do_fetch)
    if live_map:
        for mid, m in MODELS_CATALOG.items():
            rec = find_livebench(m, live_map)
            if rec and rec.get("overall") is not None:
                m["livebench"] = rec

    # Load LMArena / Arena.ai live or snapshot data
    lm_map = load_lmarena_data(fetch=do_fetch)
    if lm_map:
        for mid, m in MODELS_CATALOG.items():
            rec = find_lmarena(m, lm_map)
            if rec and rec.get("elo"):
                m["base_metrics"]["lm_elo"] = rec["elo"]

    # Load Artificial Analysis live or snapshot data
    aa_map = load_aa_data(fetch=do_fetch)
    if aa_map:
        for mid, m in MODELS_CATALOG.items():
            rec = find_aa(m, aa_map)
            if not rec:
                continue
            # aa_reasoning has no live AA equivalent since AA retired its unified
            # reasoning index in favor of raw sub-benchmarks (gpqa/hle/critpt/...);
            # left as static catalog data.
            bm = m["base_metrics"]
            if rec.get("intelligenceIndex") is not None:
                bm["aa_quality"] = rec["intelligenceIndex"]
                m["aa_live_quality"] = rec["intelligenceIndex"]  # new-scale live value marker for cohort-split z-scoring
            if rec.get("codingIndex") is not None:
                bm["aa_coding"] = rec["codingIndex"]
                m["aa_live_coding"] = rec["codingIndex"]
            if rec.get("medianTps") is not None:
                bm["speed_tps"] = rec["medianTps"]

    calculate_composite_scores(MODELS_CATALOG)

    models = list(MODELS_CATALOG.values())

    # Diffing + baseline run catalog-wide BEFORE --pool view filtering: a subset baseline would
    # fake-REMOVE every model excluded by the current view.
    prev_snapshot = load_previous_snapshot(DATA / "benchmarks.json")
    catalog_diff = diff_model_catalog(models, prev_snapshot, id_key="display")
    added_ids = catalog_diff["added_ids"]
    removed_models = catalog_diff["removed_models"]
    if do_fetch:
        p = save_baseline(models, catalog_diff)
        print(f"  updated NEW-baseline -> {p.relative_to(ROOT)}")
    stale_note = cache_staleness_note()

    if args.pool in ("accessible", "my-pools"):
        models = [m for m in models if m["pool"] in ("claude", "agy", "ocgo")]
    elif args.pool == "post-claude":
        models = [m for m in models if m["pool"] in ("agy", "ocgo")]
    elif args.pool != "all":
        models = [m for m in models if m["pool"] == args.pool]

    if args.sort == "composite":
        models.sort(key=lambda m: m.get("composite_score", 0), reverse=True)
    elif args.sort == "avi":
        models.sort(key=lambda m: m.get("avi_score", 0), reverse=True)
    elif args.sort == "fgi":
        models.sort(key=lambda m: m.get("fgi_score", 0), reverse=True)
    elif args.sort == "bfi":
        models.sort(key=lambda m: m.get("bfi_score", 0), reverse=True)
    elif args.sort == "coding":
        models.sort(key=lambda m: m["base_metrics"].get("lm_coding", 0), reverse=True)
    elif args.sort == "reasoning":
        models.sort(key=lambda m: m["base_metrics"].get("aa_reasoning", 0), reverse=True)
    elif args.sort == "speed":
        models.sort(key=lambda m: m["base_metrics"].get("speed_tps", 0), reverse=True)
    elif args.sort == "live":
        models.sort(key=lambda m: (m.get("livebench", {}).get("overall") if isinstance(m.get("livebench"), dict) else (m.get("livebench") or 0)), reverse=True)
    elif args.sort == "price":
        models.sort(key=lambda m: m.get("price_in", 999))
    elif args.sort == "effective_cost":
        models.sort(key=lambda m: m.get("effective_cost", 999))

    if args.json:
        print(json.dumps(models, indent=2))
        return

    if args.md:
        md_text = render_markdown_report(models)
        if args.md == "stdout":
            print(md_text)
        else:
            p = pathlib.Path(args.md)
            bc.atomic_write_text(p, md_text)
            print(f"Wrote Markdown report to {args.md}")
        return

    if args.html:
        html_text = render_html_report(models, added_ids=added_ids, removed_models=removed_models, stale_note=stale_note)
        p = pathlib.Path(args.html)
        bc.atomic_write_text(p, html_text)
        print(f"Wrote HTML dashboard to {args.html}")
        return

    use_color = False if args.plain else None
    if args.podium:
        print(render_podium_table(models, color=use_color))
        return

    slim_opt = True if args.slim else (False if args.wide else None)
    print(render_cli_table(models, color=use_color, slim=slim_opt, wide=args.wide, added_ids=added_ids, removed_models=removed_models, stale_note=stale_note))


if __name__ == "__main__":
    main()
