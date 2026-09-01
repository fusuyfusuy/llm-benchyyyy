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
        "tier": "Flagship Reasoning / Complex Gates",
        "sub_cost": "Claude Pro / Team / Max",
        "price_in": 5.00,
        "price_out": 25.00,
        "live_aliases": ["claude-opus-5-max-effort", "claude-opus-5"],
        "lm_aliases": ["opus-5-high", "claude-opus-5-high", "claude-opus-5"],
        "aa_aliases": ["claude-opus-5", "claude-opus-5-xhigh", "claude-opus-5-high", "claude-opus-5-medium", "claude-opus-5-low"],
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
        "live_aliases": ["claude-fable-5-max-effort", "claude-fable-5"],
        "lm_aliases": ["fable-5", "claude-fable-5"],
        "aa_aliases": ["claude-fable-5"],
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
    "claude-opus-4-8": {
        "display": "Claude Opus 4.8 (Thinking)",
        "provider": "Anthropic",
        "pool": "claude",
        "tier": "Lead Architecture / Reasoning",
        "sub_cost": "Claude Pro / AGY Bridge",
        "price_in": 5.00,
        "price_out": 25.00,
        "live_aliases": ["claude-opus-4-8-xhigh-effort", "claude-opus-4-8-max-effort", "claude-opus-4-8-high-effort", "claude-opus-4-8-medium-effort", "claude-opus-4-8-low-effort", "claude-opus-4-8"],
        "lm_aliases": ["opus-4-8", "claude-opus-4-8", "claude-opus-4-8-thinking"],
        "aa_aliases": ["claude-opus-4-8", "claude-opus-4-8-adaptive", "claude-opus-4-8-high", "claude-opus-4-8-medium"],
        "base_metrics": {
            "lm_elo": 1425,
            "lm_coding": 1505,
            "lm_hard": 1455,
            "aa_quality": 95.0,
            "aa_coding": 96.2,
            "aa_reasoning": 96.5,
            "speed_tps": 40.0,
        },
    },
    "claude-opus-4-7": {
        "display": "Claude Opus 4.7 (Thinking)",
        "provider": "Anthropic",
        "pool": "claude",
        "tier": "Lead Architecture / Reasoning",
        "sub_cost": "Claude Pro / AGY Bridge",
        "price_in": 5.00,
        "price_out": 25.00,
        "live_aliases": ["claude-opus-4-7-xhigh-effort", "claude-opus-4-7-high-effort", "claude-opus-4-7-medium-effort", "claude-opus-4-7-low-effort", "claude-opus-4-7"],
        "lm_aliases": ["opus-4-7", "claude-opus-4-7", "claude-opus-4-7-thinking"],
        "aa_aliases": ["claude-opus-4-7", "claude-opus-4-7-adaptive", "claude-opus-4-7-high", "claude-opus-4-7-medium", "claude-opus-4-7-non-reasoning"],
        "base_metrics": {
            "lm_elo": 1422,
            "lm_coding": 1500,
            "lm_hard": 1450,
            "aa_quality": 94.8,
            "aa_coding": 96.0,
            "aa_reasoning": 96.2,
            "speed_tps": 41.0,
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
        "live_aliases": ["claude-opus-4-6-thinking-auto-high-effort", "claude-opus-4-6"],
        "lm_aliases": ["opus-4-6", "claude-opus-4-6", "claude-opus-4-6-thinking"],
        "aa_aliases": ["claude-opus-4-6", "claude-opus-4-6-adaptive"],
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
        "live_aliases": ["claude-sonnet-5-xhigh-effort", "claude-sonnet-5"],
        "lm_aliases": ["claude-sonnet-5", "sonnet-5"],
        "aa_aliases": ["claude-sonnet-5"],
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
        "live_aliases": ["claude-sonnet-4-6-thinking-auto-high-effort", "claude-sonnet-4-6-thinking-auto-medium-effort", "claude-sonnet-4-6-thinking-auto-low-effort", "claude-sonnet-4-6"],
        "lm_aliases": ["claude-sonnet-4-6", "sonnet-4-6"],
        "aa_aliases": ["claude-sonnet-4-6", "claude-sonnet-4-6-thinking"],
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
        "live_aliases": ["claude-haiku-4-5-20251001-thinking-64k", "claude-haiku-4-5-20251001", "claude-haiku-4-5"],
        "lm_aliases": ["claude-haiku-4-5", "haiku-4-5"],
        "aa_aliases": ["claude-haiku-4-5"],
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
        "live_aliases": ["gemini-3.1-pro-preview-high", "gemini-3-1-pro"],
        "lm_aliases": ["gemini-3.1-pro", "gemini-3-1-pro", "gemini-3.1-pro-preview"],
        "aa_aliases": ["gemini-3-1-pro", "gemini-3.1-pro"],
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
        "live_aliases": ["gemini-3.7-flash-high", "gemini-3-7-flash-high", "gemini-3.7-flash", "gemini-3-7-flash"],
        "lm_aliases": ["gemini-3.7-flash", "gemini-3-7-flash", "gemini 3.7 flash (me", "gemini 3.7 flash (lo"],
        "aa_aliases": ["gemini-3-7-flash", "gemini-3.7-flash", "gemini-3-7-flash-thinking", "gemini-3-7-flash-medium", "gemini-3-7-flash-low"],
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
        "live_aliases": ["gemini-3.1-flash-lite-preview-high", "gemini-3-1-flash-lite"],
        "lm_aliases": ["gemini-3.1-flash-lite", "gemini-3-1-flash-lite"],
        "aa_aliases": ["gemini-3-1-flash-lite", "gemini-3.1-flash-lite"],
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
    # --- OpenAI & Frontier Subscription / API Models ---
    "gpt-5.6-sol": {
        "display": "GPT-5.6 Sol (Reasoning)",
        "provider": "OpenAI",
        "pool": "frontier",
        "tier": "Frontier Flagship Reasoning",
        "sub_cost": "API ($2.00 / $10.00)",
        "price_in": 2.00,
        "price_out": 10.00,
        "live_aliases": ["gpt-5.6-sol-max", "gpt-5-6-sol-max", "gpt-5-6-sol"],
        "lm_aliases": ["gpt-5-6-sol-xhighcodex-harness", "gpt-5-6-sol-xhighcodex", "gpt-5-6-sol", "gpt 5-6 sol-xhighcod"],
        "aa_aliases": ["gpt-5-6-sol", "gpt-5-6-sol-xhigh", "gpt-5-6-sol-high", "gpt-5-6-sol-medium", "gpt-5-6-sol-low"],
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
    "grok-4-6": {
        "display": "Grok 4.6 (Reasoning)",
        "provider": "xAI",
        "pool": "frontier",
        "tier": "Frontier Agentic Reasoning",
        "sub_cost": "API ($2.00 / $6.00)",
        "price_in": 2.00,
        "price_out": 6.00,
        "live_aliases": ["grok-4.6", "grok-4-6"],
        "lm_aliases": ["grok-4.6", "grok-4-6", "grok-4-0709"],
        "aa_aliases": ["grok-4-6", "grok-4-6-xhigh", "grok-4-6-high", "grok-4-6-medium", "grok-4-6-low"],
        "base_metrics": {
            "lm_elo": 1411,
            "lm_coding": 1460,
            "lm_hard": 1430,
            "aa_quality": 93.5,
            "aa_coding": 94.5,
            "aa_reasoning": 94.0,
            "speed_tps": 55.0,
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
        "live_aliases": ["gpt-5.5-xhigh", "gpt-5.5-high", "gpt-5-5-xhigh"],
        "lm_aliases": ["gpt-5-5-xhighcodex-harness", "gpt-5-5-highcodex-harness", "gpt-5-5", "gpt 5-5-xhighcodex-h", "gpt 5-5-highcodex-ha", "gpt 5-5-instant"],
        "aa_aliases": ["gpt-5-5"],
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
    "gpt-5-6-terra": {
        "display": "GPT-5.6 Terra (Reasoning)",
        "provider": "OpenAI",
        "pool": "frontier",
        "tier": "Frontier High-Capacity",
        "sub_cost": "API ($1.50 / $7.50)",
        "price_in": 1.50,
        "price_out": 7.50,
        "live_aliases": ["gpt-5.6-terra-max", "gpt-5-6-terra-max"],
        "lm_aliases": ["gpt-5-6-terra-xhighcodex-harness", "gpt-5-6-terra", "gpt 5-6-terra-xhighc"],
        "aa_aliases": ["gpt-5-6-terra", "gpt-5-6-terra-max", "gpt-5-6-terra-high", "gpt-5-6-terra-xhigh"],
        "base_metrics": {
            "lm_elo": 1405,
            "lm_coding": 1470,
            "lm_hard": 1425,
            "aa_quality": 92.5,
            "aa_coding": 93.5,
            "aa_reasoning": 94.0,
            "speed_tps": 50.0,
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
        "live_aliases": ["gpt-5.4-xhigh", "gpt-5.4-high"],
        "lm_aliases": ["gpt-5.4-pro", "gpt 5-4-highcodex-ha"],
        "aa_aliases": ["gpt-5.4-pro", "gpt-5-4"],
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
        "live_aliases": ["gpt-5.2-codex", "gpt-5.2-2025-12-11-high"],
        "lm_aliases": ["gpt-5.2-codex", "gpt-5.2"],
        "aa_aliases": ["gpt-5-2-codex", "gpt-5.2"],
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
        "live_aliases": ["gpt-oss-120b", "gpt-oss-120b-medium"],
        "lm_aliases": ["gpt-oss-120b", "gpt-oss-120b-medium"],
        "aa_aliases": ["gpt-oss-120b"],
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
    "grok-4.5": {
        "display": "Grok 4.5",
        "provider": "xAI",
        "pool": "frontier",
        "tier": "Frontier Agentic / Reasoning",
        "sub_cost": "API ($2.00 / $6.00)",
        "price_in": 2.00,
        "price_out": 6.00,
        "live_aliases": ["grok-4.5", "grok-4-5"],
        "lm_aliases": ["grok-4.5", "grok-4-5"],
        "aa_aliases": ["grok-4-5", "grok-4.5"],
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
        "live_aliases": ["qwen3-coder-480b", "qwen3-coder"],
        "lm_aliases": ["qwen3-coder-480b", "qwen3-coder"],
        "aa_aliases": ["qwen3-coder-480b", "qwen3-coder"],
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
    # --- Open / Upstream Top Benchmark Models ---
    "hunyuan-4-preview": {
        "display": "Hunyuan 4 Preview",
        "provider": "Tencent",
        "pool": "api",
        "tier": "Frontier Reasoning",
        "sub_cost": "API ($0.83 / $2.50)",
        "price_in": 0.834,
        "price_out": 2.501,
        "live_aliases": ["hy4-preview", "hunyuan-4-preview"],
        "lm_aliases": ["hy4-preview", "tencent-hy4-preview", "hunyuan-4-preview"],
        "aa_aliases": ["hy4-preview", "tencent-hy4-preview"],
        "base_metrics": {
            "lm_elo": 1420,
            "lm_coding": 1490,
            "speed_tps": 48.0,
        },
    },
    "qwen3.8-max": {
        "display": "Qwen3.8 Max",
        "provider": "Alibaba",
        "pool": "api",
        "tier": "Tier 1 — High Reasoning",
        "sub_cost": "API ($2.00 / $6.00)",
        "price_in": 2.00,
        "price_out": 6.00,
        "live_aliases": ["qwen3.8-max", "qwen3-8-max"],
        "lm_aliases": ["qwen3.8-max", "qwen3-8-max"],
        "aa_aliases": ["qwen-3-8-max", "qwen3-8-max"],
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
    "qwen3.8-flash-next": {
        "display": "Qwen3.8-Flash-Next",
        "provider": "Alibaba",
        "pool": "api",
        "tier": "Ultra-Fast Reasoning",
        "sub_cost": "API ($0.08 / $0.24)",
        "price_in": 0.08,
        "price_out": 0.24,
        "live_aliases": ["qwen3.8-flash-next", "qwen3-8-flash-next"],
        "lm_aliases": ["qwen3.8-flash-next", "qwen3-8-flash-next"],
        "aa_aliases": ["qwen-3-8-flash-next", "qwen3-8-flash-next"],
        "base_metrics": {
            "lm_elo": 1360,
            "lm_coding": 1390,
            "speed_tps": 120.0,
        },
    },
    "qwen3.8-27b": {
        "display": "Qwen3.8 27B",
        "provider": "Alibaba",
        "pool": "api",
        "tier": "Fast Executor",
        "sub_cost": "API ($0.40 / $3.00)",
        "price_in": 0.40,
        "price_out": 3.00,
        "live_aliases": ["qwen3.8-27b", "qwen3-8-27b"],
        "lm_aliases": ["qwen3.8-27b", "qwen3-8-27b"],
        "aa_aliases": ["qwen-3-8-27b", "qwen3.8-27b"],
        "base_metrics": {
            "lm_elo": 1355,
            "lm_coding": 1380,
            "speed_tps": 90.0,
        },
    },
    "deepseek-v4-flash": {
        "display": "DeepSeek V4 Flash",
        "provider": "DeepSeek",
        "pool": "api",
        "tier": "Ultra-Fast Verifier",
        "sub_cost": "API ($0.06 / $0.11)",
        "price_in": 0.06,
        "price_out": 0.11,
        "live_aliases": ["deepseek-v4-flash-vision-exp", "deepseek-v4-flash-0731", "deepseek-v4-flash"],
        "lm_aliases": ["deepseek-v4-flash"],
        "aa_aliases": ["deepseek-v4-flash", "deepseek-v4-flash-vision", "deepseek-v4-flash-high"],
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
    "deepseek-v4-pro": {
        "display": "DeepSeek V4 Pro",
        "provider": "DeepSeek",
        "pool": "api",
        "tier": "Tier 2 — Verifier & Logic",
        "sub_cost": "API ($0.41 / $0.83)",
        "price_in": 0.41,
        "price_out": 0.83,
        "live_aliases": ["deepseek-v4-pro-0813", "deepseek-v4-pro"],
        "lm_aliases": ["deepseek-v4-pro"],
        "aa_aliases": ["deepseek-v4-pro"],
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
    "kimi-k3": {
        "display": "Kimi K3 (Max)",
        "provider": "Moonshot",
        "pool": "api",
        "tier": "Architecture & Reasoning",
        "sub_cost": "API ($3.00 / $15.00)",
        "price_in": 3.00,
        "price_out": 15.00,
        "live_aliases": ["kimi-k3"],
        "lm_aliases": ["kimi-k3"],
        "aa_aliases": ["kimi-k3", "kimi-k3-high", "kimi-k3-low"],
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
    "kimi-k2.7-code": {
        "display": "Kimi K2.7 Code",
        "provider": "Moonshot",
        "pool": "api",
        "tier": "Code Specialist",
        "sub_cost": "API ($0.95 / $4.00)",
        "price_in": 0.95,
        "price_out": 4.00,
        "live_aliases": ["kimi-k2.7-code", "kimi-k2-7-code"],
        "lm_aliases": ["kimi-k2.7-code", "kimi-k2-7-code"],
        "aa_aliases": ["kimi-k2.7-code"],
        "base_metrics": {
            "lm_elo": 1360,
            "lm_coding": 1430,
            "speed_tps": 55.0,
        },
    },
    "glm-5.3": {
        "display": "GLM-5.3",
        "provider": "Zhipu AI",
        "pool": "api",
        "tier": "Tier 1 — Architecture & Spec",
        "sub_cost": "API ($1.40 / $4.40)",
        "price_in": 1.40,
        "price_out": 4.40,
        "live_aliases": ["glm-5.3", "glm-5-3"],
        "lm_aliases": ["glm-5.3", "glm-5-3"],
        "aa_aliases": ["glm-5-3", "glm-5.3", "glm-5-3-max", "glm-5.3-max"],
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
    "glm-5.2": {
        "display": "GLM-5.2",
        "provider": "Zhipu AI",
        "pool": "api",
        "tier": "Tier 1 — Architecture",
        "sub_cost": "API ($1.40 / $4.40)",
        "price_in": 1.40,
        "price_out": 4.40,
        "live_aliases": ["glm-5.2", "glm-5-2"],
        "lm_aliases": ["glm-5.2", "glm-5-2"],
        "aa_aliases": ["glm-5-2", "glm-5.2", "glm-5-2-max", "glm-5.2-max"],
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
    "glm-5.3-flash": {
        "display": "GLM-5.3 Flash",
        "provider": "Zhipu AI",
        "pool": "api",
        "tier": "Fast Executor",
        "sub_cost": "API ($0.15 / $0.50)",
        "price_in": 0.15,
        "price_out": 0.50,
        "live_aliases": ["glm-5.3-flash", "glm-5-3-flash"],
        "lm_aliases": ["glm-5.3-flash", "glm-5-3-flash"],
        "aa_aliases": ["glm-5-3-flash", "glm-5.3-flash"],
        "base_metrics": {
            "lm_elo": 1340,
            "lm_coding": 1360,
            "speed_tps": 110.0,
        },
    },
    "muse-spark-1-2": {
        "display": "Muse Spark 1.2 (Contributor)",
        "provider": "Muse",
        "pool": "api",
        "tier": "Fast Contributor Specialist",
        "sub_cost": "API ($0.10 / $0.20)",
        "price_in": 0.10,
        "price_out": 0.20,
        "live_aliases": ["muse-spark-1.2-xhigh", "muse-spark-1.2"],
        "lm_aliases": ["muse-spark-1-2", "muse-spark-1.2"],
        "aa_aliases": ["muse-spark-1.2", "muse-spark-1.2-contributor"],
        "base_metrics": {
            "lm_elo": 1360,
            "lm_coding": 1385,
            "speed_tps": 130.0,
        },
    },
    "gpt-5.6-luna": {
        "display": "GPT 5.6 Luna",
        "provider": "OpenAI",
        "pool": "api",
        "tier": "High-Efficiency Failover",
        "sub_cost": "API ($0.20 / $1.20)",
        "price_in": 0.20,
        "price_out": 1.20,
        "live_aliases": ["gpt-5.6-luna-max", "gpt-5-6-luna-max"],
        "lm_aliases": ["gpt-5-6-luna-xhighcodex-harness", "gpt-5-6-luna", "gpt 5-6 luna-xhighco"],
        "aa_aliases": ["gpt-5-6-luna"],
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
    "minimax-m3": {
        "display": "MiniMax M3",
        "provider": "MiniMax",
        "pool": "api",
        "tier": "General Executor",
        "sub_cost": "API ($0.30 / $1.20)",
        "price_in": 0.30,
        "price_out": 1.20,
        "live_aliases": ["minimax-m3"],
        "lm_aliases": ["minimax-m3"],
        "aa_aliases": ["minimax-m3"],
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
    "mimo-v2.5": {
        "display": "MiMo-V2.5",
        "provider": "Xiaomi",
        "pool": "api",
        "tier": "Bulk Fill",
        "sub_cost": "API ($0.14 / $0.28)",
        "price_in": 0.14,
        "price_out": 0.28,
        "live_aliases": ["mimo-v2.5", "mimo-v2-5", "mimo-v2-pro"],
        "lm_aliases": ["mimo-v2.5", "mimo-v2-5"],
        "aa_aliases": ["mimo-v2-5", "mimo-v2.5"],
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
}

# ==============================================================================
# 2. LIVE FETCHERS, SNAPSHOTS & PARSERS
# ==============================================================================

LIVEBENCH_URL = "https://livebench.ai"
LIVEBENCH_CSV_URL = "https://livebench.ai/table_2026_06_25.csv"
LIVEBENCH_CAT_URL = "https://livebench.ai/categories_2026_06_25.json"
LMARENA_URL = "https://arena.ai/leaderboard/code/webdev"
AA_URL = "https://artificialanalysis.ai/leaderboards/models"
CACHE_TTL_H = bc.CACHE_TTL_H  # canonical 24h freshness window lives in benchmark_common (rule 7)


def format_model_display_name(mid: str) -> tuple[str, str]:
    """Map a model identifier to (display_name, provider_name)."""
    low = mid.lower().strip()
    if low.startswith("glm-") or low.startswith("glm"):
        prov = "Zhipu AI"
        disp = re.sub(r"^glm[-_]?", "GLM-", mid, flags=re.I)
        disp = disp.replace("-flash", " Flash").replace("_flash", " Flash").replace("-turbo", " Turbo").replace("-fast", " Fast")
        return disp, prov
    elif low.startswith("qwen"):
        prov = "Alibaba"
        disp = re.sub(r"^qwen[-_]?", "Qwen", mid, flags=re.I)
        disp = disp.replace("-max", " Max").replace("-plus", " Plus").replace("-flash", " Flash").replace("-coder", " Coder")
        return disp, prov
    elif low.startswith("deepseek"):
        prov = "DeepSeek"
        disp = re.sub(r"^deepseek[-_]?", "DeepSeek ", mid, flags=re.I)
        disp = disp.replace("-v4", " V4").replace("-v3", " V3").replace("-pro", " Pro").replace("-flash", " Flash").replace("-vision", " Vision").replace("-exp", " Exp").replace("-fast", " Fast")
        disp = re.sub(r"\b([kKmMvV])(\d)", lambda m: m.group(1).upper() + m.group(2), disp)
        return re.sub(r"\s+", " ", disp).strip(), prov
    elif low.startswith("kimi"):
        prov = "Moonshot"
        disp = re.sub(r"^kimi[-_]?", "Kimi ", mid, flags=re.I)
        disp = disp.replace("-k3", " K3").replace("-k2.7", " K2.7").replace("-k2.6", " K2.6").replace("-k2.5", " K2.5").replace("-code", " Code").replace("-max", " Max")
        disp = re.sub(r"\b([kKmMvV])(\d)", lambda m: m.group(1).upper() + m.group(2), disp)
        return re.sub(r"\s+", " ", disp).strip(), prov
    elif low.startswith("hy") or low.startswith("hunyuan"):
        prov = "Tencent"
        disp = mid.replace("hy4-preview", "Hunyuan 4 Preview").replace("hy3-preview", "Hunyuan 3 Preview").replace("hy3", "Hunyuan 3")
        return disp, prov
    elif low.startswith("minimax"):
        prov = "MiniMax"
        disp = re.sub(r"^minimax[-_]?", "MiniMax ", mid, flags=re.I)
        disp = disp.replace("-m3", " M3").replace("-m2.7", " M2.7").replace("-m2.5", " M2.5")
        disp = re.sub(r"\b([kKmMvV])(\d)", lambda m: m.group(1).upper() + m.group(2), disp)
        return re.sub(r"\s+", " ", disp).strip(), prov
    elif low.startswith("mimo"):
        prov = "Xiaomi"
        disp = re.sub(r"^mimo[-_]?", "MiMo-", mid, flags=re.I)
        disp = disp.replace("-pro", " Pro").replace("-omni", " Omni").replace("-v2.5", "V2.5").replace("-v2", "V2")
        return disp, prov
    elif low.startswith("grok"):
        prov = "xAI"
        disp = re.sub(r"^grok[-_]?", "Grok ", mid, flags=re.I)
        return disp, prov
    elif low.startswith("gpt") or low.startswith("o3") or low.startswith("o4"):
        prov = "OpenAI"
        disp = re.sub(r"^gpt[-_]?", "GPT ", mid, flags=re.I)
        disp = disp.replace("-luna", " Luna").replace("-sol", " Sol").replace("-terra", " Terra").replace("-codex", " Codex").replace("-oss", "-OSS")
        return disp, prov
    elif low.startswith("claude") or low.startswith("fable") or low.startswith("opus") or low.startswith("sonnet") or low.startswith("haiku"):
        prov = "Anthropic"
        disp = re.sub(r"^claude[-_]?", "Claude ", mid, flags=re.I)
        disp = disp.replace("opus", "Opus").replace("sonnet", "Sonnet").replace("haiku", "Haiku").replace("fable", "Fable")
        if not disp.startswith("Claude "):
            disp = "Claude " + disp
        return re.sub(r"\s+", " ", disp).strip(), prov
    elif low.startswith("gemini") or low.startswith("gemma"):
        prov = "Google"
        disp = re.sub(r"^gemini[-_]?", "Gemini ", mid, flags=re.I)
        return disp, prov
    elif low.startswith("llama"):
        prov = "Meta"
        disp = re.sub(r"^llama[-_]?", "Llama ", mid, flags=re.I)
        return disp, prov
    elif low.startswith("mistral") or low.startswith("codestral") or low.startswith("pixtral"):
        prov = "Mistral"
        disp = mid.replace("-", " ").title()
        return disp, prov
    elif low.startswith("step"):
        prov = "StepFun"
        disp = re.sub(r"^step[-_]?", "Step ", mid, flags=re.I)
        disp = disp.replace("-flash", " Flash")
        return disp, prov
    elif low.startswith("muse"):
        prov = "Muse"
        disp = "Muse Spark 1.2 Contributor" if "spark" in low else mid.replace("-", " ").title()
        return disp, prov
    elif low.startswith("longcat"):
        prov = "Meituan"
        return "LongCat 2.0 (Meituan)", prov
    else:
        prov = "Upstream API"
        return mid.replace("-", " ").replace("_", " ").title(), prov


def load_openrouter_pricing_data():
    """Load OpenRouter model pricing and metadata if available."""
    or_pricing = {}
    or_matches = sorted(glob.glob(str(RAW / "*openrouter_models*20*.json")))
    if or_matches:
        try:
            p = pathlib.Path(or_matches[-1])
            data = json.loads(p.read_text(encoding="utf-8", errors="ignore"))
            for item in data.get("data", []):
                mid = item.get("id")
                if not mid:
                    continue
                pr = item.get("pricing", {})
                pin = float(pr.get("prompt", 0)) * 1_000_000
                pout = float(pr.get("completion", 0)) * 1_000_000
                pricing = {
                    "price_in": pin,
                    "price_out": pout,
                    "name": item.get("name") or mid,
                }
                or_pricing[bc.norm_id(mid)] = pricing
                bare_id = mid.split("/", 1)[-1].split(":", 1)[0]
                or_pricing.setdefault(bc.norm_id(bare_id), pricing)
        except Exception:
            pass
    return or_pricing


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
    """Version-safe matching for LiveBench models."""
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

    exact_map = {norm_model_slug(k): v for k, v in live_map.items()}
    base_map = {}
    for k, v in live_map.items():
        kb = norm_model_slug(livebench_base_name(k))
        if kb and v.get("overall") is not None:
            cur = base_map.get(kb)
            if cur is None or v["overall"] > cur["overall"]:
                base_map[kb] = v

    for c in cands:
        if not c:
            continue
        cn = norm_model_slug(c)
        if not cn:
            continue
        if cn in exact_map:
            return exact_map[cn]
        if cn in base_map:
            return base_map[cn]
        qn = bc.norm_id(c)
        for k, v in live_map.items():
            if not bc.variant_conflict(qn, bc.norm_id(k)) and v.get("overall") is not None:
                return v
    return None


def find_lmarena(model_id_or_dict, lm_map):
    """Version-safe matching for LMArena models."""
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

    exact_map = {norm_model_slug(k): v for k, v in lm_map.items()}
    for c in cands:
        if not c:
            continue
        cn = norm_model_slug(c)
        if not cn:
            continue
        if cn in exact_map:
            return exact_map[cn]
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

    exact_map = {norm_model_slug(k): v for k, v in aa_map.items()}
    for c in cands:
        if not c:
            continue
        cn = norm_model_slug(c)
        if not cn:
            continue
        if cn in exact_map:
            return exact_map[cn]
        qn = bc.norm_id(c)
        for k, v in aa_map.items():
            if not bc.variant_conflict(qn, bc.norm_id(k)) and v.get("intelligenceIndex") is not None:
                return v
    return None


def strip_effort_suffix(slug: str) -> str:
    """Strip secondary effort, mode, or thinking suffixes (e.g. -high, -medium, -low, -xhigh, -adaptive)."""
    return re.sub(
        r"-(high|xhigh|medium|low|minimal|max|adaptive|thinking|reasoning|non-reasoning|preview|contributor|base)(-effort)?$",
        "",
        slug,
        flags=re.I,
    )


def build_universal_catalog(base_catalog=None, live_map=None, lm_map=None, aa_map=None, or_pricing=None):
    """Build universal catalog combining curated baseline models with all upstream benchmark evaluations (AA, LMArena, LiveBench)."""
    import copy
    if base_catalog is None:
        catalog = copy.deepcopy(MODELS_CATALOG)
    else:
        catalog = copy.deepcopy(base_catalog)

    if or_pricing is None:
        or_pricing = load_openrouter_pricing_data()

    # Pre-index normalized maps for O(1) lookup
    live_norm = {bc.norm_id(k): v for k, v in (live_map or {}).items()}
    lm_norm = {bc.norm_id(k): v for k, v in (lm_map or {}).items()}
    aa_norm = {bc.norm_id(k): v for k, v in (aa_map or {}).items()}

    # Base map for LiveBench effort tiers
    live_base = {}
    for k, v in (live_map or {}).items():
        b = bc.norm_id(livebench_base_name(k))
        if b and v.get("overall") is not None:
            if b not in live_base or v["overall"] > live_base[b]["overall"]:
                live_base[b] = v

    key_index = {}
    for cid, info in catalog.items():
        key_index[bc.norm_id(cid)] = cid
        key_index[bc.norm_id(strip_effort_suffix(cid))] = cid
        key_index[bc.norm_id(info.get("display", ""))] = cid
        for a in info.get("live_aliases", []):
            key_index[bc.norm_id(a)] = cid
            key_index[bc.norm_id(strip_effort_suffix(a))] = cid
        for a in info.get("lm_aliases", []):
            key_index[bc.norm_id(a)] = cid
            key_index[bc.norm_id(strip_effort_suffix(a))] = cid
        for a in info.get("aa_aliases", []):
            key_index[bc.norm_id(a)] = cid
            key_index[bc.norm_id(strip_effort_suffix(a))] = cid

    # 1. Ingest from Artificial Analysis (intelligence index, coding index, speed, pricing)
    if aa_map:
        for slug, aa_info in aa_map.items():
            nid = bc.norm_id(slug)
            base_nid = bc.norm_id(strip_effort_suffix(slug))
            if nid in key_index or base_nid in key_index:
                continue
            disp = aa_info.get("name") or slug
            disp_formatted, prov = format_model_display_name(slug)
            if not disp or disp == slug:
                disp = disp_formatted
            p_in = aa_info.get("price_in")
            p_out = aa_info.get("price_out")
            if p_in is None or p_out is None:
                or_p = or_pricing.get(nid) or {}
                p_in = or_p.get("price_in", 1.0)
                p_out = or_p.get("price_out", 3.0)

            catalog[nid] = {
                "display": disp,
                "provider": prov,
                "pool": "api",
                "tier": "Upstream API",
                "sub_cost": "API",
                "price_in": p_in,
                "price_out": p_out,
                "live_aliases": [slug],
                "lm_aliases": [slug],
                "aa_aliases": [slug],
                "base_metrics": {
                    "speed_tps": aa_info.get("medianTps") or 60.0,
                },
            }
            key_index[nid] = nid
            key_index[base_nid] = nid

    # 2. Ingest from LiveBench
    if live_map:
        for slug, lb_rec in live_map.items():
            nid = bc.norm_id(slug)
            base_nid = bc.norm_id(livebench_base_name(slug))
            if nid in key_index or base_nid in key_index:
                continue
            disp_formatted, prov = format_model_display_name(slug)
            or_p = or_pricing.get(nid) or {}
            catalog[nid] = {
                "display": disp_formatted,
                "provider": prov,
                "pool": "api",
                "tier": "Benchmark Model",
                "sub_cost": "API",
                "price_in": or_p.get("price_in", 1.0),
                "price_out": or_p.get("price_out", 3.0),
                "live_aliases": [slug],
                "lm_aliases": [slug],
                "aa_aliases": [slug],
                "base_metrics": {},
            }
            key_index[nid] = nid
            key_index[base_nid] = nid

    # 3. Ingest from LMArena
    if lm_map:
        for slug, lm_rec in lm_map.items():
            nid = bc.norm_id(slug)
            base_nid = bc.norm_id(strip_effort_suffix(slug))
            if nid in key_index or base_nid in key_index:
                continue
            disp_formatted, prov = format_model_display_name(slug)
            or_p = or_pricing.get(nid) or {}
            catalog[nid] = {
                "display": disp_formatted,
                "provider": prov,
                "pool": "api",
                "tier": "Arena Model",
                "sub_cost": "API",
                "price_in": or_p.get("price_in", 1.0),
                "price_out": or_p.get("price_out", 3.0),
                "live_aliases": [slug],
                "lm_aliases": [slug],
                "aa_aliases": [slug],
                "base_metrics": {},
            }
            key_index[nid] = nid
            key_index[base_nid] = nid

    # Multi-source signal attachment across all aliases + base slugs
    for mid, m in catalog.items():
        # LiveBench signal
        if live_norm or live_base:
            cands_live = m.get("live_aliases", []) + [mid, m.get("display")]
            for c in cands_live:
                if not c:
                    continue
                cn = bc.norm_id(c)
                if cn in live_norm:
                    m["livebench"] = live_norm[cn]
                    break
                if cn in live_base:
                    m["livebench"] = live_base[cn]
                    break
                c_base = bc.norm_id(strip_effort_suffix(c))
                if c_base in live_base:
                    m["livebench"] = live_base[c_base]
                    break

        # LMArena signal
        if lm_norm:
            cands_lm = m.get("lm_aliases", []) + [mid, m.get("display")]
            for c in cands_lm:
                if not c:
                    continue
                cn = bc.norm_id(c)
                if cn in lm_norm:
                    rec = lm_norm[cn]
                    if rec.get("elo"):
                        m.setdefault("base_metrics", {})["lm_elo"] = rec["elo"]
                        if rec.get("coding"):
                            m["base_metrics"]["lm_coding"] = rec["coding"]
                        break
                c_base = bc.norm_id(strip_effort_suffix(c))
                if c_base in lm_norm:
                    rec = lm_norm[c_base]
                    if rec.get("elo"):
                        m.setdefault("base_metrics", {})["lm_elo"] = rec["elo"]
                        if rec.get("coding"):
                            m["base_metrics"]["lm_coding"] = rec["coding"]
                        break

        # Artificial Analysis signal
        if aa_norm:
            cands_aa = m.get("aa_aliases", []) + [mid, m.get("display")]
            for c in cands_aa:
                if not c:
                    continue
                cn = bc.norm_id(c)
                if cn in aa_norm:
                    rec = aa_norm[cn]
                    bm = m.setdefault("base_metrics", {})
                    if rec.get("intelligenceIndex") is not None:
                        bm["aa_quality"] = rec["intelligenceIndex"]
                        m["aa_live_quality"] = rec["intelligenceIndex"]
                    if rec.get("codingIndex") is not None:
                        bm["aa_coding"] = rec["codingIndex"]
                        m["aa_live_coding"] = rec["codingIndex"]
                    if rec.get("medianTps") is not None:
                        bm["speed_tps"] = rec["medianTps"]
                    break
                c_base = bc.norm_id(strip_effort_suffix(c))
                if c_base in aa_norm:
                    rec = aa_norm[c_base]
                    bm = m.setdefault("base_metrics", {})
                    if rec.get("intelligenceIndex") is not None:
                        bm["aa_quality"] = rec["intelligenceIndex"]
                        m["aa_live_quality"] = rec["intelligenceIndex"]
                    if rec.get("codingIndex") is not None:
                        bm["aa_coding"] = rec["codingIndex"]
                        m["aa_live_coding"] = rec["codingIndex"]
                    if rec.get("medianTps") is not None:
                        bm["speed_tps"] = rec["medianTps"]
                    break

    return catalog


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
    csv_matches = [
        p for p in sorted(glob.glob(str(RAW / "*livebench*20*.csv")))
        if "cost" not in pathlib.Path(p).name
    ]
    for p_csv in csv_matches[-1:]:
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
    for p_html in (matches[-1:] if matches else []):
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
    for p_html in (matches[-1:] if matches else []):
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
        z_aa_qual = _z_scores([m.get("base_metrics", {}).get("aa_quality") for m in m_list])
    live_c = [m.get("aa_live_coding") for m in m_list]
    if any(v is not None for v in live_c):
        z_aa_cod = _z_scores(live_c)
    else:
        z_aa_cod = _z_scores([m.get("base_metrics", {}).get("aa_coding") for m in m_list])
    z_lm_elo = _z_scores([m.get("base_metrics", {}).get("lm_elo") for m in m_list])
    z_lm_cod = _z_scores([m.get("base_metrics", {}).get("lm_coding") for m in m_list])
    z_aa_reas = _z_scores([m.get("base_metrics", {}).get("aa_reasoning") for m in m_list])  # static for ALL: no live AA equivalent, uniform scale
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

        speed = float(m.get("base_metrics", {}).get("speed_tps") or 60.0)
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


def partition_models_by_benchmark_coverage(models_list):
    """Partition model list into tri-verified cohort (all 3 benchmarks) and missing-benchmark sub-cohorts."""
    tri_verified = []
    missing_livebench = []
    missing_lmarena = []
    missing_aa = []
    single_source = []

    for m in models_list:
        has_live = (m.get("livebench", {}).get("overall") is not None) if isinstance(m.get("livebench"), dict) else (m.get("livebench") is not None)
        has_arena = m.get("base_metrics", {}).get("lm_elo") is not None
        has_aa = m.get("aa_live_quality") is not None or m.get("base_metrics", {}).get("aa_quality") is not None

        count = (1 if has_live else 0) + (1 if has_arena else 0) + (1 if has_aa else 0)
        if count == 3:
            tri_verified.append(m)
        elif count == 2:
            if not has_live:
                missing_livebench.append(m)
            elif not has_arena:
                missing_lmarena.append(m)
            elif not has_aa:
                missing_aa.append(m)
        elif count == 1:
            single_source.append(m)

    return {
        "tri_verified": tri_verified,
        "missing_livebench": missing_livebench,
        "missing_lmarena": missing_lmarena,
        "missing_aa": missing_aa,
        "single_source": single_source,
    }


def render_sub_table_cli(sub_models, title, color=True, is_slim=False, top_n=10):
    """Render a compact sub-table for models with partial benchmark evaluations."""
    if not sub_models:
        return ""
    display_sub = sub_models[:top_n]
    out = []
    w_total = 95
    if color:
        out.append(f"\n{C_BOLD}{C_CYAN}┌" + ("─" * w_total) + f"┐{C_RESET}")
        title_padded = f" {title}" + (" " * max(0, w_total - display_len(title) - 1))
        out.append(f"{C_BOLD}{C_CYAN}│{C_RESET}{C_BOLD}{C_WHITE}{title_padded}{C_RESET}{C_BOLD}{C_CYAN}│{C_RESET}")
        out.append(f"{C_BOLD}{C_CYAN}├────┬──────────────────────────┬───────┬────────┬─────────┬────────┬────────┬────────┬────────────┤{C_RESET}")
        hdr_cells = [
            color_cell("Rank", C_BOLD + C_WHITE, width=4, align="^", bg=BG_HEADER),
            color_cell("Model", C_BOLD + C_WHITE, width=24, align="<", bg=BG_HEADER),
            color_cell("Pool", C_BOLD + C_WHITE, width=5, align="^", bg=BG_HEADER),
            color_cell("Q(Cap)", C_BOLD + C_WHITE, width=6, align=">", bg=BG_HEADER),
            color_cell("P(Succ)", C_BOLD + C_WHITE, width=7, align=">", bg=BG_HEADER),
            color_cell("Eff $/M", C_BOLD + C_WHITE, width=7, align=">", bg=BG_HEADER),
            color_cell("Live%", C_BOLD + C_WHITE, width=6, align=">", bg=BG_HEADER),
            color_cell("Arena", C_BOLD + C_WHITE, width=6, align=">", bg=BG_HEADER),
            color_cell("AA Qual", C_BOLD + C_WHITE, width=10, align=">", bg=BG_HEADER),
        ]
        out.append(f"{BG_HEADER}{C_DIM}│{C_RESET}" + f"{BG_HEADER}{C_DIM}│{C_RESET}".join(hdr_cells) + f"{BG_HEADER}{C_DIM}│{C_RESET}")
        out.append(f"{C_BOLD}{C_CYAN}├────┼──────────────────────────┼───────┼────────┼─────────┼────────┼────────┼────────────┤{C_RESET}")
        for i, m in enumerate(display_sub, 1):
            bg = BG_ODD if (i % 2 == 1) else BG_EVEN
            mid = m["display"][:24]
            p_badge_str = pool_badge(m["pool"], color=False)
            q = m.get("capability_q", 0)
            p = m.get("p_success", 0)
            c = m.get("effective_cost", 0)
            lb = m.get("livebench")
            lb_res = lb.get("overall") if isinstance(lb, dict) else (lb if isinstance(lb, (int, float)) else None)
            lb_val = f"{lb_res:.1f}%" if isinstance(lb_res, (int, float)) else "—"
            elo = m.get("base_metrics", {}).get("lm_elo")
            elo_val = f"{int(elo)}" if isinstance(elo, (int, float)) else "—"
            aa = m.get("aa_live_quality") or m.get("base_metrics", {}).get("aa_quality")
            aa_val = f"{aa:.1f}" if isinstance(aa, (int, float)) else "—"
            row_cells = [
                color_cell(f"#{i}", C_SILVER if i == 2 else (C_GOLD if i == 1 else (C_BRONZE if i == 3 else C_WHITE)), width=4, align="^", bg=bg),
                color_cell(mid, C_WHITE, width=24, align="<", bg=bg),
                color_cell(p_badge_str, "", width=5, align="^", bg=bg),
                color_cell(f"{q:.1f}", score_color_q(q), width=6, align=">", bg=bg),
                color_cell(f"{p:.1f}%", score_color_p(p), width=7, align=">", bg=bg),
                color_cell(f"${c:.2f}", C_CYAN if c < 10 else C_YELLOW, width=7, align=">", bg=bg),
                color_cell(lb_val, C_GREEN if isinstance(lb_res, (int, float)) and lb_res >= 75 else C_GRAY, width=6, align=">", bg=bg),
                color_cell(elo_val, C_GREEN if isinstance(elo, (int, float)) and elo >= 1480 else C_GRAY, width=6, align=">", bg=bg),
                color_cell(aa_val, C_GREEN if isinstance(aa, (int, float)) and aa >= 50 else C_GRAY, width=10, align=">", bg=bg),
            ]
            out.append(f"{bg}{C_DIM}│{C_RESET}" + f"{bg}{C_DIM}│{C_RESET}".join(row_cells) + f"{bg}{C_DIM}│{C_RESET}")
        out.append(f"{C_BOLD}{C_CYAN}└────┴──────────────────────────┴───────┴────────┴─────────┴────────┴────────┴────────┴────────────┘{C_RESET}")
    else:
        out.append(f"\n" + "=" * (w_total + 2))
        out.append(f" {title}")
        out.append("=" * (w_total + 2))
        out.append("Rank Model                    Pool  Q(Cap) P(Succ)  Eff $/M  Live%  Arena    AA Qual")
        out.append("-" * (w_total + 2))
        for i, m in enumerate(display_sub, 1):
            mid = m["display"][:24]
            p_badge_str = pool_badge(m["pool"], color=False)
            q = m.get("capability_q", 0)
            p = m.get("p_success", 0)
            c = m.get("effective_cost", 0)
            lb = m.get("livebench")
            lb_res = lb.get("overall") if isinstance(lb, dict) else (lb if isinstance(lb, (int, float)) else None)
            lb_val = f"{lb_res:.1f}%" if isinstance(lb_res, (int, float)) else "—"
            elo = m.get("base_metrics", {}).get("lm_elo")
            elo_val = f"{int(elo)}" if isinstance(elo, (int, float)) else "—"
            aa = m.get("aa_live_quality") or m.get("base_metrics", {}).get("aa_quality")
            aa_val = f"{aa:.1f}" if isinstance(aa, (int, float)) else "—"
            out.append(f"#{i:<3} {mid:<24} {p_badge_str:^5} {q:>6.1f} {p:>6.1f}% ${c:>7.2f} {lb_val:>6} {elo_val:>6} {aa_val:>10}")
        out.append("-" * (w_total + 2))
    return "\n".join(out)


def render_cli_table(models_list, color=None, slim=None, wide=False, pareto_ids=None, added_ids=None, removed_models=None, stale_note=None, top_n: int | None = 30):
    """Render structured TUI table with adaptive terminal width, tri-verified main table, and missing-benchmark sub-tables."""
    if color is None:
        color = not os.getenv("NO_COLOR")

    if pareto_ids is None:
        pareto_ids = compute_pareto_frontier(models_list)

    if added_ids is None:
        added_ids = set()
    if removed_models is None:
        removed_models = []

    partitions = partition_models_by_benchmark_coverage(models_list)
    tri_models = partitions["tri_verified"]
    miss_live = partitions["missing_livebench"]
    miss_arena = partitions["missing_lmarena"]
    miss_aa = partitions["missing_aa"]
    single_source = partitions["single_source"]

    # Main table shows tri-verified models if present; fallback to full list if none
    primary_models = tri_models if tri_models else models_list
    total_tri = len(primary_models)
    display_models = primary_models[:top_n] if (top_n and len(primary_models) > top_n) else primary_models
    shown_models = len(display_models)

    col_medals = compute_column_medals(primary_models, BCHECK_COL_MEDAL_KEYS, id_key="display")

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

    top_frontier = max(primary_models, key=lambda m: m.get("fgi_score", 0)) if primary_models else None
    top_avi = max(primary_models, key=lambda m: m.get("avi_score", 0)) if primary_models else None
    top_speed = max(primary_models, key=lambda m: m.get("base_metrics", {}).get("speed_tps") or 0) if primary_models else None

    # Total inner width between outer box borders
    inner_w = sum(w + 2 for _, w, _ in headers) + len(headers) - 1

    # 1. Executive Summary Banner
    title_str = "⚡ TRI-VERIFIED AGENTIC RADAR (LiveBench · Arena.ai · AA)"
    f_info = f"Frontier: {top_frontier['display'][:14]} (FGI {top_frontier.get('fgi_score', 0):.1f})" if top_frontier else ""
    v_info = f"Top ROI: {top_avi['display'][:14]} (AVI {top_avi.get('avi_score', 0):.1f})" if top_avi else ""
    s_info = f"Fastest: {top_speed['display'][:12]} ({top_speed.get('base_metrics', {}).get('speed_tps') or 0:.0f}t/s)" if top_speed else ""
    count_label = f"Tri-Verified: {total_tri} models (Top {shown_models} shown)" if shown_models < total_tri else f"Tri-Verified: {total_tri} models"
    if is_slim:
        summary_str = f" {count_label} │ {f_info} │ {v_info}"
    else:
        summary_str = f" {count_label} │ {f_info} │ {v_info} │ {s_info}"

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
        plain_title_line=f" TRI-VERIFIED BENCHMARK & COST-BENEFIT RADAR (LiveBench · Arena · AA) — {count_label}",
        plain_diff_parts=diff_parts,
    ))

    # Border templates
    bot_border = ""
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
    for idx, m in enumerate(display_models):
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

        mid_raw = m["display"]
        is_added = (mid_raw in added_ids) or (m.get("model_id") in added_ids) or (m.get("or_slug") in added_ids) or (m.get("aa_slug") in added_ids)
        is_pareto = (mid_raw in pareto_ids) or (m.get("aa_slug") in pareto_ids) or (mid_raw[:22] in pareto_ids) or (mid_raw[:20] in pareto_ids)

        m_name_w = headers[1][1]
        mid = (("+" if is_added else "") + mid_raw)[:m_name_w]
        pool_badge_str = pool_badge(m["pool"], color=color)

        bm = m.get("base_metrics", {})
        meds = col_medals.get(mid_raw, {})

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

    # 4. Missing Benchmark Sub-Tables
    if miss_live:
        sub_t = render_sub_table_cli(miss_live, "📊 SUB-TABLE 1: TOP 10 — MISSING LIVEBENCH (Arena.ai + AA Evaluated)", color=color, is_slim=is_slim, top_n=10)
        if sub_t:
            out.append(sub_t)
    if miss_arena:
        sub_t = render_sub_table_cli(miss_arena, "⚔️ SUB-TABLE 2: TOP 10 — MISSING LMARENA (LiveBench + AA Evaluated)", color=color, is_slim=is_slim, top_n=10)
        if sub_t:
            out.append(sub_t)
    if miss_aa:
        sub_t = render_sub_table_cli(miss_aa, "🧪 SUB-TABLE 3: TOP 10 — MISSING ARTIFICIAL ANALYSIS (LiveBench + Arena Evaluated)", color=color, is_slim=is_slim, top_n=10)
        if sub_t:
            out.append(sub_t)
    if single_source:
        sub_t = render_sub_table_cli(single_source, "🚀 SUB-TABLE 4: TOP 10 — SINGLE-BENCHMARK / EMERGING MODELS (1 Evaluator Only)", color=color, is_slim=is_slim, top_n=10)
        if sub_t:
            out.append(sub_t)

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

    role_recs = compute_role_recommendations(primary_models, context="bcheck")
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


def render_sub_table_md(sub_models, title, top_n=10):
    """Render markdown sub-table for models with partial benchmark evaluations."""
    if not sub_models:
        return ""
    lines = [
        f"### {title}",
        "",
        "| Rank | Model | Pool / Tier | Q (Cap) | P(Succ) | Eff. $/M | LiveBench (%) | Arena Elo | AA Quality | Raw $/M |",
        "| :---: | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]
    for i, m in enumerate(sub_models[:top_n], 1):
        bm = m.get("base_metrics", {})
        mid_raw = m["display"]
        sub = f"`{m['pool'].upper()}` ({m['tier']})"
        q = f"**{m.get('capability_q', 0):.1f}**"
        psucc = f"{m.get('p_success', 0):.1f}%"
        eff_cost = f"${m.get('effective_cost', 0):.2f}"
        lb = m.get("livebench")
        lb_res = lb.get("overall") if isinstance(lb, dict) else (lb if isinstance(lb, (int, float)) else None)
        lb_str = f"{lb_res:.1f}%" if isinstance(lb_res, (int, float)) else "—"
        elo_str = f"{int(bm['lm_elo'])}" if isinstance(bm.get("lm_elo"), (int, float)) else "—"
        aa_val = m.get("aa_live_quality") or bm.get("aa_quality")
        aa_str = f"{aa_val:.1f}" if isinstance(aa_val, (int, float)) else "—"
        cost = f"${m['price_in']:.2f} / ${m['price_out']:.2f}"
        lines.append(f"| #{i} | **{mid_raw}** | {sub} | {q} | {psucc} | {eff_cost} | {lb_str} | {elo_str} | {aa_str} | {cost} |")
    lines.append("")
    return "\n".join(lines)


def render_sub_table_html(sub_models, title, top_n=10):
    """Render HTML sub-table for models with partial benchmark evaluations."""
    if not sub_models:
        return ""
    trs = []
    for i, m in enumerate(sub_models[:top_n], 1):
        bm = m.get("base_metrics", {})
        pool_cls = {"claude": "badge-cld", "agy": "badge-agy", "ocgo": "badge-ocg", "frontier": "badge-frt"}.get(m["pool"], "")
        lb = m.get("livebench")
        lb_res = lb.get("overall") if isinstance(lb, dict) else (lb if isinstance(lb, (int, float)) else None)
        lb_str = f"{lb_res:.1f}%" if isinstance(lb_res, (int, float)) else "—"
        elo_str = f"{int(bm['lm_elo'])}" if isinstance(bm.get("lm_elo"), (int, float)) else "—"
        aa_val = m.get("aa_live_quality") or bm.get("aa_quality")
        aa_str = f"{aa_val:.1f}" if isinstance(aa_val, (int, float)) else "—"
        trs.append(f"""
        <tr>
            <td style="font-weight:700; text-align:center;">#{i}</td>
            <td style="font-weight:600;">{html.escape(m['display'])}</td>
            <td><span class="badge {pool_cls}">{m['pool'].upper()}</span></td>
            <td>{html.escape(m['tier'])}</td>
            <td style="font-weight:700; color:#2563eb;">{m.get('capability_q', 0):.1f}</td>
            <td>{m.get('p_success', 0):.1f}%</td>
            <td>${m.get('effective_cost', 0):.2f}</td>
            <td style="font-weight:600; color:#f59e0b;">{lb_str}</td>
            <td>{elo_str}</td>
            <td>{aa_str}</td>
            <td>${m['price_in']:.2f} / ${m['price_out']:.2f}</td>
        </tr>
        """)
    return f"""
    <h3>{html.escape(title)}</h3>
    <table>
        <thead>
            <tr>
                <th>Rank</th>
                <th>Model</th>
                <th>Pool</th>
                <th>Tier</th>
                <th>Q (Cap)</th>
                <th>P(Succ)</th>
                <th>Eff $/M</th>
                <th>LiveBench</th>
                <th>Arena Elo</th>
                <th>AA Quality</th>
                <th>Price In/Out</th>
            </tr>
        </thead>
        <tbody>
            {''.join(trs)}
        </tbody>
    </table>
    """


def render_markdown_report(models_list, title=None, pareto_ids=None, top_n: int | None = 30):
    """Render detailed Markdown report with tri-verified master leaderboard and partial benchmark sub-tables."""
    if pareto_ids is None:
        pareto_ids = compute_pareto_frontier(models_list)

    if not title:
        title = f"Consolidated LLM Benchmark & Agentic Cost-Benefit Report ({dt.date.today().isoformat()})"

    partitions = partition_models_by_benchmark_coverage(models_list)
    tri_models = partitions["tri_verified"]
    miss_live = partitions["missing_livebench"]
    miss_arena = partitions["missing_lmarena"]
    miss_aa = partitions["missing_aa"]
    single_source = partitions["single_source"]

    primary_models = tri_models if tri_models else models_list
    total_tri = len(primary_models)
    display_models = primary_models[:top_n] if (top_n and len(primary_models) > top_n) else primary_models

    lines = [
        f"# {title}\n",
        f"Consolidated capability & cost-efficiency benchmark across **LiveBench** (https://livebench.ai), **LMArena / Arena.ai**, **Artificial Analysis**, **AGY Subscription (Gemini)**, **Claude Subscription (Anthropic)**, and **Frontier API Models**.",
        "",
        "## 1. Tri-Verified Master Leaderboard (All 3 Benchmarks Verified)",
    ]
    if len(display_models) < total_tri:
        lines.append(f"_Showing top {len(display_models)} of {total_tri} tri-verified models._")
    lines.extend([
        "",
        "| Model | Pool / Tier | Q (Cap) | P(Succ) | Eff. $/M | AVI (Value) | FGI (Gate) | LiveBench (%) | Arena Elo | AA Quality | Raw $/M |",
        "| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
    ])

    for m in display_models:
        bm = m.get("base_metrics", {})
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
        elo_str = f"{int(bm['lm_elo'])}" if isinstance(bm.get("lm_elo"), (int, float)) else "—"
        aa_val = m.get("aa_live_quality") or bm.get("aa_quality")
        aa_str = f"{aa_val:.1f}" if isinstance(aa_val, (int, float)) else "—"
        cost = f"${m['price_in']:.2f} / ${m['price_out']:.2f}"

        lines.append(
            f"| {mid} | {sub} | {q} | {psucc} | {eff_cost} | {avi} | {fgi} | {lb_str} | {elo_str} | {aa_str} | {cost} |"
        )

    # Sub-Tables Section
    lines.extend([
        "",
        "## 2. Models with Partial / Missing Benchmark Evaluations",
        "",
    ])
    if miss_live:
        lines.append(render_sub_table_md(miss_live, "2.1 Top 10 — Missing LiveBench (Arena.ai + AA Evaluated)", top_n=10))
    if miss_arena:
        lines.append(render_sub_table_md(miss_arena, "2.2 Top 10 — Missing LMArena (LiveBench + AA Evaluated)", top_n=10))
    if miss_aa:
        lines.append(render_sub_table_md(miss_aa, "2.3 Top 10 — Missing Artificial Analysis (LiveBench + Arena Evaluated)", top_n=10))
    if single_source:
        lines.append(render_sub_table_md(single_source, "2.4 Top 10 — Single-Benchmark / Emerging Models (1 Evaluator Only)", top_n=10))

    podium_cols = [
        ("Q(Cap) — Composite Capability", lambda m: m.get("capability_q", 0), True, None, lambda m: f"{m.get('capability_q', 0):.1f}"),
        ("FGI — Architectural Gate Index", lambda m: m.get("fgi_score", 0), True, None, lambda m: f"{m.get('fgi_score', 0):.1f}"),
        ("AVI — Agentic Value Index (ROI)", lambda m: m.get("avi_score", 0), True, None, lambda m: f"{m.get('avi_score', 0):.1f}"),
        ("LiveBench (%) — Decontaminated", lambda m: m.get("livebench", {}).get("overall", 0) if isinstance(m.get("livebench"), dict) and isinstance(m.get("livebench", {}).get("overall"), (int, float)) else 0, True, lambda m: isinstance(m.get("livebench"), dict) and isinstance(m.get("livebench", {}).get("overall"), (int, float)), lambda m: f"{m.get('livebench', {}).get('overall'):.1f}%"),
        ("Arena.ai Elo — Global Arena", lambda m: m.get("base_metrics", {}).get("lm_elo", 0), True, lambda m: isinstance(m.get("base_metrics", {}).get("lm_elo"), (int, float)), lambda m: f"{int(m.get('base_metrics', {}).get('lm_elo'))}"),
        ("Coding Elo — LMSYS Arena", lambda m: m.get("base_metrics", {}).get("lm_coding", 0), True, lambda m: isinstance(m.get("base_metrics", {}).get("lm_coding"), (int, float)), lambda m: f"{int(m.get('base_metrics', {}).get('lm_coding'))}"),
        ("Speed — Generation Throughput", lambda m: m.get("base_metrics", {}).get("speed_tps", 0), True, lambda m: isinstance(m.get("base_metrics", {}).get("speed_tps"), (int, float)), lambda m: f"{int(m.get('base_metrics', {}).get('speed_tps'))} t/s"),
        ("Eff $/M — Real Solved Task Cost", lambda m: m.get("effective_cost", 999), False, None, lambda m: f"${m.get('effective_cost', 0):.2f}"),
        ("Price — Blended Raw Cost", lambda m: m.get("blended_price", 999), False, None, lambda m: f"${m.get('blended_price', 0):.2f}"),
        ("P(Succ) (%) — 1-Turn Pass Rate", lambda m: m.get("p_success", 0), True, None, lambda m: f"{m.get('p_success', 0):.1f}%"),
    ]

    lines.extend([
        "",
        "## 3. Column Winners & Podium Leaders (1st 🥇 · 2nd 🥈 · 3rd 🥉)",
        "",
        "| Metric / Column | 🥇 1st Place (Gold) | 🥈 2nd Place (Silver) | 🥉 3rd Place (Bronze) |",
        "| :--- | :--- | :--- | :--- |",
    ])
    for col_label, key_fn, rev, filt, fmt_fn in podium_cols:
        valid = [m for m in primary_models if filt(m)] if filt else primary_models
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

    role_recs = compute_role_recommendations(primary_models, context="bcheck")
    if role_recs:
        lines.extend([
            "",
            "## 4. Dynamic Function & Role Recommendations (Weighted Scoring)",
            "",
            render_role_recommendations_md(role_recs),
        ])

    lines.extend([
        "",
        "## 5. Key Insights & Routing Architecture",
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


def render_html_report(models_list, pareto_ids=None, added_ids=None, removed_models=None, stale_note=None, top_n: int | None = 30):
    """Render standalone HTML dashboard with tri-verified table and sub-tables."""
    if pareto_ids is None:
        pareto_ids = compute_pareto_frontier(models_list)

    if added_ids is None:
        added_ids = set()
    if removed_models is None:
        removed_models = []

    partitions = partition_models_by_benchmark_coverage(models_list)
    tri_models = partitions["tri_verified"]
    miss_live = partitions["missing_livebench"]
    miss_arena = partitions["missing_lmarena"]
    miss_aa = partitions["missing_aa"]
    single_source = partitions["single_source"]

    primary_models = tri_models if tri_models else models_list
    display_models = primary_models[:top_n] if (top_n and len(primary_models) > top_n) else primary_models

    role_recs = compute_role_recommendations(primary_models, context="bcheck")
    role_recs_html = render_role_recommendations_html(role_recs) if role_recs else ""

    trs = []
    for m in display_models:
        bm = m.get("base_metrics", {})
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
        ("Arena.ai — Global Elo", lambda m: m.get("base_metrics", {}).get("lm_elo", 0), True, lambda m: isinstance(m.get("base_metrics", {}).get("lm_elo"), (int, float)), lambda m: f"{int(m.get('base_metrics', {}).get('lm_elo'))}"),
        ("Coding Elo — LMSYS Arena", lambda m: m.get("base_metrics", {}).get("lm_coding", 0), True, lambda m: isinstance(m.get("base_metrics", {}).get("lm_coding"), (int, float)), lambda m: f"{int(m.get('base_metrics', {}).get('lm_coding'))}"),
        ("Speed — Throughput", lambda m: m.get("base_metrics", {}).get("speed_tps", 0), True, lambda m: isinstance(m.get("base_metrics", {}).get("speed_tps"), (int, float)), lambda m: f"{int(m.get('base_metrics', {}).get('speed_tps'))} t/s"),
        ("Eff $/M — Real Task Cost", lambda m: m.get("effective_cost", 999), False, None, lambda m: f"${m.get('effective_cost', 0):.2f}"),
        ("Price — Blended $/M", lambda m: m.get("blended_price", 999), False, None, lambda m: f"${m.get('blended_price', 0):.2f}"),
        ("P(Succ) — Pass Rate", lambda m: m.get("p_success", 0), True, None, lambda m: f"{m.get('p_success', 0):.1f}%"),
    ]

    podium_trs = []
    for col_label, key_fn, rev, filt, fmt_fn in podium_cols:
        valid = [m for m in primary_models if filt(m)] if filt else primary_models
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

    # Sub-tables HTML
    sub_tables_html = []
    if miss_live:
        sub_tables_html.append(render_sub_table_html(miss_live, "📊 Top 10 — Missing LiveBench (Arena.ai + AA Evaluated)", top_n=10))
    if miss_arena:
        sub_tables_html.append(render_sub_table_html(miss_arena, "⚔️ Top 10 — Missing LMArena (LiveBench + AA Evaluated)", top_n=10))
    if miss_aa:
        sub_tables_html.append(render_sub_table_html(miss_aa, "🧪 Top 10 — Missing Artificial Analysis (LiveBench + Arena Evaluated)", top_n=10))
    if single_source:
        sub_tables_html.append(render_sub_table_html(single_source, "🚀 Top 10 — Single-Benchmark / Emerging Models (1 Evaluator Only)", top_n=10))

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

    <h2>1. Tri-Verified Master Leaderboard (LiveBench · Arena · AA)</h2>
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

    <h2>2. Models with Partial / Missing Benchmark Evaluations</h2>
    {''.join(sub_tables_html)}

    <h2>3. Column Winners & Podium Leaders (1st 🥇 · 2nd 🥈 · 3rd 🥉)</h2>
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
        description="Consolidate benchmarks across LiveBench, LMArena, Artificial Analysis, and Frontier API models."
    )
    parser.add_argument(
        "--pool",
        choices=["all", "accessible", "my-pools", "post-claude", "ocgo", "agy", "claude", "frontier", "api"],
        default="all",
        help="Filter by ecosystem (default: all)",
    )
    parser.add_argument(
        "--sort",
        choices=["avi", "fgi", "bfi", "composite", "coding", "reasoning", "live", "speed", "price", "effective_cost"],
        default="composite",
        help="Sort criterion (default: composite)",
    )
    parser.add_argument("-n", "--top", type=int, default=30, help="Number of top models to display in report (default: 30; use --all for full catalog)")
    parser.add_argument("--all", action="store_true", help="Display all tracked models across the catalog (disables top-30 limit)")
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
    top_n = None if (args.all or args.top <= 0) else args.top

    # Load LiveBench from 24h response cache (or live + refresh cache with --fetch)
    live_map = load_livebench_data(fetch=do_fetch)

    # Load LMArena / Arena.ai live or snapshot data
    lm_map = load_lmarena_data(fetch=do_fetch)

    # Load Artificial Analysis live or snapshot data
    aa_map = load_aa_data(fetch=do_fetch)

    # Build universal catalog across all upstream benchmark feeds (with live signals mapped)
    catalog = build_universal_catalog(live_map=live_map, lm_map=lm_map, aa_map=aa_map)
    calculate_composite_scores(catalog)

    # Filter to models with verified benchmark evaluations
    models = [m for m in catalog.values() if m.get("livebench") or m.get("aa_live_quality") or m.get("base_metrics", {}).get("lm_elo") or m.get("base_metrics", {}).get("aa_quality")]

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
        models.sort(key=lambda m: m.get("base_metrics", {}).get("lm_coding", 0), reverse=True)
    elif args.sort == "reasoning":
        models.sort(key=lambda m: m.get("base_metrics", {}).get("aa_reasoning", 0), reverse=True)
    elif args.sort == "speed":
        models.sort(key=lambda m: m.get("base_metrics", {}).get("speed_tps", 0), reverse=True)
    elif args.sort == "live":
        models.sort(key=lambda m: (m.get("livebench", {}).get("overall") if isinstance(m.get("livebench"), dict) else (m.get("livebench") or 0)), reverse=True)
    elif args.sort == "price":
        models.sort(key=lambda m: m.get("price_in", 999))
    elif args.sort == "effective_cost":
        models.sort(key=lambda m: m.get("effective_cost", 999))

    if args.json:
        display_models = models[:top_n] if (top_n and len(models) > top_n) else models
        print(json.dumps(display_models, indent=2))
        return

    if args.md:
        md_text = render_markdown_report(models, top_n=top_n)
        if args.md == "stdout":
            print(md_text)
        else:
            p = pathlib.Path(args.md)
            bc.atomic_write_text(p, md_text)
            print(f"Wrote Markdown report to {args.md}")
        return

    if args.html:
        html_text = render_html_report(models, added_ids=added_ids, removed_models=removed_models, stale_note=stale_note, top_n=top_n)
        p = pathlib.Path(args.html)
        bc.atomic_write_text(p, html_text)
        print(f"Wrote HTML dashboard to {args.html}")
        return

    use_color = False if args.plain else None
    if args.podium:
        print(render_podium_table(models, color=use_color))
        return

    slim_opt = True if args.slim else (False if args.wide else None)
    print(render_cli_table(models, color=use_color, slim=slim_opt, wide=args.wide, added_ids=added_ids, removed_models=removed_models, stale_note=stale_note, top_n=top_n))


if __name__ == "__main__":
    main()
