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
import contextlib
import copy
import datetime as dt
import glob
import html
import json
import os
import pathlib
import re
import shutil
import subprocess
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

import benchmark_common as bc  # noqa: E402
from benchmark_common import (  # noqa: E402
    BG_EVEN,
    BG_HEADER,
    BG_ODD,
    C_BOLD,
    C_BRONZE,
    C_CYAN,
    C_DIM,
    C_GOLD,
    C_GRAY,
    C_GREEN,
    C_RED,
    C_RESET,
    C_SILVER,
    C_WHITE,
    C_YELLOW,
    EFFORT_DISPLAY,
    HTML_CSS_COMMON,
    HTML_SORT_SCRIPT,
    VALS_INDEX_URL,
    clean_display_name,
    color_cell,
    compute_column_medals,
    compute_priced_pareto_frontier,
    compute_role_recommendations,
    diff_model_catalog,
    display_len,
    extract_capability_pillars,
    extract_effort_from_label,
    format_context_window,
    load_or_fetch_cursor_evals,
    load_or_fetch_frontiercode,
    load_or_fetch_frontierswe,
    load_previous_snapshot,
    medal_badge,
    normalize_effort,
    pad_display,
    parse_aa,
    parse_livebench,
    parse_lmarena_hf,
    parse_vals_index,
    pool_badge,
    render_banner_box,
    render_metric_guide_cli,
    render_removed_models_cli,
    render_role_recommendations_cli,
    render_role_recommendations_html,
    render_role_recommendations_md,
    score_color_avi,
    score_color_q,
    score_five_axes_and_roles,
)

UA = bc.UA

# ==============================================================================
# 1. CATALOG SPECIFICATION & SUBSCRIPTION POOLS
# ==============================================================================
# Subscription Pools & Model Definitions
# pool: 'ocgo' | 'agy' | 'claude' | 'frontier'
MODELS_CATALOG = {
    'claude-fable-5-2-max': {
        "display": 'Claude Fable 5.2 (Max)',
        "effort": 'max',
        "provider": 'Anthropic',
        "pool": 'claude',
        "tier": 'Apex Reasoning / Architecture',
        "sub_cost": 'Claude Max / API ($8.00 / $40.00)',
        "price_in": 8.0,
        "price_out": 40.0,
        "context_length": 1_000_000,
        "live_aliases": ['claude-fable-5-2-max-effort'],
        "lm_aliases": ['claude fable 5.2 (max)', 'claude-fable-5.2-max'],
        "aa_aliases": ['claude-fable-5-2-max'],
        "base_metrics": {"speed_tps": 91.0},
    },
    'claude-fable-5-2-xhigh': {
        "display": 'Claude Fable 5.2 (Xhigh)',
        "effort": 'xhigh',
        "provider": 'Anthropic',
        "pool": 'claude',
        "tier": 'Apex Reasoning / Architecture',
        "sub_cost": 'Claude Max / API ($8.00 / $40.00)',
        "price_in": 8.0,
        "price_out": 40.0,
        "context_length": 1_000_000,
        "live_aliases": ['claude-fable-5-2-xhigh-effort'],
        "lm_aliases": ['claude fable 5.2 (xhigh)', 'claude-fable-5.2-xhigh'],
        "aa_aliases": ['claude-fable-5-2-xhigh'],
        "base_metrics": {"speed_tps": 91.0},
    },
    'claude-fable-5-2-high': {
        "display": 'Claude Fable 5.2 (High)',
        "effort": 'high',
        "provider": 'Anthropic',
        "pool": 'claude',
        "tier": 'Apex Reasoning / Architecture',
        "sub_cost": 'Claude Pro / Team / Max',
        "price_in": 8.0,
        "price_out": 40.0,
        "context_length": 1_000_000,
        "live_aliases": ['claude-fable-5-2-high-effort'],
        "lm_aliases": ['claude fable 5.2 (high)', 'claude-fable-5.2-high'],
        "aa_aliases": ['claude-fable-5-2-high'],
        "base_metrics": {"speed_tps": 91.0},
    },
    'claude-fable-5-2-medium': {
        "display": 'Claude Fable 5.2 (Medium)',
        "effort": 'medium',
        "provider": 'Anthropic',
        "pool": 'claude',
        "tier": 'Elite Coding / Balanced Effort',
        "sub_cost": 'Claude Pro / Team / Max',
        "price_in": 8.0,
        "price_out": 40.0,
        "context_length": 1_000_000,
        "live_aliases": ['claude-fable-5-2-medium-effort'],
        "lm_aliases": ['claude fable 5.2 (medium)', 'claude-fable-5.2-medium'],
        "aa_aliases": ['claude-fable-5-2-medium'],
        "base_metrics": {"speed_tps": 90.0},
    },
    'claude-fable-5-2-low': {
        "display": 'Claude Fable 5.2 (Low)',
        "effort": 'low',
        "provider": 'Anthropic',
        "pool": 'claude',
        "tier": 'Fast Frontier / Low Effort',
        "sub_cost": 'Claude Pro / Team / Max',
        "price_in": 8.0,
        "price_out": 40.0,
        "context_length": 1_000_000,
        "live_aliases": ['claude-fable-5-2-low-effort'],
        "lm_aliases": ['claude fable 5.2 (low)', 'claude-fable-5.2-low'],
        "aa_aliases": ['claude-fable-5-2-low'],
        "base_metrics": {"speed_tps": 85.0},
    },
    'claude-opus-5-5-max': {
        "display": 'Claude Opus 5.5 (Max)',
        "effort": 'max',
        "provider": 'Anthropic',
        "pool": 'claude',
        "tier": 'Flagship Reasoning / Max Effort',
        "sub_cost": 'Claude Max / API ($4.00 / $20.00)',
        "price_in": 4.0,
        "price_out": 20.0,
        "context_length": 1_000_000,
        "live_aliases": ['claude-opus-5-5-max-effort'],
        "lm_aliases": ['claude opus 5.5 (max)', 'claude-opus-5.5-max'],
        "aa_aliases": ['claude-opus-5-5-max'],
        "base_metrics": {"speed_tps": 72.0},
    },
    'claude-opus-5-5-xhigh': {
        "display": 'Claude Opus 5.5 (Xhigh)',
        "effort": 'xhigh',
        "provider": 'Anthropic',
        "pool": 'claude',
        "tier": 'Flagship Reasoning / Xhigh Effort',
        "sub_cost": 'Claude Max / API ($4.00 / $20.00)',
        "price_in": 4.0,
        "price_out": 20.0,
        "context_length": 1_000_000,
        "live_aliases": ['claude-opus-5-5-xhigh-effort'],
        "lm_aliases": ['claude opus 5.5 (xhigh)', 'claude-opus-5.5-xhigh'],
        "aa_aliases": ['claude-opus-5-5-xhigh'],
        "base_metrics": {"speed_tps": 72.0},
    },
    'claude-sonnet-5-5-max': {
        "display": 'Claude Sonnet 5.5 (Max)',
        "effort": 'max',
        "provider": 'Anthropic',
        "pool": 'claude',
        "tier": 'Elite Coding / Max Effort',
        "sub_cost": 'Claude Max / API ($2.00 / $10.00)',
        "price_in": 2.0,
        "price_out": 10.0,
        "context_length": 1_000_000,
        "live_aliases": ['claude-sonnet-5-5-max-effort'],
        "lm_aliases": ['claude sonnet 5.5 (max)', 'claude-sonnet-5.5-max'],
        "aa_aliases": ['claude-sonnet-5-5-max'],
        "base_metrics": {"speed_tps": 64.0},
    },
    'claude-sonnet-5-5-xhigh': {
        "display": 'Claude Sonnet 5.5 (Xhigh)',
        "effort": 'xhigh',
        "provider": 'Anthropic',
        "pool": 'claude',
        "tier": 'Elite Coding / Xhigh Effort',
        "sub_cost": 'Claude Max / API ($2.00 / $10.00)',
        "price_in": 2.0,
        "price_out": 10.0,
        "context_length": 1_000_000,
        "live_aliases": ['claude-sonnet-5-5-xhigh-effort'],
        "lm_aliases": ['claude sonnet 5.5 (xhigh)', 'claude-sonnet-5.5-xhigh'],
        "aa_aliases": ['claude-sonnet-5-5-xhigh'],
        "base_metrics": {"speed_tps": 64.0},
    },
    'claude-opus-5': {
        "display": 'Claude Opus 5 (Thinking)',
        "provider": 'Anthropic',
        "pool": 'claude',
        "tier": 'Flagship Reasoning / Complex Gates',
        "sub_cost": 'Claude Pro / Team / Max',
        "price_in": 5.0,
        "price_out": 25.0,
        "live_aliases": ['claude-opus-5-max-effort', 'claude-opus-5'],
        "lm_aliases": ['opus-5-high', 'claude-opus-5-high', 'claude-opus-5'],
        "aa_aliases": ['claude-opus-5', 'claude-opus-5-xhigh', 'claude-opus-5-high', 'claude-opus-5-medium', 'claude-opus-5-low'],
        "base_metrics": {
            "speed_tps": 38.0,
        },
    },
    'claude-fable-5': {
        "display": 'Claude Fable 5 (High)',
        "provider": 'Anthropic',
        "pool": 'claude',
        "tier": 'Elite Creative / Agent',
        "sub_cost": 'API ($10.00 / $50.00)',
        "price_in": 10.0,
        "price_out": 50.0,
        "live_aliases": ['claude-fable-5-max-effort', 'claude-fable-5'],
        "lm_aliases": ['fable-5', 'claude-fable-5'],
        "aa_aliases": ['claude-fable-5'],
        "base_metrics": {
            "speed_tps": 35.0,
        },
    },
    'claude-opus-4-8': {
        "display": 'Claude Opus 4.8 (Thinking)',
        "provider": 'Anthropic',
        "pool": 'claude',
        "tier": 'Lead Architecture / Reasoning',
        "sub_cost": 'Claude Pro / AGY Bridge',
        "price_in": 5.0,
        "price_out": 25.0,
        "live_aliases": ['claude-opus-4-8-xhigh-effort', 'claude-opus-4-8-max-effort', 'claude-opus-4-8-high-effort', 'claude-opus-4-8-medium-effort', 'claude-opus-4-8-low-effort', 'claude-opus-4-8'],
        "lm_aliases": ['opus-4-8', 'claude-opus-4-8', 'claude-opus-4-8-thinking'],
        "aa_aliases": ['claude-opus-4-8', 'claude-opus-4-8-adaptive', 'claude-opus-4-8-high', 'claude-opus-4-8-medium'],
        "base_metrics": {
            "speed_tps": 40.0,
        },
    },
    'claude-opus-4-7': {
        "display": 'Claude Opus 4.7 (Thinking)',
        "provider": 'Anthropic',
        "pool": 'claude',
        "tier": 'Lead Architecture / Reasoning',
        "sub_cost": 'Claude Pro / AGY Bridge',
        "price_in": 5.0,
        "price_out": 25.0,
        "live_aliases": ['claude-opus-4-7-xhigh-effort', 'claude-opus-4-7-high-effort', 'claude-opus-4-7-medium-effort', 'claude-opus-4-7-low-effort', 'claude-opus-4-7'],
        "lm_aliases": ['opus-4-7', 'claude-opus-4-7', 'claude-opus-4-7-thinking'],
        "aa_aliases": ['claude-opus-4-7', 'claude-opus-4-7-adaptive', 'claude-opus-4-7-high', 'claude-opus-4-7-medium', 'claude-opus-4-7-non-reasoning'],
        "base_metrics": {
            "speed_tps": 41.0,
        },
    },
    'claude-opus-4-6': {
        "display": 'Claude Opus 4.6 (Thinking)',
        "provider": 'Anthropic',
        "pool": 'claude',
        "tier": 'Lead / Architecture',
        "sub_cost": 'Claude Pro / AGY Bridge',
        "price_in": 5.0,
        "price_out": 25.0,
        "live_aliases": ['claude-opus-4-6-thinking-auto-high-effort', 'claude-opus-4-6'],
        "lm_aliases": ['opus-4-6', 'claude-opus-4-6', 'claude-opus-4-6-thinking'],
        "aa_aliases": ['claude-opus-4-6', 'claude-opus-4-6-adaptive'],
        "base_metrics": {
            "speed_tps": 42.0,
        },
    },
    'claude-sonnet-5': {
        "display": 'Claude Sonnet 5',
        "provider": 'Anthropic',
        "pool": 'claude',
        "tier": 'Fast Agentic / Design',
        "sub_cost": 'Claude Pro ($20/mo) / Team',
        "price_in": 2.0,
        "price_out": 10.0,
        "live_aliases": ['claude-sonnet-5-xhigh-effort', 'claude-sonnet-5'],
        "lm_aliases": ['claude-sonnet-5', 'sonnet-5', 'sonnet-5-high', 'claude-sonnet-5-high'],
        "aa_aliases": ['claude-sonnet-5'],
        "base_metrics": {
            "speed_tps": 68.0,
        },
    },
    'claude-sonnet-4-6': {
        "display": 'Claude Sonnet 4.6 (Thinking)',
        "provider": 'Anthropic',
        "pool": 'claude',
        "tier": 'Design / Refactor',
        "sub_cost": 'Claude Pro / AGY Bridge',
        "price_in": 3.0,
        "price_out": 15.0,
        "live_aliases": ['claude-sonnet-4-6-thinking-auto-high-effort', 'claude-sonnet-4-6-thinking-auto-medium-effort', 'claude-sonnet-4-6-thinking-auto-low-effort', 'claude-sonnet-4-6'],
        "lm_aliases": ['claude-sonnet-4-6', 'sonnet-4-6'],
        "aa_aliases": ['claude-sonnet-4-6', 'claude-sonnet-4-6-thinking'],
        "base_metrics": {
            "speed_tps": 52.0,
        },
    },
    'claude-haiku-4-5': {
        "display": 'Claude Haiku 4.5',
        "provider": 'Anthropic',
        "pool": 'claude',
        "tier": 'Fast / Scout',
        "sub_cost": 'Claude Pro / API ($1.00 / $5.00)',
        "price_in": 1.0,
        "price_out": 5.0,
        "live_aliases": ['claude-haiku-4-5-20251001-thinking-64k', 'claude-haiku-4-5-20251001', 'claude-haiku-4-5'],
        "lm_aliases": ['claude-haiku-4-5', 'haiku-4-5', 'haiku-4-5-20251001'],
        "aa_aliases": ['claude-haiku-4-5', 'claude-4-5-haiku', 'claude-4-5-haiku-reasoning'],
        "base_metrics": {
            "speed_tps": 125.0,
        },
    },
    'gemini-3.1-pro': {
        "display": 'Gemini 3.1 Pro (High)',
        "provider": 'Google',
        "pool": 'agy',
        "tier": 'Flagship Reasoning (1M ctx)',
        "sub_cost": 'AGY Sub (1B tokens/wk + 300M/5h)',
        "price_in": 2.0,
        "price_out": 12.0,
        "live_aliases": ['gemini-3.1-pro-preview-high', 'gemini-3-1-pro'],
        "lm_aliases": ['gemini-3.1-pro', 'gemini-3-1-pro', 'gemini-3.1-pro-preview', 'gemini-3-1-pro-preview'],
        "aa_aliases": ['gemini-3-1-pro', 'gemini-3.1-pro', 'gemini-3-1-pro-preview'],
        "base_metrics": {
            "speed_tps": 52.0,
        },
    },
    'gemini-3.7-flash-thinking': {
        "display": 'Gemini 3.7 Flash (Thinking)',
        "provider": 'Google',
        "pool": 'agy',
        "tier": 'Workhorse / Default',
        "sub_cost": 'AGY Sub (1B tokens/wk + 300M/5h)',
        "price_in": 0.38,
        "price_out": 1.88,
        "live_aliases": ['gemini-3.7-flash-high', 'gemini-3-7-flash-high', 'gemini-3.7-flash', 'gemini-3-7-flash'],
        "lm_aliases": ['gemini-3.7-flash', 'gemini-3-7-flash', 'gemini 3.7 flash (me', 'gemini 3.7 flash (lo', 'gemini-3.7-flash-thinking', 'gemini-3-7-flash-high', 'gemini-3-flashthinking-minimal'],
        "aa_aliases": ['gemini-3-7-flash', 'gemini-3.7-flash', 'gemini-3-7-flash-thinking', 'gemini-3-7-flash-medium', 'gemini-3-7-flash-low'],
        "base_metrics": {
            "speed_tps": 135.0,
        },
    },
    'gemini-3.8-flash': {
        "display": 'Gemini 3.8 Flash',
        "provider": 'Google',
        "pool": 'agy',
        "tier": 'Next-Gen Workhorse / Agentic Coding',
        "sub_cost": 'AGY Sub (1B tokens/wk + 300M/5h)',
        "price_in": 0.38,
        "price_out": 1.88,
        "live_aliases": ['gemini-3.8-flash-high', 'gemini-3-8-flash-high', 'gemini-3.8-flash', 'gemini-3-8-flash', 'gemini-3.8-flash-thinking'],
        "lm_aliases": ['gemini-3.8-flash', 'gemini-3-8-flash', 'gemini 3.8 flash', 'gemini-3.8-flash-high', 'gemini-3-8-flash-high'],
        "aa_aliases": ['gemini-3-8-flash', 'gemini-3.8-flash', 'gemini-3-8-flash-thinking'],
        "base_metrics": {
            "speed_tps": 140.0,
        },
    },
    'gemini-3.1-flash-lite': {
        "display": 'Gemini 3.1 Flash Lite',
        "provider": 'Google',
        "pool": 'agy',
        "tier": 'Ultra Fast / Bulk',
        "sub_cost": 'AGY Sub (1B tokens/wk + 300M/5h)',
        "price_in": 0.25,
        "price_out": 1.5,
        "live_aliases": ['gemini-3.1-flash-lite-preview-high', 'gemini-3-1-flash-lite'],
        "lm_aliases": ['gemini-3.1-flash-lite', 'gemini-3-1-flash-lite', 'gemini-3-1-flash-lite-preview'],
        "aa_aliases": ['gemini-3-1-flash-lite', 'gemini-3.1-flash-lite', 'gemini-3-1-flash-lite-preview'],
        "base_metrics": {
            "speed_tps": 180.0,
        },
    },
    'gemini-4-carbon-high': {
        "display": 'Gemini 4 Carbon (High)',
        "effort": 'high',
        "provider": 'Google',
        "pool": 'agy',
        "tier": 'Flagship Reasoning & Research (1M ctx)',
        "sub_cost": 'AGY Sub (Gemini Plans)',
        "price_in": 4.0,
        "price_out": 20.0,
        "context_length": 1_000_000,
        "live_aliases": ['gemini-4-carbon-high'],
        "lm_aliases": ['gemini 4 carbon (high)', 'gemini-4-carbon-high'],
        "aa_aliases": ['gemini-4-carbon-high'],
        "base_metrics": {"speed_tps": 72.0},
    },
    'gemini-4-carbon-medium': {
        "display": 'Gemini 4 Carbon (Medium)',
        "effort": 'medium',
        "provider": 'Google',
        "pool": 'agy',
        "tier": 'Grounded Synthesis & Coding (1M ctx)',
        "sub_cost": 'AGY Sub (Gemini Plans)',
        "price_in": 4.0,
        "price_out": 20.0,
        "context_length": 1_000_000,
        "live_aliases": ['gemini-4-carbon-medium'],
        "lm_aliases": ['gemini 4 carbon (medium)', 'gemini-4-carbon-medium'],
        "aa_aliases": ['gemini-4-carbon-medium'],
        "base_metrics": {"speed_tps": 72.0},
    },
    'gemini-4-carbon-low': {
        "display": 'Gemini 4 Carbon (Low)',
        "effort": 'low',
        "provider": 'Google',
        "pool": 'agy',
        "tier": 'Fast Frontier Drafts (1M ctx)',
        "sub_cost": 'AGY Sub (Gemini Plans)',
        "price_in": 4.0,
        "price_out": 20.0,
        "context_length": 1_000_000,
        "live_aliases": ['gemini-4-carbon-low'],
        "lm_aliases": ['gemini 4 carbon (low)', 'gemini-4-carbon-low'],
        "aa_aliases": ['gemini-4-carbon-low'],
        "base_metrics": {"speed_tps": 75.0},
    },
    'gemini-4-hydrogen-xhigh': {
        "display": 'Gemini 4 Hydrogen (Xhigh)',
        "effort": 'xhigh',
        "provider": 'Google',
        "pool": 'agy',
        "tier": 'High-Speed Agentic Workhorse (1M ctx)',
        "sub_cost": 'AGY Sub (Gemini Plans)',
        "price_in": 1.5,
        "price_out": 7.5,
        "context_length": 1_000_000,
        "live_aliases": ['gemini-4-hydrogen-xhigh'],
        "lm_aliases": ['gemini 4 hydrogen (xhigh)', 'gemini-4-hydrogen-xhigh'],
        "aa_aliases": ['gemini-4-hydrogen-xhigh'],
        "base_metrics": {"speed_tps": 178.0},
    },
    'gemini-4-hydrogen-high': {
        "display": 'Gemini 4 Hydrogen (High)',
        "effort": 'high',
        "provider": 'Google',
        "pool": 'agy',
        "tier": 'High-Speed Agentic Workhorse (1M ctx)',
        "sub_cost": 'AGY Sub (Gemini Plans)',
        "price_in": 1.5,
        "price_out": 7.5,
        "context_length": 1_000_000,
        "live_aliases": ['gemini-4-hydrogen-high'],
        "lm_aliases": ['gemini 4 hydrogen (high)', 'gemini-4-hydrogen-high'],
        "aa_aliases": ['gemini-4-hydrogen-high'],
        "base_metrics": {"speed_tps": 178.0},
    },
    'gemini-4-hydrogen-medium': {
        "display": 'Gemini 4 Hydrogen (Medium)',
        "effort": 'medium',
        "provider": 'Google',
        "pool": 'agy',
        "tier": 'High-Speed Agentic Loop (1M ctx)',
        "sub_cost": 'AGY Sub (Gemini Plans)',
        "price_in": 1.5,
        "price_out": 7.5,
        "context_length": 1_000_000,
        "live_aliases": ['gemini-4-hydrogen-medium'],
        "lm_aliases": ['gemini 4 hydrogen (medium)', 'gemini-4-hydrogen-medium'],
        "aa_aliases": ['gemini-4-hydrogen-medium'],
        "base_metrics": {"speed_tps": 178.0},
    },
    'gemini-4-hydrogen-low': {
        "display": 'Gemini 4 Hydrogen (Low)',
        "effort": 'low',
        "provider": 'Google',
        "pool": 'agy',
        "tier": 'Ultra-Fast Subagent Scout (1M ctx)',
        "sub_cost": 'AGY Sub (Gemini Plans)',
        "price_in": 1.5,
        "price_out": 7.5,
        "context_length": 1_000_000,
        "live_aliases": ['gemini-4-hydrogen-low'],
        "lm_aliases": ['gemini 4 hydrogen (low)', 'gemini-4-hydrogen-low'],
        "aa_aliases": ['gemini-4-hydrogen-low'],
        "base_metrics": {"speed_tps": 182.0},
    },
    'claude-opus-5-5-high': {
        "display": 'Claude Opus 5.5 (High)',
        "effort": 'high',
        "provider": 'Anthropic',
        "pool": 'agy',
        "tier": 'Flagship Reasoning / Architecture',
        "sub_cost": 'AGY Sub (Gemini Plans)',
        "price_in": 4.0,
        "price_out": 20.0,
        "context_length": 1_000_000,
        "live_aliases": ['claude-opus-5-5-high-effort'],
        "lm_aliases": ['claude opus 5.5 (high)', 'claude-opus-5.5-high'],
        "aa_aliases": ['claude-opus-5-5-high'],
        "base_metrics": {"speed_tps": 72.0},
    },
    'claude-opus-5-5-medium': {
        "display": 'Claude Opus 5.5 (Medium)',
        "effort": 'medium',
        "provider": 'Anthropic',
        "pool": 'agy',
        "tier": 'Balanced Architecture & Coding',
        "sub_cost": 'AGY Sub (Gemini Plans)',
        "price_in": 4.0,
        "price_out": 20.0,
        "context_length": 1_000_000,
        "live_aliases": ['claude-opus-5-5-medium-effort'],
        "lm_aliases": ['claude opus 5.5 (medium)', 'claude-opus-5.5-medium'],
        "aa_aliases": ['claude-opus-5-5-medium'],
        "base_metrics": {"speed_tps": 74.0},
    },
    'claude-opus-5-5-low': {
        "display": 'Claude Opus 5.5 (Low)',
        "effort": 'low',
        "provider": 'Anthropic',
        "pool": 'agy',
        "tier": 'Fast Opus Triage',
        "sub_cost": 'AGY Sub (Gemini Plans)',
        "price_in": 4.0,
        "price_out": 20.0,
        "context_length": 1_000_000,
        "live_aliases": ['claude-opus-5-5-low-effort'],
        "lm_aliases": ['claude opus 5.5 (low)', 'claude-opus-5.5-low'],
        "aa_aliases": ['claude-opus-5-5-low'],
        "base_metrics": {"speed_tps": 75.0},
    },
    'claude-sonnet-5-5-high': {
        "display": 'Claude Sonnet 5.5 (High)',
        "effort": 'high',
        "provider": 'Anthropic',
        "pool": 'agy',
        "tier": 'Elite Coding / Pair Coder',
        "sub_cost": 'AGY Sub (Gemini Plans)',
        "price_in": 2.0,
        "price_out": 10.0,
        "context_length": 1_000_000,
        "live_aliases": ['claude-sonnet-5-5-high-effort'],
        "lm_aliases": ['claude sonnet 5.5 (high)', 'claude-sonnet-5.5-high'],
        "aa_aliases": ['claude-sonnet-5-5-high'],
        "base_metrics": {"speed_tps": 64.0},
    },
    'claude-sonnet-5-5-medium': {
        "display": 'Claude Sonnet 5.5 (Medium)',
        "effort": 'medium',
        "provider": 'Anthropic',
        "pool": 'agy',
        "tier": 'Workhorse Coding / UI Craft',
        "sub_cost": 'AGY Sub (Gemini Plans)',
        "price_in": 2.0,
        "price_out": 10.0,
        "context_length": 1_000_000,
        "live_aliases": ['claude-sonnet-5-5-medium-effort'],
        "lm_aliases": ['claude sonnet 5.5 (medium)', 'claude-sonnet-5.5-medium'],
        "aa_aliases": ['claude-sonnet-5-5-medium'],
        "base_metrics": {"speed_tps": 66.0},
    },
    'claude-sonnet-5-5-low': {
        "display": 'Claude Sonnet 5.5 (Low)',
        "effort": 'low',
        "provider": 'Anthropic',
        "pool": 'agy',
        "tier": 'Fast Sonnet Loop',
        "sub_cost": 'AGY Sub (Gemini Plans)',
        "price_in": 2.0,
        "price_out": 10.0,
        "context_length": 1_000_000,
        "live_aliases": ['claude-sonnet-5-5-low-effort'],
        "lm_aliases": ['claude sonnet 5.5 (low)', 'claude-sonnet-5.5-low'],
        "aa_aliases": ['claude-sonnet-5-5-low'],
        "base_metrics": {"speed_tps": 68.0},
    },
    'gpt-5.6-sol': {
        "display": 'GPT-5.6 Sol (Reasoning)',
        "provider": 'OpenAI',
        "pool": 'frontier',
        "tier": 'Frontier Flagship Reasoning',
        "sub_cost": 'API ($2.00 / $10.00)',
        "price_in": 2.0,
        "price_out": 10.0,
        "live_aliases": ['gpt-5.6-sol-max', 'gpt-5-6-sol-max', 'gpt-5-6-sol'],
        "lm_aliases": ['gpt-5-6-sol-xhighcodex-harness', 'gpt-5-6-sol-xhighcodex', 'gpt-5-6-sol', 'gpt 5-6 sol-xhighcod'],
        "aa_aliases": ['gpt-5-6-sol', 'gpt-5-6-sol-xhigh', 'gpt-5-6-sol-high', 'gpt-5-6-sol-medium', 'gpt-5-6-sol-low'],
        "base_metrics": {
            "speed_tps": 45.0,
        },
    },
    'grok-4-6': {
        "display": 'Grok 4.6 (Reasoning)',
        "provider": 'xAI',
        "pool": 'frontier',
        "tier": 'Frontier Agentic Reasoning',
        "sub_cost": 'API ($2.00 / $6.00)',
        "price_in": 2.0,
        "price_out": 6.0,
        "live_aliases": ['grok-4.6', 'grok-4-6'],
        "lm_aliases": ['grok-4.6', 'grok-4-6', 'grok-4-0709', 'grok-4-6-high', 'grok-4.6-high'],
        "aa_aliases": ['grok-4-6', 'grok-4-6-xhigh', 'grok-4-6-high', 'grok-4-6-medium', 'grok-4-6-low'],
        "base_metrics": {
            "speed_tps": 55.0,
        },
    },
    'gpt-5.5': {
        "display": 'GPT 5.5 (xHigh)',
        "provider": 'OpenAI',
        "pool": 'frontier',
        "tier": 'Frontier Agentic Reasoning',
        "sub_cost": 'API ($5.00 / $30.00)',
        "price_in": 5.0,
        "price_out": 30.0,
        "live_aliases": ['gpt-5.5-xhigh', 'gpt-5.5-high', 'gpt-5-5-xhigh'],
        "lm_aliases": ['gpt-5-5-xhighcodex-harness', 'gpt-5-5-highcodex-harness', 'gpt-5-5', 'gpt 5-5-xhighcodex-h', 'gpt 5-5-highcodex-ha', 'gpt 5-5-instant'],
        "aa_aliases": ['gpt-5-5'],
        "base_metrics": {
            "speed_tps": 40.0,
        },
    },
    'gpt-5-6-terra': {
        "display": 'GPT-5.6 Terra (Reasoning)',
        "provider": 'OpenAI',
        "pool": 'frontier',
        "tier": 'Frontier High-Capacity',
        "sub_cost": 'API ($1.50 / $7.50)',
        "price_in": 1.5,
        "price_out": 7.5,
        "live_aliases": ['gpt-5.6-terra-max', 'gpt-5-6-terra-max'],
        "lm_aliases": ['gpt-5-6-terra-xhighcodex-harness', 'gpt-5-6-terra', 'gpt 5-6-terra-xhighc'],
        "aa_aliases": ['gpt-5-6-terra', 'gpt-5-6-terra-max', 'gpt-5-6-terra-high', 'gpt-5-6-terra-xhigh'],
        "base_metrics": {
            "speed_tps": 50.0,
        },
    },
    'gpt-5.4-pro': {
        "display": 'GPT-5.4 Pro',
        "provider": 'OpenAI',
        "pool": 'frontier',
        "tier": 'Enterprise Agentic Flagship',
        "sub_cost": 'API ($30.00 / $180.00)',
        "price_in": 30.0,
        "price_out": 180.0,
        "live_aliases": ['gpt-5.4-xhigh', 'gpt-5.4-high'],
        "lm_aliases": ['gpt-5.4-pro', 'gpt 5-4-highcodex-ha', 'gpt-5-4-highcodex-harness', 'gpt-5-4-mediumcodex-harness', 'gpt-5-4'],
        "aa_aliases": ['gpt-5.4-pro', 'gpt-5-4'],
        "base_metrics": {
            "speed_tps": 36.0,
        },
    },
    'gpt-5.2-codex': {
        "display": 'GPT-5.2 Codex',
        "provider": 'OpenAI',
        "pool": 'frontier',
        "tier": 'Coding Specialist / Agent',
        "sub_cost": 'API ($1.75 / $14.00)',
        "price_in": 1.75,
        "price_out": 14.0,
        "live_aliases": ['gpt-5.2-codex', 'gpt-5.2-2025-12-11-high'],
        "lm_aliases": ['gpt-5.2-codex', 'gpt-5.2', 'gpt-5-2-codex'],
        "aa_aliases": ['gpt-5-2-codex', 'gpt-5.2'],
        "base_metrics": {
            "speed_tps": 62.0,
        },
    },
    'gpt-oss-120b': {
        "display": 'GPT-OSS 120B (Medium)',
        "provider": 'OpenAI / Open-Weights',
        "pool": 'frontier',
        "tier": 'Open High-Efficiency',
        "sub_cost": 'Open-Weights / API ($0.04 / $0.17)',
        "price_in": 0.04,
        "price_out": 0.17,
        "live_aliases": ['gpt-oss-120b', 'gpt-oss-120b-medium'],
        "lm_aliases": ['gpt-oss-120b', 'gpt-oss-120b-medium'],
        "aa_aliases": ['gpt-oss-120b'],
        "base_metrics": {
            "speed_tps": 110.0,
        },
    },
    'grok-4.5': {
        "display": 'Grok 4.5',
        "provider": 'xAI',
        "pool": 'frontier',
        "tier": 'Frontier Agentic / Reasoning',
        "sub_cost": 'API ($2.00 / $6.00)',
        "price_in": 2.0,
        "price_out": 6.0,
        "live_aliases": ['grok-4.5', 'grok-4-5'],
        "lm_aliases": ['grok-4.5', 'grok-4-5'],
        "aa_aliases": ['grok-4-5', 'grok-4.5'],
        "base_metrics": {
            "speed_tps": 50.0,
        },
    },
    'qwen3-coder': {
        "display": 'Qwen3 Coder 480B',
        "provider": 'Alibaba',
        "pool": 'frontier',
        "tier": 'Open Coding Specialist',
        "sub_cost": 'Open-Weights / API ($0.30 / $1.00)',
        "price_in": 0.3,
        "price_out": 1.0,
        "live_aliases": ['qwen3-coder-480b', 'qwen3-coder'],
        "lm_aliases": ['qwen3-coder-480b', 'qwen3-coder', 'qwen3-coder-480b-a35b-instruct'],
        "aa_aliases": ['qwen3-coder-480b', 'qwen3-coder', 'qwen3-coder-480b-a35b-instruct'],
        "base_metrics": {
            "speed_tps": 80.0,
        },
    },
    'hunyuan-4-preview': {
        "display": 'Hunyuan 4 Preview',
        "provider": 'Tencent',
        "pool": 'api',
        "tier": 'Frontier Reasoning',
        "sub_cost": 'API ($0.83 / $2.50)',
        "price_in": 0.834,
        "price_out": 2.501,
        "live_aliases": ['hy4-preview', 'hunyuan-4-preview'],
        "lm_aliases": ['hy4-preview', 'tencent-hy4-preview', 'hunyuan-4-preview'],
        "aa_aliases": ['hy4-preview', 'tencent-hy4-preview'],
        "base_metrics": {
            "speed_tps": 48.0,
        },
    },
    'qwen3.8-max': {
        "display": 'Qwen3.8 Max',
        "provider": 'Alibaba',
        "pool": 'api',
        "tier": 'Tier 1 — High Reasoning',
        "sub_cost": 'API ($2.00 / $6.00)',
        "price_in": 2.0,
        "price_out": 6.0,
        "live_aliases": ['qwen3.8-max', 'qwen3-8-max'],
        "lm_aliases": ['qwen3.8-max', 'qwen3-8-max'],
        "aa_aliases": ['qwen-3-8-max', 'qwen3-8-max'],
        "base_metrics": {
            "speed_tps": 40.0,
        },
    },
    'qwen3.8-flash-next': {
        "display": 'Qwen3.8-Flash-Next',
        "provider": 'Alibaba',
        "pool": 'api',
        "tier": 'Ultra-Fast Reasoning',
        "sub_cost": 'API ($0.08 / $0.24)',
        "price_in": 0.08,
        "price_out": 0.24,
        "live_aliases": ['qwen3.8-flash-next', 'qwen3-8-flash-next'],
        "lm_aliases": ['qwen3.8-flash-next', 'qwen3-8-flash-next'],
        "aa_aliases": ['qwen-3-8-flash-next', 'qwen3-8-flash-next'],
        "base_metrics": {
            "speed_tps": 120.0,
        },
    },
    'qwen3.8-27b': {
        "display": 'Qwen3.8 27B',
        "provider": 'Alibaba',
        "pool": 'api',
        "tier": 'Fast Executor',
        "sub_cost": 'API ($0.40 / $3.00)',
        "price_in": 0.4,
        "price_out": 3.0,
        "live_aliases": ['qwen3.8-27b', 'qwen3-8-27b'],
        "lm_aliases": ['qwen3.8-27b', 'qwen3-8-27b'],
        "aa_aliases": ['qwen-3-8-27b', 'qwen3.8-27b'],
        "base_metrics": {
            "speed_tps": 90.0,
        },
    },
    'deepseek-v4.1-flash': {
        "display": 'DeepSeek V4.1 Flash',
        "provider": 'DeepSeek',
        "pool": 'api',
        "tier": 'Ultra-Fast Verifier & CED',
        "sub_cost": 'API ($0.15 / $0.60)',
        "price_in": 0.15,
        "price_out": 0.60,
        "live_aliases": ['deepseek-v4.1-flash-max', 'deepseek-v4.1-flash', 'deepseek-v4-1-flash'],
        "lm_aliases": ['deepseek-v4.1-flash-max', 'deepseek-v4.1-flash', 'deepseek-v4-1-flash'],
        "aa_aliases": ['deepseek-v4.1-flash', 'deepseek-v4-1-flash', 'deepseek-v4.1-flash-20260910'],
        "base_metrics": {
            "speed_tps": 110.0,
        },
    },
    'deepseek-v4-flash': {
        "display": 'DeepSeek V4 Flash',
        "provider": 'DeepSeek',
        "pool": 'api',
        "tier": 'Ultra-Fast Verifier',
        "sub_cost": 'API ($0.06 / $0.11)',
        "price_in": 0.06,
        "price_out": 0.11,
        "live_aliases": ['deepseek-v4-flash-vision-exp', 'deepseek-v4-flash-0731', 'deepseek-v4-flash'],
        "lm_aliases": ['deepseek-v4-flash', 'deepseek-v4-flash-high', 'deepseek-v4-flash-high-preview'],
        "aa_aliases": ['deepseek-v4-flash', 'deepseek-v4-flash-vision', 'deepseek-v4-flash-high'],
        "base_metrics": {
            "speed_tps": 95.0,
        },
    },
    'deepseek-v4-pro': {
        "display": 'DeepSeek V4 Pro',
        "provider": 'DeepSeek',
        "pool": 'api',
        "tier": 'Tier 2 — Verifier & Logic',
        "sub_cost": 'API ($0.41 / $0.83)',
        "price_in": 0.41,
        "price_out": 0.83,
        "live_aliases": ['deepseek-v4-pro-0813', 'deepseek-v4-pro'],
        "lm_aliases": ['deepseek-v4-pro'],
        "aa_aliases": ['deepseek-v4-pro'],
        "base_metrics": {
            "speed_tps": 38.0,
        },
    },
    'kimi-k3': {
        "display": 'Kimi K3 (Max)',
        "provider": 'Moonshot',
        "pool": 'api',
        "tier": 'Architecture & Reasoning',
        "sub_cost": 'API ($3.00 / $15.00)',
        "price_in": 3.0,
        "price_out": 15.0,
        "live_aliases": ['kimi-k3'],
        "lm_aliases": ['kimi-k3'],
        "aa_aliases": ['kimi-k3', 'kimi-k3-high', 'kimi-k3-low'],
        "base_metrics": {
            "speed_tps": 46.0,
        },
    },
    'kimi-k2.7-code': {
        "display": 'Kimi K2.7 Code',
        "provider": 'Moonshot',
        "pool": 'api',
        "tier": 'Code Specialist',
        "sub_cost": 'API ($0.95 / $4.00)',
        "price_in": 0.95,
        "price_out": 4.0,
        "live_aliases": ['kimi-k2.7-code', 'kimi-k2-7-code'],
        "lm_aliases": ['kimi-k2.7-code', 'kimi-k2-7-code'],
        "aa_aliases": ['kimi-k2.7-code'],
        "base_metrics": {
            "speed_tps": 55.0,
        },
    },
    'glm-5.3': {
        "display": 'GLM-5.3',
        "provider": 'Zhipu AI',
        "pool": 'api',
        "tier": 'Tier 1 — Architecture & Spec',
        "sub_cost": 'API ($1.40 / $4.40)',
        "price_in": 1.4,
        "price_out": 4.4,
        "live_aliases": ['glm-5.3', 'glm-5-3'],
        "lm_aliases": ['glm-5.3', 'glm-5-3', 'glm-5-3-max'],
        "aa_aliases": ['glm-5-3', 'glm-5.3', 'glm-5-3-max', 'glm-5.3-max'],
        "base_metrics": {
            "speed_tps": 42.0,
        },
    },
    'glm-5.2': {
        "display": 'GLM-5.2',
        "provider": 'Zhipu AI',
        "pool": 'api',
        "tier": 'Tier 1 — Architecture',
        "sub_cost": 'API ($1.40 / $4.40)',
        "price_in": 1.4,
        "price_out": 4.4,
        "live_aliases": ['glm-5.2', 'glm-5-2'],
        "lm_aliases": ['glm-5.2', 'glm-5-2', 'glm-5-2-max'],
        "aa_aliases": ['glm-5-2', 'glm-5.2', 'glm-5-2-max', 'glm-5.2-max'],
        "base_metrics": {
            "speed_tps": 60.0,
        },
    },
    'glm-5.3-flash': {
        "display": 'GLM-5.3 Flash',
        "provider": 'Zhipu AI',
        "pool": 'api',
        "tier": 'Fast Executor',
        "sub_cost": 'API ($0.15 / $0.50)',
        "price_in": 0.15,
        "price_out": 0.5,
        "live_aliases": ['glm-5.3-flash', 'glm-5-3-flash'],
        "lm_aliases": ['glm-5.3-flash', 'glm-5-3-flash'],
        "aa_aliases": ['glm-5-3-flash', 'glm-5.3-flash'],
        "base_metrics": {
            "speed_tps": 110.0,
        },
    },
    'muse-spark-1-2': {
        "display": 'Muse Spark 1.2 (Contributor)',
        "provider": 'Muse',
        "pool": 'api',
        "tier": 'Fast Contributor Specialist',
        "sub_cost": 'API ($0.10 / $0.20)',
        "price_in": 0.1,
        "price_out": 0.2,
        "live_aliases": ['muse-spark-1.2-xhigh', 'muse-spark-1-2-xhigh', 'muse-spark-1.2', 'muse-spark-1-2'],
        "lm_aliases": ['muse-spark-1-2xhigh', 'muse-spark-1-2-xhigh', 'muse-spark-1.2-xhigh', 'muse-spark-1-2', 'muse-spark-1.2', 'muse-spark-1.2-contributor'],
        "aa_aliases": ['muse-spark-1.2', 'muse-spark-1-2', 'muse-spark-1.2-contributor'],
        "base_metrics": {
            "speed_tps": 130.0,
        },
    },
    'gpt-5.6-luna': {
        "display": 'GPT 5.6 Luna',
        "provider": 'OpenAI',
        "pool": 'api',
        "tier": 'High-Efficiency Failover',
        "sub_cost": 'API ($0.20 / $1.20)',
        "price_in": 0.2,
        "price_out": 1.2,
        "live_aliases": ['gpt-5.6-luna-max', 'gpt-5-6-luna-max'],
        "lm_aliases": ['gpt-5-6-luna-xhighcodex-harness', 'gpt-5-6-luna', 'gpt 5-6 luna-xhighco'],
        "aa_aliases": ['gpt-5-6-luna'],
        "base_metrics": {
            "speed_tps": 60.0,
        },
    },
    'minimax-m3': {
        "display": 'MiniMax M3',
        "provider": 'MiniMax',
        "pool": 'api',
        "tier": 'General Executor',
        "sub_cost": 'API ($0.30 / $1.20)',
        "price_in": 0.3,
        "price_out": 1.2,
        "live_aliases": ['minimax-m3'],
        "lm_aliases": ['minimax-m3', 'minimax-m3-high', 'minimax-m3-reasoning', 'm3'],
        "aa_aliases": ['minimax-m3'],
        "base_metrics": {
            "speed_tps": 75.0,
        },
    },
    'mimo-v2.5': {
        "display": 'MiMo-V2.5',
        "provider": 'Xiaomi',
        "pool": 'api',
        "tier": 'Bulk Fill',
        "sub_cost": 'API ($0.14 / $0.28)',
        "price_in": 0.14,
        "price_out": 0.28,
        "live_aliases": ['mimo-v2.5', 'mimo-v2-5', 'mimo-v2-pro'],
        "lm_aliases": ['mimo-v2.5', 'mimo-v2-5', 'mimo-v2-5-pro'],
        "aa_aliases": ['mimo-v2-5', 'mimo-v2.5', 'mimo-v2-5-0424', 'mimo-v2-5-pro'],
        "base_metrics": {
            "speed_tps": 115.0,
        },
    },
    'muse-spark-1.3': {
        "display": 'Muse Spark 1.3 (Max)',
        "provider": 'Meta / Muse',
        "pool": 'api',
        "tier": 'Elite Fast Frontier / High TPS',
        "sub_cost": 'OpenCode / CommandCode / Free',
        "price_in": 0.35,
        "price_out": 1.5,
        "live_aliases": ['muse-spark-1.3-xhigh', 'muse-spark-1-3-xhigh', 'muse-spark-1.3-max', 'muse-spark-1-3-max', 'muse-spark-1.3', 'muse-spark-1-3'],
        "lm_aliases": ['muse-spark-1-3xhigh', 'muse-spark-1-3-xhigh', 'muse-spark-1.3-xhigh', 'muse-spark-1.3', 'muse-spark-1-3', 'muse-spark-1.3-contributor'],
        "aa_aliases": ['muse-spark-1-3', 'muse-spark-1.3', 'muse-spark-1-3-max', 'muse-spark-1-3-xhigh', 'muse-spark-1.3-xhigh', 'meta/muse-spark-1.3'],
        "base_metrics": {
            "speed_tps": 190.0,
        },
    },
    'qwen3.8-27b-hetzner': {
        "display": 'Qwen 3.8 27B (Hetzner)',
        "provider": 'Alibaba / Hetzner',
        "pool": 'hetzner',
        "tier": 'Free Long-Context Specialist (262k)',
        "sub_cost": 'Hetzner Free Inference (262k ctx)',
        "price_in": 0.2,
        "price_out": 0.6,
        "live_aliases": ['qwen3.8-27b', 'qwen-3.8-27b', 'qwen-3-8-27b'],
        "lm_aliases": ['qwen3.8-27b', 'qwen-3.8-27b', 'qwen3-8-27b'],
        "aa_aliases": ['qwen3.8-27b', 'qwen-3.8-27b', 'qwen-3-8-27b', 'qwen3-8-27b'],
        "base_metrics": {
            "speed_tps": 95.0,
        },
    },
    'kimi-k3-nvidia': {
        "display": 'Kimi K3 (NVIDIA NIM)',
        "provider": 'Moonshot / NVIDIA',
        "pool": 'nvidia',
        "tier": 'Frontier Long-Context Reasoning',
        "sub_cost": 'NVIDIA Integrate API ($0 / NIM credits)',
        "price_in": 0.8,
        "price_out": 3.2,
        "live_aliases": ['kimi-k3', 'kimi-k-3'],
        "lm_aliases": ['kimi-k3', 'kimi-k-3', 'kimi-k3-max'],
        "aa_aliases": ['kimi-k3', 'kimi-k-3'],
        "base_metrics": {
            "speed_tps": 75.0,
        },
    },
}
# ==============================================================================
# 2. LIVE FETCHERS, SNAPSHOTS & PARSERS
# ==============================================================================

LIVEBENCH_TABLE_DATE = "2026-06-25"  # release date baked into the CSV path; the feed is not daily
LIVEBENCH_CSV_URL = f"https://livebench.ai/v1/table_{LIVEBENCH_TABLE_DATE.replace('-', '_')}.csv"
LIVEBENCH_CAT_URL = f"https://livebench.ai/v1/categories_{LIVEBENCH_TABLE_DATE.replace('-', '_')}.json"
AA_URL = "https://artificialanalysis.ai/leaderboards/models"
CACHE_TTL_H = bc.CACHE_TTL_H  # canonical 24h freshness window lives in benchmark_common (rule 7)

_DISPLAY_RULES: list[tuple[tuple[str, ...], str, str | None, str, tuple[tuple[str, str], ...]]] = [
    (("glm",), "Zhipu AI", r"^glm[-_]?\s*", "GLM-", (("-flash", " Flash"), ("_flash", " Flash"), ("-turbo", " Turbo"), ("-fast", " Fast"))),
    (("qwen",), "Alibaba", r"^qwen[-_]?\s*", "Qwen", (("-max", " Max"), ("-plus", " Plus"), ("-flash", " Flash"), ("-coder", " Coder"))),
    (("deepseek",), "DeepSeek", r"^deepseek[-_]?\s*", "DeepSeek ", (("-v4.1", " V4.1"), ("-v4", " V4"), ("-v3", " V3"), ("-pro", " Pro"), ("-flash", " Flash"), ("-vision", " Vision"), ("-exp", " Exp"), ("-fast", " Fast"))),
    (("kimi",), "Moonshot", r"^kimi[-_]?\s*", "Kimi ", (("-k3", " K3"), ("-k2.7", " K2.7"), ("-k2.6", " K2.6"), ("-k2.5", " K2.5"), ("-code", " Code"), ("-max", " Max"))),
    (("hy", "hunyuan"), "Tencent", None, "", (("hy4-preview", "Hunyuan 4 Preview"), ("hy3-preview", "Hunyuan 3 Preview"), ("hy3", "Hunyuan 3"))),
    (("minimax",), "MiniMax", r"^minimax[-_]?\s*", "MiniMax ", (("-m3", " M3"), ("-m2.7", " M2.7"), ("-m2.5", " M2.5"))),
    (("mimo",), "Xiaomi", r"^mimo[-_]?\s*", "MiMo-", (("-pro", " Pro"), ("-omni", " Omni"), ("-v2.5", "V2.5"), ("-v2", "V2"))),
    (("grok",), "xAI", r"^grok[-_]?\s*", "Grok ", ()),
    (("gpt", "o3", "o4"), "OpenAI", r"^gpt[-_]?\s*", "GPT ", (("-luna", " Luna"), ("-sol", " Sol"), ("-terra", " Terra"), ("-codex", " Codex"), ("-oss", "-OSS"))),
    (("claude", "fable", "opus", "sonnet", "haiku"), "Anthropic", r"^claude[-_]?\s*", "Claude ", (("opus", "Opus"), ("sonnet", "Sonnet"), ("haiku", "Haiku"), ("fable", "Fable"))),
    (("gemini", "gemma"), "Google", r"^gemini[-_]?\s*", "Gemini ", ()),
    (("llama",), "Meta", r"^llama[-_]?\s*", "Llama ", ()),
    (("step",), "StepFun", r"^step[-_]?\s*", "Step ", (("-flash", " Flash"),)),
]


def _apply_display_rule(mid: str, rule) -> tuple[str, str]:
    """Apply matched display rule with whitespace collapsing."""
    _, prov, pat, repl, subs = rule
    disp = re.sub(pat, repl, mid, flags=re.I) if pat else mid
    for old, new in subs:
        disp = disp.replace(old, new)
    if prov in ("DeepSeek", "Kimi", "MiniMax"):
        disp = re.sub(r"\b([kKmMvV])(\d)", lambda m: m.group(1).upper() + m.group(2), disp)
    if prov == "Anthropic" and not disp.startswith("Claude "):
        disp = "Claude " + disp
    return re.sub(r"\s+", " ", disp).strip(), prov


def _format_muse_name(mid: str, low: str) -> str:
    ver = "1.2" if ("1-2" in low or "1.2" in low) else ("1.3" if ("1-3" in low or "1.3" in low) else "")
    if not ver:
        return mid.replace("-", " ").title()
    variant = " Contributor" if "contrib" in low else ""
    return f"Muse Spark {ver}{variant}".strip()


def format_model_display_name(mid: str) -> tuple[str, str]:
    """Map a model identifier to (display_name, provider_name)."""
    low = mid.lower().strip()
    if low.startswith(("mistral", "codestral", "pixtral")):
        return re.sub(r"\s+", " ", mid.replace("-", " ").title()).strip(), "Mistral"
    if low.startswith("muse"):
        return _format_muse_name(mid, low), "Muse"
    if low.startswith("longcat"):
        return "LongCat 2.0 (Meituan)", "Meituan"
    for rule in _DISPLAY_RULES:
        if any(low.startswith(pfx) for pfx in rule[0]):
            return _apply_display_rule(mid, rule)
    return re.sub(r"\s+", " ", mid.replace("-", " ").replace("_", " ").title()).strip(), "Upstream API"


def _index_openrouter_pricing_item(item: dict, or_pricing: dict) -> None:
    """Register one OpenRouter catalog item; keep `:variant` SKUs off bare keys."""
    mid = item.get("id")
    if not mid:
        return
    pr = item.get("pricing") or {}
    pin_v = bc._safe_float(pr.get("prompt"))
    pout_v = bc._safe_float(pr.get("completion"))
    pricing = {
        "price_in": (pin_v * 1_000_000) if pin_v is not None else 0.0,
        "price_out": (pout_v * 1_000_000) if pout_v is not None else 0.0,
        "name": item.get("name") or mid,
        "context_length": item.get("context_length"),
    }
    or_pricing[bc.norm_id(mid)] = pricing
    if ":" not in mid:
        or_pricing.setdefault(bc.norm_id(mid.split("/", 1)[-1]), pricing)


def load_openrouter_pricing_data():
    """Load OpenRouter model pricing and metadata if available."""
    or_matches = sorted(glob.glob(str(RAW / "*openrouter_models*20*.json")))
    if not or_matches:
        return {}
    or_pricing: dict = {}
    with contextlib.suppress(Exception):
        data = json.loads(pathlib.Path(or_matches[-1]).read_text(encoding="utf-8", errors="ignore"))
        items = sorted(data.get("data", []), key=lambda x: ":" in (x.get("id") or ""))
        for item in items:
            _index_openrouter_pricing_item(item, or_pricing)
    return or_pricing


def _resolve_prices(nid: str, or_pricing: dict, aa_norm: dict) -> tuple:
    """Real per-1M prices for a model id: OpenRouter first, Artificial Analysis second, None when truly unknown.

    Never invents a price (previously OR/AA-absent rows silently got $1.00/$3.00,
    fabricating effective costs, AVI, and Pareto membership for ~200 catalog rows).
    """
    or_p = or_pricing.get(nid) or {}
    pi, po = or_p.get("price_in"), or_p.get("price_out")
    if pi is None or po is None:
        aa_rec = aa_norm.get(nid) or {}
        if pi is None:
            pi = aa_rec.get("price_in")
        if po is None:
            po = aa_rec.get("price_out")
    return pi, po


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



_EFFORT_RANK: dict[str, int] = {
    "max": 6, "xhigh": 5, "high": 4, "medium": 3, "low": 2, "minimal": 1, "non-reasoning": 0,
}
_BARE_CLAUDE_PREFIXES = ("fable-", "opus-", "sonnet-", "haiku-")
_FAMILY_SLUG_ALIASES: dict[str, str] = {
    "muse-wonder-1-0": "muse-wonder",
    "deepseek-v4-1-flash-1017": "deepseek-v4-1-flash",
    "deepseek-v4-flash-vision-exp": "deepseek-v4-flash-vision",
    "qwen3-8-max-0902": "qwen3-8-max",
    "gpt-6-sol-daybreak-blue": "gpt-6-sol",
    "gpt-6-sol-daybreak-blue-daybreak-blue": "gpt-6-sol",
}
_AA_SUB_METRIC_MAP: tuple[tuple[str, str], ...] = (
    ("terminalbench4", "aa_tb4"),
    ("frontiercode2", "aa_fc2"),
    ("hle", "aa_hle"),
    ("critptHard", "aa_critpt"),
    ("scicode", "aa_scicode"),
    ("gpqa", "aa_gpqa"),
    ("ifbench", "aa_ifbench"),
    ("longContextReasoning", "aa_lcr"),
    ("omniscienceNonHallucination", "aa_non_halluc"),
    ("omniscienceAccuracy", "aa_omni_acc"),
    ("tau2", "aa_tau2"),
    ("costPerTask", "aa_cost_per_task"),
)


def strip_effort_suffix(slug: str) -> str:
    """Strip secondary effort/thinking suffixes while preserving Qwen/Mistral model-size tiers."""
    s = re.sub(r"(\d+)(xhigh|high|medium|low|minimal|max)$", r"\1-\2", slug or "")
    low = s.lower()
    if low.startswith("qwen") and low.endswith(("-max", "_max")):
        return s
    if low.startswith(("mistral", "devstral", "magistral", "ministral", "pixtral", "voxtral")) and low.endswith(("-medium", "_medium")):
        return s
    return re.sub(
        r"[-_](high|xhigh|medium|low|minimal|max|adaptive|thinking|reasoning|non-reasoning|preview|contributor|base)(-effort)?$",
        "",
        s,
        flags=re.I,
    )


def _canon_family_slug(raw: str) -> str:
    base = strip_effort_suffix(bc.norm_model_slug(raw))
    base = re.sub(r"-(?:20\d{6}|\d{4})$", "", base)
    for pref in _BARE_CLAUDE_PREFIXES:
        if base.startswith(pref):
            base = "claude-" + base
            break
    return _FAMILY_SLUG_ALIASES.get(base, base)


def _record_effort(slug: str, rec: dict | None = None) -> str | None:
    d = bc._as_dict(rec)
    return (
        normalize_effort(d.get("effort"))
        or extract_effort_from_label(d.get("name") or d.get("display"))
        or extract_effort_from_label(slug)
    )


def _is_synthetic_fallback(slug: str, rec: dict, tier: str) -> bool:
    if rec.get("is_fallback"):
        return True
    return bool(tier == "Upstream API" and rec.get("slug") and slug != rec.get("slug"))


def _norm_variants_index(src_map):
    out = {}
    for k, v in (src_map or {}).items():
        out[bc.norm_id(k)] = v
        out[bc.norm_id(k.replace(".", "-"))] = v
        out[bc.norm_model_slug(k)] = v
    return out


def _best_base_index(src_map, metric_key, strip_fn=strip_effort_suffix, include_arena=False):
    out = {}
    for k, v in (src_map or {}).items():
        val = v.get(metric_key)
        if not bc._is_num(val):
            continue
        keys = [
            bc.norm_id(strip_fn(k)),
            bc.norm_id(strip_fn(k.replace(".", "-"))),
            bc.norm_model_slug(strip_fn(k)),
            _canon_family_slug(strip_fn(k)),
        ]
        if include_arena:
            keys.extend([bc.arena_base_key(k), bc.arena_token_key(k)])
        for bk in keys:
            if bk and (bk not in out or val > (out[bk].get(metric_key) or 0)):
                out[bk] = v
    return out


def _collect_upstream_efforts(*maps: tuple[str, dict | None]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for tier, smap in maps:
        for slug, rec in (smap or {}).items():
            d = bc._as_dict(rec)
            if _is_synthetic_fallback(slug, d, tier):
                continue
            eff = _record_effort(slug, d)
            if eff:
                out.setdefault(_canon_family_slug(slug), set()).add(eff)
    return out


def _bind_catalog_efforts(catalog: dict, up_effs: dict[str, set[str]]) -> dict[str, dict]:
    fam_meta: dict[str, dict] = {}
    for cid, info in catalog.items():
        fam = _canon_family_slug(cid)
        if fam not in fam_meta:
            fam_meta[fam] = {
                "provider": info.get("provider"),
                "pool": info["pool"] if info.get("pool") in ("claude", "frontier", "api") else "api",
                "tier": info.get("tier"),
                "sub_cost": info["sub_cost"] if info.get("pool") in ("claude", "frontier") else "API",
            }
        eff = _record_effort(cid, info)
        if eff is None and fam in up_effs:
            top_eff = max(up_effs[fam], key=lambda e: _EFFORT_RANK.get(e, 0))
            base_disp = re.sub(r"\s*\((?:Thinking|Reasoning)\)\s*$", "", info.get("display") or cid).strip()
            info["display"] = f"{base_disp} ({EFFORT_DISPLAY[top_eff]})"
            info["effort"] = top_eff
            vslug = f"{fam}-{top_eff}"
            info["live_aliases"] = [vslug, f"{vslug}-effort"]
            info["lm_aliases"] = [vslug, f"{base_disp.lower()} ({top_eff})"]
            info["aa_aliases"] = [vslug]
        else:
            info["effort"] = eff
    return fam_meta


def _register_entry_keys(key_index: dict, seen_families: set[str], cid: str, info: dict) -> None:
    fam = _canon_family_slug(cid)
    eff = info.get("effort")
    seen_families.add(fam)
    key_index.setdefault(f"{fam}::{eff or 'none'}", cid)
    key_index.setdefault(bc.norm_id(cid), cid)
    key_index.setdefault(bc.norm_model_slug(cid), cid)
    if eff is None:
        key_index.setdefault(fam, cid)
        for a in (*info.get("live_aliases", []), *info.get("lm_aliases", []), *info.get("aa_aliases", [])):
            if a:
                key_index.setdefault(bc.norm_id(a), cid)
                key_index.setdefault(bc.norm_model_slug(a), cid)


def _ensure_effort_in_display(disp: str, eff: str | None) -> str:
    cleaned = clean_display_name(disp)
    if not eff or extract_effort_from_label(cleaned) == eff:
        return cleaned
    return f"{cleaned} ({EFFORT_DISPLAY[eff]})"


def _resolve_ingested_prices(nid: str, fam: str, rec: dict, or_pricing: dict, aa_norm: dict) -> tuple:
    p_in, p_out = rec.get("price_in"), rec.get("price_out")
    if p_in is not None and p_out is not None:
        return p_in, p_out
    p_in, p_out = _resolve_prices(nid, or_pricing, aa_norm)
    if p_in is not None and p_out is not None:
        return p_in, p_out
    return _resolve_prices(bc.norm_id(fam), or_pricing, aa_norm)


def _resolve_ingested_pool_prov(fam: str, default_prov: str, meta: dict) -> tuple[str, str, str]:
    is_claude = fam.startswith("claude-")
    prov = "Anthropic" if is_claude else (meta.get("provider") or default_prov)
    pool = meta.get("pool") or ("claude" if is_claude else "api")
    sub = meta.get("sub_cost") or ("Claude Max / API" if pool == "claude" else "API")
    return prov, pool, sub


def _build_ingested_entry(
    slug: str, raw: str, nid: str, fam: str, eff: str | None, rec: dict,
    tier: str, or_pricing: dict, aa_norm: dict, fam_meta: dict[str, dict],
) -> dict:
    disp_fmt, prov0 = format_model_display_name(raw)
    name_raw = rec.get("name")
    cand = name_raw if (name_raw and name_raw != slug) else disp_fmt
    meta = fam_meta.get(fam) or {}
    prov, pool, sub_cost = _resolve_ingested_pool_prov(fam, prov0, meta)
    p_in, p_out = _resolve_ingested_prices(nid, fam, rec, or_pricing, aa_norm)
    bare = rec.get("bare_slug") or slug.split("/")[-1]
    aliases = [slug, bare, raw] if tier == "Vals Model" else [slug]
    tps = rec.get("medianTps")
    entry = {
        "display": _ensure_effort_in_display(cand, eff),
        "effort": eff,
        "provider": prov,
        "pool": pool,
        "tier": meta.get("tier") or tier,
        "sub_cost": sub_cost,
        "price_in": p_in,
        "price_out": p_out,
        "aa_aliases": list(aliases),
        "base_metrics": {"speed_tps": tps} if tps else {},
    }
    if tier != "Benchmark Model":
        entry["live_aliases"] = list(aliases)
        entry["lm_aliases"] = list(aliases)
    return entry


_AA_SIGNAL_KEYS = (
    "intelligenceIndex", "codingIndex", "hle", "critptHard",
    "terminalbench4", "frontiercode2", "scicode", "gpqa", "ifbench", "omniscienceNonHallucination",
)


def _has_aa_eval(rec: dict) -> bool:
    return any(rec.get(k) is not None for k in _AA_SIGNAL_KEYS)


def _should_skip_ingest(slug: str, raw: str, fam: str, eff: str | None, rec: dict, tier: str, key_index: dict, seen_families: set[str]) -> bool:
    if tier == "Vals Model" and "/" not in slug:
        return True
    if _is_synthetic_fallback(slug, rec, tier):
        return True
    if tier == "Upstream API" and not _has_aa_eval(rec):
        return True
    if eff:
        return (f"{fam}::{eff}" in key_index) or (f"{fam}::none" in key_index)
    return (fam in seen_families) or (bc.norm_id(raw) in key_index) or (bc.norm_model_slug(raw) in key_index)


def _ingest_source_models(catalog, key_index, seen_families, source_map, or_pricing, aa_norm, tier, fam_meta, strip_fn=strip_effort_suffix):
    for slug, raw_rec in (source_map or {}).items():
        rec = bc._as_dict(raw_rec)
        raw = (rec.get("bare_slug") or slug.split("/")[-1]).replace("_", "-") if tier == "Vals Model" else slug
        fam = _canon_family_slug(strip_fn(raw) if strip_fn is livebench_base_name else raw)
        eff = _record_effort(slug, rec)
        if _should_skip_ingest(slug, raw, fam, eff, rec, tier, key_index, seen_families):
            continue
        cid_raw = f"{fam}-{eff}" if eff else raw
        nid = bc.norm_id(cid_raw)
        if nid in catalog:
            nid = f"{nid}-{eff}" if eff else nid
        entry = _build_ingested_entry(slug, raw, nid, fam, eff, rec, tier, or_pricing, aa_norm, fam_meta)
        catalog[nid] = entry
        _register_entry_keys(key_index, seen_families, cid_raw, entry)


def _rank_val_for_index(rec: dict, score_key: str) -> float | None:
    val = bc._safe_float(rec.get(score_key))
    if val is not None:
        return val
    return 0.0 if (score_key == "intelligenceIndex" and _has_aa_eval(rec)) else None


def _index_fam_effort(src_map: dict | None, tier: str, score_key: str, base_fn=None) -> dict[tuple[str, str | None], dict]:
    out: dict[tuple[str, str | None], dict] = {}
    for slug, raw_rec in (src_map or {}).items():
        rec = bc._as_dict(raw_rec)
        if _is_synthetic_fallback(slug, rec, tier):
            continue
        rank_val = _rank_val_for_index(rec, score_key)
        if rank_val is None:
            continue
        stem = base_fn(slug) if base_fn else slug
        key = (_canon_family_slug(stem), _record_effort(slug, rec))
        prev = out.get(key)
        if prev is None or rank_val > (_rank_val_for_index(prev, score_key) or 0.0):
            out[key] = rec
    return out


def _lookup_effort_strict(
    idx: dict[tuple[str, str | None], dict], fam: str, row_eff: str | None, is_flagship: bool, allow_untagged_flagship: bool = False,
) -> dict | None:
    if row_eff:
        exact = idx.get((fam, row_eff))
        if exact or not (allow_untagged_flagship and is_flagship):
            return exact
        return idx.get((fam, None))
    return idx.get((fam, None))


def _attach_livebench_signal(mid: str, m: dict, fam: str, row_eff: str | None, is_flagship: bool, lb_idx: dict, live_norm: dict, live_base: dict) -> None:
    rec = _lookup_effort_strict(lb_idx, fam, row_eff, is_flagship, allow_untagged_flagship=True)
    if rec is None and row_eff is None:
        for c in (*m.get("live_aliases", []), mid, m.get("display")):
            if c and (hit := live_norm.get(bc.norm_id(c)) or live_base.get(bc.norm_id(strip_effort_suffix(c)))):
                rec = hit
                break
    if rec:
        m["livebench"] = rec


def _fallback_lm_alias(cands: tuple, row_eff: str | None, lm_norm: dict, lm_base: dict, lm_slug_of: dict) -> dict | None:
    for c in cands:
        if not c:
            continue
        cand = lm_norm.get(bc.norm_id(c))
        if cand is None and row_eff is None:
            cand = lm_base.get(bc.arena_base_key(c))
        if cand and _record_effort(lm_slug_of.get(id(cand), ""), cand) in (None, row_eff):
            return cand
    return None


def _attach_lm_signal(mid: str, m: dict, fam: str, row_eff: str | None, is_flagship: bool, lm_idx: dict, lm_norm: dict, lm_base: dict, lm_slug_of: dict) -> None:
    rec = _lookup_effort_strict(lm_idx, fam, row_eff, is_flagship, allow_untagged_flagship=True)
    if rec is None and (row_eff is None or is_flagship):
        rec = _fallback_lm_alias((*m.get("lm_aliases", []), mid, m.get("display")), row_eff, lm_norm, lm_base, lm_slug_of)
    if rec and rec.get("elo"):
        bm = m.setdefault("base_metrics", {})
        bm["lm_elo"] = rec["elo"]
        bm["lm_match"] = lm_slug_of.get(id(rec))
        if rec.get("coding"):
            bm["lm_coding"] = rec["coding"]


def _apply_aa_record(m: dict, rec: dict) -> None:
    bm = m.setdefault("base_metrics", {})
    if rec.get("intelligenceIndex") is not None:
        bm["aa_quality"] = rec["intelligenceIndex"]
        m["aa_live_quality"] = rec["intelligenceIndex"]
    if rec.get("codingIndex") is not None:
        bm["aa_coding"] = rec["codingIndex"]
        m["aa_live_coding"] = rec["codingIndex"]
    if rec.get("medianTps") is not None:
        bm["speed_tps"] = rec["medianTps"]
    for src_k, dst_k in _AA_SUB_METRIC_MAP:
        if rec.get(src_k) is not None:
            bm[dst_k] = rec[src_k]
    if m.get("price_in") is None and rec.get("price_in") is not None:
        m["price_in"] = rec["price_in"]
    if m.get("price_out") is None and rec.get("price_out") is not None:
        m["price_out"] = rec["price_out"]


def _attach_aa_signal(mid: str, m: dict, fam: str, row_eff: str | None, aa_idx: dict, aa_norm: dict, aa_base: dict) -> None:
    rec = _lookup_effort_strict(aa_idx, fam, row_eff, is_flagship=False)
    if rec is None and row_eff is None:
        for c in (*m.get("aa_aliases", []), mid, m.get("display")):
            if c and (hit := aa_norm.get(bc.norm_id(c)) or aa_base.get(bc.norm_model_slug(strip_effort_suffix(c)))):
                rec = hit
                break
    if rec:
        _apply_aa_record(m, rec)


def _attach_fc2_signal(m: dict, fam: str, row_eff: str | None, fc2_idx: dict, fc2_map: dict) -> None:
    rec = _lookup_effort_strict(fc2_idx, fam, row_eff, is_flagship=False)
    if rec is None and row_eff is None:
        rec = fc2_map.get(fam)
    if rec:
        bm = m.setdefault("base_metrics", {})
        for k in ("fc2_score", "fc2_correct", "fc2_cost", "fc2_tokens"):
            if rec.get(k) is not None:
                bm[k] = rec[k]


def _attach_cursor_signal(m: dict, fam: str, row_eff: str | None, cur_idx: dict, cursor_map: dict) -> None:
    rec = _lookup_effort_strict(cur_idx, fam, row_eff, is_flagship=False)
    if rec is None and row_eff is None:
        rec = cursor_map.get(fam)
    if rec:
        bm = m.setdefault("base_metrics", {})
        for k in ("cursor_score", "cursor_cost", "cursor_tokens", "cursor_steps"):
            if rec.get(k) is not None:
                bm[k] = rec[k]


def _attach_fswe_signal(m: dict, fam: str, is_flagship: bool, fswe_by_fam: dict) -> None:
    if not is_flagship:
        return
    rec = fswe_by_fam.get(fam)
    if rec:
        bm = m.setdefault("base_metrics", {})
        for k in ("fswe_overall", "fswe_impl", "fswe_perf", "fswe_research", "fswe_cost"):
            if rec.get(k) is not None:
                bm[k] = rec[k]


def _attach_vals_signal(m: dict, fam: str, is_flagship: bool, vals_map: dict) -> None:
    if not is_flagship or not vals_map:
        return
    probe = dict(m, aa_aliases=[*m.get("aa_aliases", []), fam])
    v_match = bc.find_vals_for_model(probe, vals_map)
    if not v_match:
        return
    m["vals_metrics"] = v_match
    for k in ("vals_overall", "vals_coding", "vals_terminal", "vals_coding_blend", "vals_cost_per_test", "vals_latency"):
        m[k] = v_match.get(k)


def _attach_context_length(mid: str, m: dict, fam: str, or_pricing: dict, aa_norm: dict, aa_base: dict) -> None:
    if m.get("context_length") is not None:
        return
    cands = [mid, fam, m.get("display"), *m.get("live_aliases", []), *m.get("lm_aliases", []), *m.get("aa_aliases", [])]
    for c in cands:
        if not c:
            continue
        cn = bc.norm_id(c)
        or_info = or_pricing.get(cn) or or_pricing.get(bc.norm_id(strip_effort_suffix(c)))
        if or_info and or_info.get("context_length"):
            m["context_length"] = or_info["context_length"]
            return
        aa_rec = aa_norm.get(cn) or aa_base.get(cn)
        if aa_rec and aa_rec.get("contextWindowTokens"):
            m["context_length"] = aa_rec["contextWindowTokens"]
            return


def _lm_match_of(m: dict) -> str | None:
    return bc._as_dict(m.get("base_metrics")).get("lm_match")


def _drop_claimed_arena_rows(catalog: dict) -> None:
    claimed = {_lm_match_of(m) for m in catalog.values() if m.get("tier") != "Arena Model"}
    claimed.discard(None)
    for mid in [k for k, m in catalog.items() if m.get("tier") == "Arena Model" and _lm_match_of(m) in claimed]:
        catalog.pop(mid, None)
    for m in catalog.values():
        bc._as_dict(m.get("base_metrics")).pop("lm_match", None)


def _signal_signature(m: dict) -> tuple:
    bm = bc._as_dict(m.get("base_metrics"))
    return (
        _lb_overall(m),
        m.get("aa_live_quality"),
        bm.get("aa_tb4"),
        bm.get("aa_hle"),
        bm.get("aa_non_halluc"),
        bm.get("lm_elo"),
        bm.get("lm_coding"),
        m.get("vals_overall"),
        bm.get("fc2_score"),
        bm.get("fswe_overall"),
        bm.get("cursor_score"),
    )


def _dedupe_arena_and_mirrors(catalog):
    """Drop Arena auto-rows already claimed by curated rows, and tag exact multi-signal mirrors."""
    _drop_claimed_arena_rows(catalog)
    seen_signals: dict[tuple, str] = {}
    for mid, m in catalog.items():
        key = _signal_signature(m)
        if sum(1 for v in key if v is not None) < 2:
            continue
        if key in seen_signals:
            m["signal_mirror_of"] = seen_signals[key]
        else:
            seen_signals[key] = mid


def _top_effort_ranks(catalog: dict) -> dict[str, int]:
    ranks: dict[str, int] = {}
    for mid, m in catalog.items():
        fam = _canon_family_slug(mid)
        r = _EFFORT_RANK.get(m.get("effort") or "", -1)
        if r > ranks.get(fam, -2):
            ranks[fam] = r
    return ranks


def _build_signal_indices(sources: dict, catalog: dict) -> dict:
    live_map, lm_map, aa_map = sources["live"], sources["lm"], sources["aa"]
    fc2_map, fswe_map, cursor_map = sources["fc2"], sources["fswe"], sources["cursor"]
    return {
        "live_norm": {bc.norm_id(k): v for k, v in (live_map or {}).items()},
        "lm_norm": _norm_variants_index(lm_map),
        "aa_norm": _norm_variants_index(aa_map),
        "live_base": _best_base_index(live_map, "overall", strip_fn=livebench_base_name),
        "lm_base": _best_base_index(lm_map, "elo", strip_fn=strip_effort_suffix, include_arena=True),
        "aa_base": _best_base_index(aa_map, "intelligenceIndex", strip_fn=strip_effort_suffix),
        "lm_slug_of": {id(v): k for k, v in (lm_map or {}).items()},
        "lb_idx": _index_fam_effort(live_map, "Benchmark Model", "overall", base_fn=livebench_base_name),
        "lm_idx": _index_fam_effort(lm_map, "Arena Model", "elo"),
        "aa_idx": _index_fam_effort(aa_map, "Upstream API", "intelligenceIndex"),
        "fc2_idx": _index_fam_effort(fc2_map, "FrontierCode Model", "fc2_score"),
        "cur_idx": _index_fam_effort(cursor_map, "CursorBench Model", "cursor_score"),
        "fswe_by_fam": {_canon_family_slug(k): v for k, v in (fswe_map or {}).items()},
        "top_ranks": _top_effort_ranks(catalog),
    }


def _attach_all_signals(catalog, sources: dict, or_pricing: dict) -> None:
    ix = _build_signal_indices(sources, catalog)
    fc2_raw = sources["fc2"] or {}
    cur_raw = sources["cursor"] or {}
    vals_raw = sources["vals"] or {}
    for mid, m in catalog.items():
        fam = _canon_family_slug(mid)
        row_eff = m.get("effort")
        is_flagship = (row_eff is None) or (_EFFORT_RANK.get(row_eff, -1) == ix["top_ranks"].get(fam, -1))
        _attach_livebench_signal(mid, m, fam, row_eff, is_flagship, ix["lb_idx"], ix["live_norm"], ix["live_base"])
        _attach_lm_signal(mid, m, fam, row_eff, is_flagship, ix["lm_idx"], ix["lm_norm"], ix["lm_base"], ix["lm_slug_of"])
        _attach_aa_signal(mid, m, fam, row_eff, ix["aa_idx"], ix["aa_norm"], ix["aa_base"])
        _attach_fc2_signal(m, fam, row_eff, ix["fc2_idx"], fc2_raw)
        _attach_cursor_signal(m, fam, row_eff, ix["cur_idx"], cur_raw)
        _attach_fswe_signal(m, fam, is_flagship, ix["fswe_by_fam"])
        _attach_vals_signal(m, fam, is_flagship, vals_raw)
        _attach_context_length(mid, m, fam, or_pricing, ix["aa_norm"], ix["aa_base"])


def build_universal_catalog(
    base_catalog=None, live_map=None, lm_map=None, aa_map=None, vals_map=None,
    or_pricing=None, fc2_map=None, fswe_map=None, cursor_map=None,
):
    """Build universal catalog across all 7 upstream authorities with distinct thinking levels."""
    catalog = copy.deepcopy(MODELS_CATALOG if base_catalog is None else base_catalog)
    vals_map = load_vals_data(fetch=False) if vals_map is None else vals_map
    fc2_map = load_frontiercode_data(fetch=False) if fc2_map is None else fc2_map
    fswe_map = load_frontierswe_data(fetch=False) if fswe_map is None else fswe_map
    cursor_map = load_cursor_data(fetch=False) if cursor_map is None else cursor_map
    or_pricing = load_openrouter_pricing_data() if or_pricing is None else or_pricing
    aa_norm = _norm_variants_index(aa_map)

    up_effs = _collect_upstream_efforts(
        ("Upstream API", aa_map), ("FrontierCode Model", fc2_map), ("CursorBench Model", cursor_map),
    )
    fam_meta = _bind_catalog_efforts(catalog, up_effs)
    key_index: dict[str, str] = {}
    seen_families: set[str] = set()
    for cid, info in catalog.items():
        _register_entry_keys(key_index, seen_families, cid, info)

    for src_map, tier, sfn in (
        (aa_map, "Upstream API", strip_effort_suffix),
        (fc2_map, "FrontierCode Model", strip_effort_suffix),
        (cursor_map, "CursorBench Model", strip_effort_suffix),
        (fswe_map, "FrontierSWE Model", strip_effort_suffix),
        (live_map, "Benchmark Model", livebench_base_name),
        (lm_map, "Arena Model", strip_effort_suffix),
        (vals_map, "Vals Model", strip_effort_suffix),
    ):
        _ingest_source_models(catalog, key_index, seen_families, src_map, or_pricing, aa_norm, tier, fam_meta, strip_fn=sfn)

    sources = {
        "live": live_map, "lm": lm_map, "aa": aa_map, "vals": vals_map,
        "fc2": fc2_map, "fswe": fswe_map, "cursor": cursor_map,
    }
    _attach_all_signals(catalog, sources, or_pricing)
    _dedupe_arena_and_mirrors(catalog)
    return catalog


def fetch_url(url, timeout=15):
    """Fetch URL with browser user agent."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception:
        return None


def _utc_stamp() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y%m%d")


def _load_cached_livebench(out: dict) -> None:
    csv_matches = [
        p for p in sorted(glob.glob(str(RAW / "*livebench*20*.csv")))
        if "cost" not in pathlib.Path(p).name
    ]
    for p_csv in csv_matches[-1:]:
        p = pathlib.Path(p_csv)
        try:
            date_part = "".join(filter(str.isdigit, p.stem))
            cat_p = RAW / f"livebench_categories_{date_part}.json"
            cat_json = cat_p.read_text(encoding="utf-8", errors="ignore") if cat_p.exists() else None
            out.update(parse_livebench(p.read_text(encoding="utf-8", errors="ignore"), categories_json=cat_json))
        except Exception as e:
            print(f"  WARN LiveBench cache parse failed ({p.name}): {e}", file=sys.stderr)


def load_livebench_data(verbose=False, fetch=False):
    """Load LiveBench from the 24h response cache (docs/data/raw/), refreshing today's snapshot when fetch=True."""
    out = {}
    _load_cached_livebench(out)
    if not fetch:
        return out
    try:
        csv_text = fetch_url(LIVEBENCH_CSV_URL)
        cat_text = fetch_url(LIVEBENCH_CAT_URL)
        parsed = parse_livebench(csv_text, categories_json=cat_text, verbose=verbose) if csv_text else {}
        if len(parsed) >= 40:
            stamp = _utc_stamp()
            s_csv = RAW / f"livebench_{stamp}.csv"
            bc.atomic_write_text(s_csv, csv_text)
            print(f"  saved LiveBench -> {s_csv.relative_to(ROOT)} ({len(csv_text)} bytes)")
            if cat_text:
                s_cat = RAW / f"livebench_categories_{stamp}.json"
                bc.atomic_write_text(s_cat, cat_text)
            out.update(parsed)
    except Exception as e:  # noqa: BLE001 — never swallow silently (S2-C1)
        print(f"  WARN LiveBench fetch/save failed: {e}", file=sys.stderr)
    return out


def lmarena_publish_date():
    """Publish date of the newest Arena HF snapshot, or None."""
    for p in reversed(sorted(glob.glob(str(RAW / "*lmarena_hf*20*.json")))):
        try:
            payload = json.loads(pathlib.Path(p).read_text(encoding="utf-8"))
        except Exception:
            continue
        for row in (payload.get("rows") or []):
            d = row.get("leaderboard_publish_date")
            if d:
                return str(d)
    return None


def load_lmarena_data(verbose=False, fetch=False):
    """Load Arena leaderboard data; force-refresh today's HF snapshot when fetch=True."""
    out = bc.load_lmarena_map(RAW, verbose=verbose)
    if fetch:
        try:
            payload = bc.fetch_lmarena_hf_snapshot(RAW, verbose=verbose, force=True)
            if payload:
                out.update(parse_lmarena_hf(payload, verbose=verbose))
            else:
                print("  WARN LMArena HF fetch returned no usable rows", file=sys.stderr)
        except Exception as e:  # noqa: BLE001 — never swallow silently (S2-C1)
            print(f"  WARN LMArena HF fetch/save failed: {e}", file=sys.stderr)
    return out


def _load_or_fetch_html(pattern, url, prefix, label, parser, min_rows=20, verbose=False, fetch=False):
    out = {}
    for p_html in reversed(sorted(glob.glob(str(RAW / pattern)))):
        p = pathlib.Path(p_html)
        try:
            parsed = parser(p.read_text(encoding="utf-8", errors="ignore"), verbose=verbose)
            if len(parsed) >= min_rows:
                out.update(parsed)
                break
        except Exception as e:
            print(f"  WARN {label} cache parse failed ({p.name}): {e}", file=sys.stderr)
    if fetch:
        try:
            html_txt = fetch_url(url)
            parsed_live = parser(html_txt, verbose=verbose) if html_txt else {}
            if len(parsed_live) >= min_rows:
                s = RAW / f"{prefix}_{_utc_stamp()}.html"
                bc.atomic_write_text(s, html_txt)
                print(f"  saved {label} -> {s.relative_to(ROOT)} ({len(html_txt)} bytes)")
                out.update(parsed_live)
            else:
                print(f"  WARN {label} fetch returned {len(parsed_live)} rows (<{min_rows}); keeping cache", file=sys.stderr)
        except Exception as e:  # noqa: BLE001 — never swallow silently (S2-C1)
            print(f"  WARN {label} fetch/save failed: {e}", file=sys.stderr)
    return out


def load_aa_data(verbose=False, fetch=False):
    """Load Artificial Analysis v5.0.1 data from cache or live with fail-closed validation."""
    return _load_or_fetch_html(
        "*artificial_analysis*20*.html", AA_URL, "artificial_analysis", "Artificial Analysis", parse_aa, min_rows=100, verbose=verbose, fetch=fetch
    )


def load_vals_data(verbose=False, fetch=False):
    """Load Vals Index from cache or live with fail-closed validation."""
    return _load_or_fetch_html(
        "*vals_index*20*.html", VALS_INDEX_URL, "vals_index", "Vals Index", parse_vals_index, min_rows=40, verbose=verbose, fetch=fetch
    )


def load_frontiercode_data(verbose=False, fetch=False):
    """Load Cognition FrontierCode 2.0 from cache or live."""
    return load_or_fetch_frontiercode(RAW, fetch=fetch, write=True, verbose=verbose)


def load_frontierswe_data(verbose=False, fetch=False):
    """Load FrontierSWE from cache or live."""
    return load_or_fetch_frontierswe(RAW, fetch=fetch, write=True, verbose=verbose)


def load_cursor_data(verbose=False, fetch=False):
    """Load CursorBench 4.0 from cache or live."""
    return load_or_fetch_cursor_evals(RAW, fetch=fetch, write=True, verbose=verbose)


def newest_snapshot_age_h(pattern):
    """Hours since the newest docs/data/raw/ snapshot matching `pattern`; None when none exists."""
    matches = glob.glob(str(RAW / pattern))
    return min(bc.snapshot_age_hours(p) for p in matches) if matches else None


def livebench_table_age_days(now: dt.datetime | None = None) -> int:
    """Age of the pinned LiveBench release (LIVEBENCH_TABLE_DATE) in days."""
    now = now or dt.datetime.now(dt.UTC)
    released = dt.datetime.strptime(LIVEBENCH_TABLE_DATE, "%Y-%m-%d").replace(tzinfo=dt.UTC)
    return max(0, (now - released).days)


def _lmarena_staleness_part() -> str | None:
    age = newest_snapshot_age_h("*lmarena_hf*20*.json") or newest_snapshot_age_h("*lmarena*20*.html")
    if age is None:
        return "LMArena missing"
    return f"LMArena {age:.0f}h old" if age > CACHE_TTL_H else None


_STALENESS_FEEDS: tuple[tuple[str, str], ...] = (
    ("Artificial Analysis", "*artificial_analysis*20*.html"),
    ("Vals Index", "*vals_index*20*.html"),
    ("FrontierCode", "*frontiercode*20*.json"),
    ("FrontierSWE", "*frontierswe*20*.html"),
    ("CursorBench", "*cursor_evals*20*.json"),
    ("LiveBench", "*livebench*20*.csv"),
)


def cache_staleness_note():
    """Staleness warning for offline runs across all 7 cached upstream feeds."""
    parts = []
    for name, pat in _STALENESS_FEEDS:
        age = newest_snapshot_age_h(pat)
        if age is None:
            parts.append(f"{name} missing")
        elif age > CACHE_TTL_H:
            parts.append(f"{name} {age:.0f}h old")
    lm_part = _lmarena_staleness_part()
    if lm_part:
        parts.append(lm_part)
    return ("cached responses >24h — run with --fetch: " + ", ".join(parts)) if parts else ""


def _int_str(v) -> str:
    """NaN/Inf-safe int display; never throws (None-safe)."""
    i = bc._safe_int(v)
    return f"{i}" if i is not None else "—"


def _lb_overall(m: dict) -> float | None:
    """Extract numeric LiveBench overall score whether dict or scalar."""
    lb = m.get("livebench")
    val = lb.get("overall") if isinstance(lb, dict) else lb
    return float(val) if bc._is_num(val) else None


def _role_val(m: dict, key: str) -> float | None:
    return bc._safe_float(bc._as_dict(m.get("roles")).get(key))


def calculate_composite_scores(models_dict):
    """Score all rows across the 5 shrunk capability/economics axes and 4 task roles."""
    score_five_axes_and_roles(list(models_dict.values()))


def _fmt_one_price(v) -> str:
    if v is None:
        return "—"
    if v == 0:
        return "$0"
    if v >= 1.0:
        if v.is_integer():
            return f"${v:.0f}"
        return f"${v:.1f}" if round(v * 10, 2).is_integer() else f"${v:.2f}"
    return f"${v:.2f}"


def format_compact_price(p_in, p_out):
    """Format prompt and completion price compactly e.g. $5/$25 or $0.41/$0.83."""
    return f"{_fmt_one_price(p_in)}/{_fmt_one_price(p_out)}"


BCHECK_COL_MEDAL_KEYS = {
    "q": (lambda m: m.get("capability_q") or 0.0, True, lambda m: bc._is_num(m.get("capability_q"))),
    "arch": (lambda m: _role_val(m, "architecture") or 0.0, True, lambda m: _role_val(m, "architecture") is not None),
    "dev": (lambda m: _role_val(m, "software_dev") or 0.0, True, lambda m: _role_val(m, "software_dev") is not None),
    "design": (lambda m: _role_val(m, "design") or 0.0, True, lambda m: _role_val(m, "design") is not None),
    "research": (lambda m: _role_val(m, "research") or 0.0, True, lambda m: _role_val(m, "research") is not None),
    "eff_cost": (lambda m: m.get("effective_cost") if bc._is_num(m.get("effective_cost")) else 999.0, False, lambda m: bc._is_num(m.get("effective_cost"))),
    "cursor": (lambda m: bc._as_dict(m.get("base_metrics")).get("cursor_score") or 0.0, True, lambda m: bc._is_num(bc._as_dict(m.get("base_metrics")).get("cursor_score"))),
    "fc2": (lambda m: bc._as_dict(m.get("base_metrics")).get("fc2_score") or 0.0, True, lambda m: bc._is_num(bc._as_dict(m.get("base_metrics")).get("fc2_score"))),
    "speed": (lambda m: bc._safe_float(bc._as_dict(m.get("base_metrics")).get("speed_tps"), 0) or 0, True, lambda m: bc._is_num(bc._as_dict(m.get("base_metrics")).get("speed_tps"))),
    "price": (lambda m: m.get("blended_price") if bc._is_num(m.get("blended_price")) else 999.0, False, lambda m: bc._is_num(m.get("blended_price"))),
}


COVERAGE_SOURCES = ("arena", "aa", "vals", "live", "fc2", "fswe", "cursor")


def signal_coverage(m: dict, live_aa_only: bool = False) -> dict[str, bool]:
    """Which of the seven upstream authorities evaluated this model."""
    bm = bc._as_dict(m.get("base_metrics"))
    aa_live = bc._is_num(m.get("aa_live_quality")) or bc._is_num(bm.get("aa_hle")) or bc._is_num(bm.get("aa_tb4"))
    aa_static = bc._is_num(bm.get("aa_quality"))
    return {
        "arena": bc._is_num(bm.get("lm_elo")),
        "aa": aa_live if live_aa_only else (aa_live or aa_static),
        "vals": bc._is_num(m.get("vals_overall")),
        "live": bc._is_num(_lb_overall(m)),
        "fc2": bc._is_num(bm.get("fc2_score")),
        "fswe": bc._is_num(bm.get("fswe_overall")),
        "cursor": bc._is_num(bm.get("cursor_score")),
    }


def coverage_label(n: int) -> str:
    """Confidence badge `[7/7]`…`[1/7]*`; the star marks single-source evidence."""
    return f"[{n}/{len(COVERAGE_SOURCES)}]*" if n == 1 else f"[{n}/{len(COVERAGE_SOURCES)}]"


def partition_models_by_benchmark_coverage(models_list):
    """Group rows by how many of the seven upstream authorities evaluated them."""
    has_live_aa = any(bc._is_num(m.get("aa_live_quality")) for m in models_list)
    buckets = {n: [] for n in range(len(COVERAGE_SOURCES) + 1)}
    for m in models_list:
        n = sum(signal_coverage(m, live_aa_only=has_live_aa).values())
        buckets[n].append(m)
    return {
        "high_conf": [m for n in (7, 6, 5, 4) for m in buckets[n]],
        "mid_conf": [m for n in (3, 2) for m in buckets[n]],
        "one": buckets[1],
        "unmatched": buckets[0],
        "counts": {n: len(buckets[n]) for n in range(7, 0, -1) if buckets[n]},
    }


def _merge_unmatched_models(unmatched_models, partition_unmatched):
    """Deduplicate unmatched models across catalog unmatched and partition unmatched while preserving order."""
    seen = set()
    merged = []
    for m in list(unmatched_models or []) + list(partition_unmatched or []):
        key = m.get("display") or m.get("model_id") or id(m)
        if key not in seen:
            seen.add(key)
            merged.append(m)
    return merged


_POOL_HTML_CLS = {
    "claude": "badge-cld",
    "agy": "badge-agy",
    "ocgo": "badge-ocg",
    "frontier": "badge-frt",
    "hetzner": "badge-htz",
    "nvidia": "badge-nvd",
}

_SUB_TABLE_SPECS = (
    ("one", "🚀 SUB-TABLE: TOP 10 — SINGLE-SOURCE / EMERGING MODELS ([1/7]* Authority Only)", "2.1 Top 10 — Single-Source / Emerging Models ([1/7]* Authority Only)"),
)

_PODIUM_SPECS = (
    ("Q(Cap) — Capability", "Q(Cap) — Composite Capability", lambda m: m.get("capability_q") or 0.0, True, lambda m: bc._is_num(m.get("capability_q")), lambda m: f"{m['capability_q']:.1f}"),
    ("🏗️ Architecture — Spec", "🏗️ Architecture — Spec & Debug", lambda m: _role_val(m, "architecture") or 0.0, True, lambda m: _role_val(m, "architecture") is not None, lambda m: f"{_role_val(m, 'architecture'):.1f}"),
    ("💻 Software Dev — ROI", "💻 Software Dev — Agentic ROI", lambda m: _role_val(m, "software_dev") or 0.0, True, lambda m: _role_val(m, "software_dev") is not None, lambda m: f"{_role_val(m, 'software_dev'):.1f}"),
    ("🎨 Design — UI Craft", "🎨 Design — UI / Webdev Craft", lambda m: _role_val(m, "design") or 0.0, True, lambda m: _role_val(m, "design") is not None, lambda m: f"{_role_val(m, 'design'):.1f}"),
    ("🔬 Research — Synthesis", "🔬 Research — Grounded Synthesis", lambda m: _role_val(m, "research") or 0.0, True, lambda m: _role_val(m, "research") is not None, lambda m: f"{_role_val(m, 'research'):.1f}"),
    ("CursorBench 4.0 — %", "CursorBench 4.0 — Agentic Coding %", lambda m: bc._as_dict(m.get("base_metrics")).get("cursor_score") or 0.0, True, lambda m: bc._is_num(bc._as_dict(m.get("base_metrics")).get("cursor_score")), lambda m: f"{bc._as_dict(m.get('base_metrics'))['cursor_score']:.1f}%"),
    ("FrontierCode 2.0 — %", "Cognition FrontierCode 2.0 — %", lambda m: bc._as_dict(m.get("base_metrics")).get("fc2_score") or 0.0, True, lambda m: bc._is_num(bc._as_dict(m.get("base_metrics")).get("fc2_score")), lambda m: f"{bc._as_dict(m.get('base_metrics'))['fc2_score']:.1f}%"),
    ("FrontierSWE — Overall %", "FrontierSWE — Software & Research %", lambda m: bc._as_dict(m.get("base_metrics")).get("fswe_overall") or 0.0, True, lambda m: bc._is_num(bc._as_dict(m.get("base_metrics")).get("fswe_overall")), lambda m: f"{bc._as_dict(m.get('base_metrics'))['fswe_overall']:.1f}%"),
    ("Non-Halluc. — Omnisc.", "Omniscience Non-Hallucination %", lambda m: bc._as_dict(m.get("base_metrics")).get("aa_non_halluc") or 0.0, True, lambda m: bc._is_num(bc._as_dict(m.get("base_metrics")).get("aa_non_halluc")), lambda m: f"{bc._as_dict(m.get('base_metrics'))['aa_non_halluc']:.1f}%"),
    ("Speed — Throughput", "Speed — Generation Throughput", lambda m: bc._safe_float(bc._as_dict(m.get("base_metrics")).get("speed_tps"), 0) or 0, True, lambda m: bc._is_num(bc._as_dict(m.get("base_metrics")).get("speed_tps")), lambda m: f"{_int_str(bc._as_dict(m.get('base_metrics')).get('speed_tps'))} t/s"),
    ("$/Task — Empirical Cost", "$/Task — Empirical Task Cost", lambda m: m.get("effective_cost") if bc._is_num(m.get("effective_cost")) else 999.0, False, lambda m: bc._is_num(m.get("effective_cost")), lambda m: f"${m['effective_cost']:.2f}"),
)


def _rank_label(rank_num: int) -> str:
    return {1: "🥇#1", 2: "🥈#2", 3: "🥉#3"}.get(rank_num, f" #{rank_num}")


def _rank_color(rank_num: int) -> str:
    return C_BOLD + {1: C_GOLD, 2: C_SILVER, 3: C_BRONZE}.get(rank_num, C_WHITE)


def _model_flags(m: dict, added_ids: set, pareto_ids: set) -> tuple[bool, bool]:
    alias0 = (m.get("aa_aliases") or m.get("lm_aliases") or m.get("live_aliases") or [None])[0]
    keys = {m.get("display"), alias0, m.get("model_id"), m.get("or_slug"), m.get("aa_slug"), m.get("lm_slug")} - {None}
    is_added = bool(keys & added_ids) if added_ids else False
    is_pareto = bool(keys & pareto_ids) if pareto_ids else False
    return is_added, is_pareto


def _cap_list_str(items: list[str], limit: int = 8) -> str:
    extra = f" (+{len(items) - limit} more)" if len(items) > limit else ""
    return ", ".join(items[:limit]) + extra


def _diff_banner_notices(added_ids, removed_models, stale_note):
    notices, parts = [], []
    if added_ids:
        joined = _cap_list_str(sorted(added_ids))
        notices.append(f"{C_BOLD}{C_GREEN}✨ New (+{len(added_ids)}): {joined}{C_RESET}")
        parts.append(f"[+NEW (+{len(added_ids)}): {joined}]")
    if removed_models:
        rem_names = [m.get("display") or m.get("model_id", "unknown") for m in removed_models]
        joined = _cap_list_str(rem_names)
        notices.append(f"{C_BOLD}{C_RED}🔻 Removed (-{len(removed_models)}): {joined}{C_RESET}")
        parts.append(f"[-REMOVED (-{len(removed_models)}): {joined}]")
    if stale_note:
        notices.append(f"{C_BOLD}{C_YELLOW}⚠ {stale_note}{C_RESET}")
        parts.append(f"[!] {stale_note}")
    return notices, parts


def _cli_table_frame(headers, color: bool, skip_top: bool = False):
    inner_w = sum(w + 2 for _, w, _ in headers) + len(headers) - 1
    if not color:
        hdr_str = " ".join(pad_display(h, w, a) for h, w, a in headers)
        return ["-" * (inner_w + 2), hdr_str, "-" * (inner_w + 2)], "-" * (inner_w + 2)
    top_border = "┌" + "┬".join("─" * (w + 2) for _, w, _ in headers) + "┐"
    mid_border = "├" + "┼".join("─" * (w + 2) for _, w, _ in headers) + "┤"
    bot_border = "└" + "┴".join("─" * (w + 2) for _, w, _ in headers) + "┘"
    hdr_cells = [color_cell(h, C_BOLD + C_WHITE, width=w, align=a, bg=BG_HEADER) for h, w, a in headers]
    hdr_row = f"{BG_HEADER}{C_DIM}│{C_RESET}" + f"{BG_HEADER}{C_DIM}│{C_RESET}".join(hdr_cells) + f"{BG_HEADER}{C_DIM}│{C_RESET}"
    head = ([] if skip_top else [f"{C_DIM}{top_border}{C_RESET}"]) + [hdr_row, f"{C_DIM}{mid_border}{C_RESET}"]
    return head, f"{C_DIM}{bot_border}{C_RESET}"


def _format_cli_row(cells_specs, bg: str, color: bool) -> str:
    if color:
        cells = [color_cell(txt, clr, width=w, align=a, bg=bg) for txt, clr, w, a in cells_specs]
        return f"{bg}{C_DIM}│{C_RESET}" + f"{bg}{C_DIM}│{C_RESET}".join(cells) + f"{bg}{C_DIM}│{C_RESET}"
    return " ".join(pad_display(txt, w, a) for txt, _, w, a in cells_specs)


def render_unmatched_models_cli(unmatched_models, color=True):
    """Render prominent warning for catalog models with zero upstream benchmark signals."""
    if not unmatched_models:
        return ""
    w_total = 95
    header_text = "⚠️ UNMATCHED CATALOG MODELS (0 upstream benchmark evaluations found)"
    sub_text = "See Something, Say Something: these catalog models have no verified evaluations on Arena.ai, Artificial Analysis, or Vals Index:"
    if not color:
        lines = ["\n" + "=" * (w_total + 2), f" {header_text}", f" {sub_text}", "-" * (w_total + 2)]
        for i, m in enumerate(unmatched_models, 1):
            la = ", ".join(m.get("live_aliases", [])[:2]) or "—"
            lma = ", ".join(m.get("lm_aliases", [])[:2]) or "—"
            p = pool_badge(m.get("pool", "api"), color=False)
            lines.append(f" #{i:<2} {m.get('display', 'Unknown')[:24]:<24} {p:^5} | Live ({la}) · Arena ({lma}) -> 0 matches")
        lines.append("-" * (w_total + 2))
        return "\n".join(lines)

    title_pad = f" {header_text}" + (" " * max(0, w_total - display_len(header_text) - 1))
    sub_pad = f" {sub_text}" + (" " * max(0, w_total - display_len(sub_text) - 1))
    lines = [
        f"\n{C_BOLD}{C_YELLOW}╭" + ("─" * w_total) + f"╮{C_RESET}",
        f"{C_BOLD}{C_YELLOW}│{C_RESET}{C_BOLD}{C_WHITE}{title_pad}{C_RESET}{C_BOLD}{C_YELLOW}│{C_RESET}",
        f"{C_BOLD}{C_YELLOW}│{C_RESET}{C_DIM}{sub_pad}{C_RESET}{C_BOLD}{C_YELLOW}│{C_RESET}",
        f"{C_BOLD}{C_YELLOW}├────┬──────────────────────────┬───────┬────────────────────────────────────────────────────┤{C_RESET}",
    ]
    for i, m in enumerate(unmatched_models, 1):
        la = ", ".join(m.get("live_aliases", [])[:2]) or "—"
        lma = ", ".join(m.get("lm_aliases", [])[:2]) or "—"
        info = f"Live ({la}) · Arena ({lma}) -> 0 matches"[:50]
        row_cells = [
            color_cell(f"#{i}", C_GRAY, width=4, align="^", bg=BG_HEADER),
            color_cell(m.get("display", "Unknown")[:24], C_YELLOW, width=24, align="<", bg=BG_HEADER),
            color_cell(pool_badge(m.get("pool", "api"), color=False), "", width=5, align="^", bg=BG_HEADER),
            color_cell(info, C_DIM, width=50, align="<", bg=BG_HEADER),
        ]
        lines.append(f"{C_BOLD}{C_YELLOW}│{C_RESET}" + f"{C_BOLD}{C_YELLOW}│{C_RESET}".join(row_cells) + f"{C_BOLD}{C_YELLOW}│{C_RESET}")
    lines.append(f"{C_BOLD}{C_YELLOW}╰────┴──────────────────────────┴───────┴────────────────────────────────────────────────────╯{C_RESET}")
    return "\n".join(lines)


def render_unmatched_models_md(unmatched_models):
    """Render Markdown alert for catalog models missing all upstream benchmark signals."""
    if not unmatched_models:
        return ""
    lines = [
        "",
        "### ⚠️ Unmatched Catalog Models (0 Upstream Benchmark Evaluations)",
        "> **See Something, Say Something**: The following models configured in the catalog did not match any verified evaluation on Arena.ai, Artificial Analysis, or Vals Index (or LiveBench):",
        "",
        "| Model | Pool | Checked LiveBench Aliases | Checked LMArena Aliases |",
        "| :--- | :---: | :--- | :--- |",
    ]
    for m in unmatched_models:
        la = ", ".join(m.get("live_aliases", [])) or "—"
        lma = ", ".join(m.get("lm_aliases", [])) or "—"
        lines.append(f"| {m.get('display', 'Unknown')} | `[{m.get('pool', 'api').upper()}]` | `{la}` | `{lma}` |")
    lines.append("")
    return "\n".join(lines)


def render_unmatched_models_html(unmatched_models):
    """Render HTML alert for catalog models missing all upstream benchmark signals."""
    if not unmatched_models:
        return ""
    trs = []
    for m in unmatched_models:
        disp = html.escape(m.get("display", "Unknown"))
        p = html.escape(m.get("pool", "api").upper())
        la = html.escape(", ".join(m.get("live_aliases", [])) or "—")
        lma = html.escape(", ".join(m.get("lm_aliases", [])) or "—")
        trs.append(f'<tr><td style="font-weight:600;">{disp}</td><td><code>[{p}]</code></td><td><code>{la}</code></td><td><code>{lma}</code></td></tr>')
    return f"""
    <div style="background: #2a1515; border: 1px solid #ef4444; border-radius: 8px; padding: 16px; margin-top: 24px;">
        <h3 style="color: #ef4444; margin-top: 0;">⚠️ Unmatched Catalog Models (0 Upstream Benchmark Evaluations)</h3>
        <p style="color: #cbd5e1; font-size: 0.9em;"><strong>See Something, Say Something</strong>: The following models configured in the catalog did not match any verified evaluation on Arena.ai, Artificial Analysis, or Vals Index (or LiveBench):</p>
        <table style="width: 100%; border-collapse: collapse; margin-top: 8px;">
            <thead>
                <tr style="text-align: left; color: #94a3b8; border-bottom: 1px solid #475569;">
                    <th>Model</th><th>Pool</th><th>LiveBench Aliases</th><th>LMArena Aliases</th>
                </tr>
            </thead>
            <tbody>{"".join(trs)}</tbody>
        </table>
    </div>
    """


def _sub_metrics(m: dict) -> dict:
    bm = bc._as_dict(m.get("base_metrics"))
    q = m.get("capability_q")
    c = m.get("effective_cost")
    cur = bm.get("cursor_score")
    fc2 = bm.get("fc2_score")
    elo = bm.get("lm_elo")
    aa = m.get("aa_live_quality")
    return {
        "q": q,
        "c": c,
        "q_str": f"{q:.1f}" if bc._is_num(q) else "—",
        "c_str": f"${c:.2f}" if bc._is_num(c) else "—",
        "cur": cur,
        "cur_str": f"{cur:.1f}%" if bc._is_num(cur) else "—",
        "fc2": fc2,
        "fc2_str": f"{fc2:.1f}%" if bc._is_num(fc2) else "—",
        "elo": elo,
        "elo_str": _int_str(elo),
        "aa": aa,
        "aa_str": f"{aa:.1f}" if bc._is_num(aa) else "—",
        "role": m.get("best_role") or "—",
    }


def _fmt_num(val, fmt: str = "{:.1f}", badge_rank: int | None = None, color: bool = True) -> str:
    txt = fmt.format(val) if bc._is_num(val) else "—"
    return txt + medal_badge(badge_rank, color=color) if badge_rank else txt


def _thresh_color(val, cutoff: float, hi: str = C_GREEN, lo: str = C_GRAY) -> str:
    return hi if bc._is_num(val) and val >= cutoff else lo


def _eff_cost_color(eff_cost) -> str:
    if eff_cost is None:
        return C_YELLOW
    if eff_cost < 3.0:
        return C_GREEN
    return C_CYAN if eff_cost < 12.0 else C_YELLOW


def _conf_color_cli(cov_n: int) -> str:
    if cov_n >= 5:
        return C_GREEN
    if cov_n >= 3:
        return C_CYAN
    return C_YELLOW if cov_n == 2 else C_GRAY


def _resolve_cli_layout(color: bool | None, slim: bool | None, wide: bool) -> tuple[bool, bool]:
    use_color = (not os.getenv("NO_COLOR")) if color is None else color
    term_cols = shutil.get_terminal_size((120, 24)).columns
    is_slim = (term_cols < 120 and not wide) if slim is None else slim
    return use_color, is_slim


def _clip_models(models_list: list, top_n: int | None) -> list:
    return models_list[:top_n] if (top_n and len(models_list) > top_n) else models_list


def _top_summary(models_list: list, val_fn, label: str, fmt: str) -> str:
    if not models_list:
        return ""
    best = max(models_list, key=lambda m: val_fn(m) or 0.0)
    val = val_fn(best)
    if not bc._is_num(val):
        return ""
    name = (best.get("display") or best.get("model_id") or "")[:18]
    return f"{label}: {name} (" + fmt.format(val) + ")"


def _sub_table_frame(sub_headers: list, title: str, color: bool) -> tuple[list[str], str]:
    w_total = sum(w + 2 for _, w, _ in sub_headers) + len(sub_headers) - 1
    if color:
        mid_border = "├" + "┼".join("─" * (w + 2) for _, w, _ in sub_headers) + "┤"
        title_padded = f" {title}" + (" " * max(0, w_total - display_len(title) - 1))
        head, bot = _cli_table_frame(sub_headers, True, skip_top=True)
        return [
            f"\n{C_BOLD}{C_CYAN}┌" + ("─" * w_total) + f"┐{C_RESET}",
            f"{C_BOLD}{C_CYAN}│{C_RESET}{C_BOLD}{C_WHITE}{title_padded}{C_RESET}{C_BOLD}{C_CYAN}│{C_RESET}",
            f"{C_BOLD}{C_CYAN}{mid_border}{C_RESET}",
            *head,
        ], bot
    hdr_str = " ".join(pad_display(h, w, a) for h, w, a in sub_headers)
    plain_w = len(hdr_str)
    return ["\n" + "=" * plain_w, f" {title}", "=" * plain_w, hdr_str, "-" * plain_w], "-" * plain_w


def render_sub_table_cli(sub_models, title, color=True, top_n=10):
    """Render compact sub-table for single-source / emerging models."""
    if not sub_models:
        return ""
    sub_headers = [
        ("Rank", 4, "^"), ("Model", 24, "<"), ("Pool", 5, "^"), ("Best Role", 13, "<"),
        ("Q(Cap)", 6, ">"), ("$/Task", 7, ">"), ("Cur%", 6, ">"), ("FC2%", 6, ">"), ("Arena", 5, ">"), ("AA", 5, ">"),
    ]
    out, bot = _sub_table_frame(sub_headers, title, color)
    for i, m in enumerate(sub_models[:top_n], 1):
        bg = BG_ODD if (i % 2 == 1) else BG_EVEN
        sm = _sub_metrics(m)
        cells = [
            (f"#{i}", _rank_color(i), 4, "^"),
            (m["display"][:24], C_WHITE, 24, "<"),
            (pool_badge(m["pool"], color=False), "", 5, "^"),
            (sm["role"][:13], C_CYAN, 13, "<"),
            (sm["q_str"], score_color_q(sm["q"] or 0.0), 6, ">"),
            (sm["c_str"], _eff_cost_color(sm["c"]), 7, ">"),
            (sm["cur_str"], _thresh_color(sm["cur"], 50), 6, ">"),
            (sm["fc2_str"], _thresh_color(sm["fc2"], 40), 6, ">"),
            (sm["elo_str"], _thresh_color(sm["elo"], 1480), 5, ">"),
            (sm["aa_str"], _thresh_color(sm["aa"], 50), 5, ">"),
        ]
        out.append(_format_cli_row(cells, bg, color))
    out.append(f"{C_BOLD}{C_CYAN}{bot}{C_RESET}" if color else bot)
    return "\n".join(out)


def _main_cli_row(idx: int, m: dict, m_name_w: int, col_medals: dict, added_ids: set, pareto_ids: set, is_slim: bool, color: bool) -> str:
    rank_num = idx + 1
    bg = BG_ODD if (idx % 2 == 1) else BG_EVEN
    mid_raw = m["display"]
    is_added, is_pareto = _model_flags(m, added_ids, pareto_ids)
    mid_color = (C_BOLD + C_GREEN) if is_added else ((C_BOLD + C_GOLD) if is_pareto else C_WHITE)
    bm = bc._as_dict(m.get("base_metrics"))
    meds = col_medals.get(mid_raw, {})

    q_val, eff_cost = m.get("capability_q"), m.get("effective_cost")
    r_arc, r_dev = _role_val(m, "architecture"), _role_val(m, "software_dev")
    r_des, r_res = _role_val(m, "design"), _role_val(m, "research")
    cov_n = sum(signal_coverage(m).values())

    cells = [
        (_rank_label(rank_num), _rank_color(rank_num), 4, "^"),
        ((("+" if is_added else "") + mid_raw)[:m_name_w], mid_color, m_name_w, "<"),
        (coverage_label(cov_n), _conf_color_cli(cov_n), 6, "^"),
        (pool_badge(m["pool"], color=color), "", 5, "^"),
        (_fmt_num(q_val, "{:.1f}", meds.get("q"), color), score_color_q(q_val or 0.0), 6, ">"),
        (_fmt_num(r_arc, "{:.1f}", meds.get("arch"), color), score_color_q(r_arc or 0.0), 6, ">"),
        (_fmt_num(r_dev, "{:.1f}", meds.get("dev"), color), score_color_avi(r_dev or 0.0), 6, ">"),
        (_fmt_num(r_des, "{:.1f}", meds.get("design"), color), _thresh_color(r_des, 82.0, C_CYAN, C_WHITE), 6, ">"),
        (_fmt_num(r_res, "{:.1f}", meds.get("research"), color), _thresh_color(r_res, 82.0, C_GREEN, C_WHITE), 6, ">"),
        (_fmt_num(eff_cost, "${:.2f}", meds.get("eff_cost"), color), _eff_cost_color(eff_cost), 8, ">"),
    ]
    if not is_slim:
        price_disp = format_compact_price(m.get("price_in"), m.get("price_out")) + medal_badge(meds.get("price"), color=color)
        cells.extend([
            (_fmt_num(bm.get("cursor_score"), "{:.1f}%", meds.get("cursor"), color), _thresh_color(bm.get("cursor_score"), 55.0), 6, ">"),
            (_fmt_num(bm.get("fc2_score"), "{:.1f}%", meds.get("fc2"), color), _thresh_color(bm.get("fc2_score"), 42.0), 6, ">"),
            (_fmt_num(bm.get("speed_tps"), "{:.0f}t/s", meds.get("speed"), color), _thresh_color(bm.get("speed_tps"), 100, C_GREEN, C_WHITE), 6, ">"),
            (price_disp, C_DIM, 11, ">"),
        ])
    return _format_cli_row(cells, bg, color)


def _cli_ctx(models_list, color, slim, wide, pareto_ids, added_ids, removed_models, top_n):
    use_color, is_slim = _resolve_cli_layout(color, slim, wide)
    p_ids = compute_priced_pareto_frontier(models_list) if pareto_ids is None else pareto_ids
    return use_color, is_slim, p_ids, added_ids or set(), removed_models or [], _clip_models(models_list, top_n)


def _append_cli_footer(out: list[str], guide_title: str, guide_items: list, medal_pool: list, unmatched_list: list | None, color: bool, is_slim: bool, inner_w: int) -> None:
    if unmatched_list:
        unm = render_unmatched_models_cli(unmatched_list, color=color)
        if unm:
            out.append(unm)
    out.append("")
    out.extend(render_metric_guide_cli(guide_title, guide_items, color=color))
    role_recs = compute_role_recommendations(medal_pool, context="bcheck")
    if role_recs:
        out.extend(["", *render_role_recommendations_cli(role_recs, color=color, is_slim=is_slim, width=inner_w)])


def _cli_main_summary(models_list: list, display_models: list, partitions: dict, is_slim: bool) -> tuple[str, str]:
    a_info = _top_summary(models_list, lambda m: _role_val(m, "architecture"), "Arch", "{:.1f}")
    d_info = _top_summary(models_list, lambda m: _role_val(m, "software_dev"), "Dev", "{:.1f}")
    r_info = "" if is_slim else _top_summary(models_list, lambda m: _role_val(m, "research"), "Rsch", "{:.1f}")
    shown_note = f" (Top {len(display_models)} shown)" if len(display_models) < len(models_list) else ""
    conf_str = f"4+/7: {len(partitions['high_conf'])} · 2-3/7: {len(partitions['mid_conf'])} · 1/7: {len(partitions['one'])}"
    count_label = f"Ranked: {len(models_list)} models{shown_note} │ Conf {conf_str}"
    return count_label, " " + " │ ".join(p for p in (count_label, a_info, d_info, r_info) if p)


_MAIN_GUIDE_ITEMS = [
    ("Gold Bold", "Pareto Frontier (undefeated capability vs empirical $/task curve).", C_GOLD),
    ("Green (+)", "Newly added model/thinking variant vs previous baseline snapshot.", C_GREEN),
    ("Conf [k/7]", "Authorities: AA · Vals · Arena · LiveBench · FrontierCode · FrontierSWE · CursorBench.", C_GREEN),
    ("Q(Cap)", "Shrunk 5-axis composite (Reasoning 30 · Coding 30 · Research 20 · Design 20; λ=0.20).", C_GREEN),
    ("Arch / Dev", "Architecture (spec/debug) & Software Dev (coding + $/task + speed ROI) role scores.", C_CYAN),
    ("Dsgn / Rsch", "Design (webdev/UI/IFBench) & Research (non-hallucination/LCR/FSWE/GPQA, >=200k ctx).", C_GREEN),
    ("$/Task", "Empirical geometric-mean $/task across Cursor, FrontierCode, AA & Vals (blended $/M fallback).", C_YELLOW),
]


def render_cli_table(models_list, color=None, slim=None, wide=False, pareto_ids=None, added_ids=None, removed_models=None, stale_note=None, top_n: int | None = 30, unmatched_models=None):
    """Render the 7-authority, 4-role Q-ranked leaderboard with distinct thinking levels."""
    color, is_slim, pareto_ids, added_ids, removed_models, display_models = _cli_ctx(
        models_list, color, slim, wide, pareto_ids, added_ids, removed_models, top_n
    )
    partitions = partition_models_by_benchmark_coverage(models_list)
    medal_pool = [m for m in models_list if not m.get("signal_mirror_of")]
    col_medals = compute_column_medals(medal_pool, BCHECK_COL_MEDAL_KEYS, id_key="display")
    headers = [
        ("Rank", 4, "^"), ("Model", 24, "<"), ("Conf", 6, "^"), ("Pool", 5, "^"),
        ("Q(Cap)", 6, ">"), ("Arch", 6, ">"), ("Dev", 6, ">"), ("Dsgn", 6, ">"), ("Rsch", 6, ">"), ("$/Task", 8, ">"),
    ]
    if not is_slim:
        headers.extend([("Cur%", 6, ">"), ("FC2%", 6, ">"), ("Speed", 6, ">"), ("Price", 11, ">")])

    inner_w = sum(w + 2 for _, w, _ in headers) + len(headers) - 1
    count_label, summary_str = _cli_main_summary(models_list, display_models, partitions, is_slim)
    notices, parts = _diff_banner_notices(added_ids, removed_models, stale_note)
    out = render_banner_box(
        "⚡ 7-AUTHORITY AGENTIC & RESEARCH RADAR (AA · Vals · Arena · LB · FrontierCode · FrontierSWE · Cursor)",
        summary_lines=[summary_str],
        diff_notices=notices,
        inner_w=inner_w,
        color=color,
        plain_title_line=f" 7-AUTHORITY BENCHMARK & ROLE RADAR — {count_label}",
        plain_diff_parts=parts,
    )
    head, bot = _cli_table_frame(headers, color)
    out.extend(head)
    out.extend(_main_cli_row(idx, m, headers[1][1], col_medals, added_ids, pareto_ids, is_slim, color) for idx, m in enumerate(display_models))
    out.append(bot)

    if removed_models:
        out.extend(["", *render_removed_models_cli(removed_models, color=color, is_slim=is_slim, id_key="display")])
    out.extend(t for k, cli_t, _ in _SUB_TABLE_SPECS if (t := render_sub_table_cli(partitions[k], cli_t, color=color, top_n=10)))
    all_unmatched = _merge_unmatched_models(unmatched_models, partitions.get("unmatched", []))
    _append_cli_footer(out, "Metric & Role Decision Guide", _MAIN_GUIDE_ITEMS, medal_pool, all_unmatched, color, is_slim, inner_w)
    return "\n".join(out)


def _oneshot_headers(is_slim: bool, wide: bool):
    if is_slim:
        return [("Rank", 4, "^"), ("Model", 22, "<"), ("Pool", 5, "^"), ("Conf", 6, "^"), ("Q(Cap)", 6, ">"), ("Reason", 6, ">"), ("Coding", 6, ">"), ("Rsch", 6, ">"), ("Ctx", 5, ">")]
    if wide:
        return [("Rank", 4, "^"), ("Model", 24, "<"), ("Pool", 5, "^"), ("Conf", 6, "^"), ("Q(Cap)", 6, ">"), ("Reason", 6, ">"), ("Coding", 6, ">"), ("Design", 6, ">"), ("Rsch", 6, ">"), ("Speed", 6, ">"), ("Ctx", 6, ">"), ("$/Task", 8, ">"), ("Price", 11, ">"), ("Best Role", 13, "<")]
    return [("Rank", 4, "^"), ("Model", 24, "<"), ("Pool", 5, "^"), ("Conf", 6, "^"), ("Q(Cap)", 6, ">"), ("Reason", 6, ">"), ("Coding", 6, ">"), ("Rsch", 6, ">"), ("Speed", 6, ">"), ("Ctx", 5, ">"), ("Price", 11, ">"), ("Best Role", 13, "<")]


def _oneshot_wide_cells(m: dict, base: list, pl: dict, headers, meds: dict, ctx_disp: str, price_disp: str, color: bool) -> list:
    eff = m.get("effective_cost")
    return [
        *base,
        (_fmt_num(pl.get("reasoning"), "{:.1f}", meds.get("reason"), color), _thresh_color(pl.get("reasoning"), 84.0, C_GREEN, C_WHITE), 6, ">"),
        (_fmt_num(pl.get("coding"), "{:.1f}", meds.get("coding"), color), _thresh_color(pl.get("coding"), 84.0, C_GREEN, C_WHITE), 6, ">"),
        (_fmt_num(pl.get("design"), "{:.1f}", meds.get("design"), color), _thresh_color(pl.get("design"), 82.0, C_CYAN, C_WHITE), 6, ">"),
        (_fmt_num(pl.get("research"), "{:.1f}", meds.get("research"), color), _thresh_color(pl.get("research"), 84.0, C_GREEN, C_WHITE), 6, ">"),
        (_fmt_num(pl.get("speed"), "{:.0f}t/s", meds.get("speed"), color), _thresh_color(pl.get("speed"), 120, C_GREEN, C_WHITE), 6, ">"),
        (ctx_disp, C_WHITE, headers[10][1], ">"),
        (_fmt_num(eff, "${:.2f}", meds.get("eff_cost"), color), _eff_cost_color(eff), headers[11][1], ">"),
        (price_disp, C_WHITE, headers[12][1], ">"),
        (pl.get("best_role", "—"), C_CYAN, headers[13][1], "<"),
    ]


def _oneshot_prefix_cells(idx: int, m: dict, headers, pl: dict, meds: dict, added_ids: set, pareto_ids: set, color: bool) -> tuple[list, list]:
    rank_num = idx + 1
    mid_raw = m.get("display") or m.get("model_id", "Unknown")
    is_added, is_pareto = _model_flags(m, added_ids, pareto_ids)
    mid_color = (C_BOLD + C_GREEN) if is_added else ((C_BOLD + C_GOLD) if is_pareto else C_WHITE)
    q_val = m.get("capability_q")
    cov_n = pl["coverage_count"]
    label = (("+" if is_added else "") + mid_raw)[:headers[1][1]]
    base = [
        (_rank_label(rank_num), C_YELLOW if rank_num <= 3 else C_GRAY, headers[0][1], "^"),
        (label, mid_color, headers[1][1], "<"),
        (pool_badge(m.get("pool", "api"), color=color), "", headers[2][1], "^"),
        (coverage_label(cov_n), _conf_color_cli(cov_n), headers[3][1], "^"),
        (_fmt_num(q_val, "{:.1f}", meds.get("q"), color), score_color_q(q_val or 0.0), headers[4][1], ">"),
    ]
    pillars = [
        (_fmt_num(pl.get("reasoning"), "{:.1f}", meds.get("reason"), color), _thresh_color(pl.get("reasoning"), 84.0, C_GREEN, C_WHITE), 6, ">"),
        (_fmt_num(pl.get("coding"), "{:.1f}", meds.get("coding"), color), _thresh_color(pl.get("coding"), 84.0, C_GREEN, C_WHITE), 6, ">"),
        (_fmt_num(pl.get("research"), "{:.1f}", meds.get("research"), color), _thresh_color(pl.get("research"), 84.0, C_GREEN, C_WHITE), 6, ">"),
    ]
    return base, pillars


def _render_oneshot_cli_row(idx: int, m: dict, headers, pillars_map, col_medals, added_ids, pareto_ids, is_slim: bool, wide: bool, color: bool) -> str:
    mid_raw = m.get("display") or m.get("model_id", "Unknown")
    pl = pillars_map.get(mid_raw) or extract_capability_pillars(m)
    meds = col_medals.get(mid_raw, {})
    base, core_pillars = _oneshot_prefix_cells(idx, m, headers, pl, meds, added_ids, pareto_ids, color)
    ctx_disp = format_context_window(pl.get("context_length"))
    price_disp = format_compact_price(m.get("price_in"), m.get("price_out"))
    if is_slim:
        cells = [*base, *core_pillars, (ctx_disp, C_WHITE, headers[8][1], ">")]
    elif wide:
        cells = _oneshot_wide_cells(m, base, pl, headers, meds, ctx_disp, price_disp, color)
    else:
        spd_cell = (_fmt_num(pl.get("speed"), "{:.0f}t/s", meds.get("speed"), color), _thresh_color(pl.get("speed"), 120, C_GREEN, C_WHITE), 6, ">")
        cells = [*base, *core_pillars, spd_cell, (ctx_disp, C_WHITE, headers[9][1], ">"), (price_disp, C_WHITE, headers[10][1], ">"), (pl.get("best_role", "—"), C_CYAN, headers[11][1], "<")]
    return _format_cli_row(cells, BG_ODD if (idx % 2 == 1) else BG_EVEN, color)


def _oneshot_medal_metrics(pillars_map: dict) -> dict:
    def _pl_val(key: str):
        return (
            lambda m: pillars_map.get(m.get("display", ""), {}).get(key) or 0.0,
            True,
            lambda m: pillars_map.get(m.get("display", ""), {}).get(key) is not None,
        )
    return {
        "q": BCHECK_COL_MEDAL_KEYS["q"],
        "eff_cost": BCHECK_COL_MEDAL_KEYS["eff_cost"],
        "reason": _pl_val("reasoning"),
        "coding": _pl_val("coding"),
        "design": _pl_val("design"),
        "research": _pl_val("research"),
        "speed": _pl_val("speed"),
    }


def _oneshot_summary_line(models_list: list, display_models: list, pillars_map: dict, is_slim: bool) -> tuple[str, str]:
    c_info = _top_summary(models_list, lambda m: m.get("capability_q"), "Top Cap", "{:.1f}")
    r_info = _top_summary(models_list, lambda m: pillars_map.get(m.get("display", ""), {}).get("reasoning"), "Reason", "{:.1f}")
    cd_info = _top_summary(models_list, lambda m: pillars_map.get(m.get("display", ""), {}).get("coding"), "Coding", "{:.1f}")
    s_info = _top_summary(models_list, lambda m: pillars_map.get(m.get("display", ""), {}).get("speed"), "Fastest", "{:.0f}t/s")
    shown = f" (Top {len(display_models)} shown)" if len(display_models) < len(models_list) else ""
    count_label = f"Catalog: {len(models_list)} models{shown}"
    parts = [count_label, c_info, cd_info] if is_slim else [count_label, c_info, r_info, cd_info, s_info]
    return count_label, " " + " │ ".join(p for p in parts if p)


_ONESHOT_GUIDE_ITEMS = [
    ("Gold Bold", "Pareto Frontier (undefeated capability vs empirical $/task curve).", C_GOLD),
    ("Conf [k/7]", "Evaluated across AA, Vals, Arena, LiveBench, FrontierCode, FrontierSWE, CursorBench.", C_GREEN),
    ("Reason", "Shrunk Reasoning axis (HLE, CritPt, AA Intelligence, LiveBench).", C_GREEN),
    ("Coding", "Shrunk Coding axis (CursorBench, FrontierCode 2.0, FrontierSWE, TB-4, Vals, LB).", C_GREEN),
    ("Rsch / Design", "Research (non-hallucination/LCR/FSWE/SciCode/GPQA) & Design (WebDev Elo/IFBench) axes.", C_CYAN),
    ("Speed / Ctx", "Generation throughput (tok/s) and context window capacity.", C_WHITE),
]


def render_one_shot_cli_table(models_list, color=None, slim=None, wide=False, pareto_ids=None, added_ids=None, removed_models=None, stale_note=None, top_n: int | None = 30, unmatched_models=None):
    """Render unified one-shot capability table with 5-axis pillars and Best Role."""
    color, is_slim, pareto_ids, added_ids, removed_models, display_models = _cli_ctx(
        models_list, color, slim, wide, pareto_ids, added_ids, removed_models, top_n
    )
    headers = _oneshot_headers(is_slim, wide)
    pillars_map = {(m.get("display") or m.get("model_id") or ""): extract_capability_pillars(m) for m in models_list}
    medal_pool = [m for m in models_list if not m.get("signal_mirror_of")]
    col_medals = compute_column_medals(medal_pool, _oneshot_medal_metrics(pillars_map), id_key="display")
    inner_w = sum(w + 2 for _, w, _ in headers) + len(headers) - 1
    count_label, summary_str = _oneshot_summary_line(models_list, display_models, pillars_map, is_slim)

    notices, parts = _diff_banner_notices(added_ids, removed_models, stale_note)
    out = render_banner_box(
        "🎯 ONE-SHOT 5-AXIS CAPABILITIES RADAR (7 Upstream Authorities)",
        summary_lines=[summary_str],
        diff_notices=notices,
        inner_w=inner_w,
        color=color,
        plain_title_line=f" ONE-SHOT 5-AXIS CAPABILITIES RADAR — {count_label}",
        plain_diff_parts=parts,
    )
    head, bot = _cli_table_frame(headers, color)
    out.extend(head)
    out.extend(_render_oneshot_cli_row(idx, m, headers, pillars_map, col_medals, added_ids, pareto_ids, is_slim, wide, color) for idx, m in enumerate(display_models))
    out.append(bot)

    if removed_models:
        out.extend(["", *render_removed_models_cli(removed_models, color=color, is_slim=is_slim, id_key="display")])
    _append_cli_footer(out, "One-Shot 5-Axis Guide", _ONESHOT_GUIDE_ITEMS, medal_pool, unmatched_models, color, is_slim, inner_w)
    return "\n".join(out)


def _podium_winners(models_list, spec) -> list[tuple[dict, str]]:
    _, _, key_fn, rev, filt, fmt_fn = spec
    valid = [m for m in models_list if filt(m)] if filt else models_list
    return [(m, fmt_fn(m)) for m in sorted(valid, key=key_fn, reverse=rev)[:3]]


def render_podium_table(models_list, color=None):
    """Render top 3 winners podium table across all key roles and benchmarks."""
    if color is None:
        color = not os.getenv("NO_COLOR")
    headers = [
        ("Metric / Role", 26, "<"),
        ("🥇 1st Place (Gold)", 32, "<"),
        ("🥈 2nd Place (Silver)", 32, "<"),
        ("🥉 3rd Place (Bronze)", 32, "<"),
    ]
    inner_w = sum(w + 2 for _, w, _ in headers) + len(headers) - 1
    title = "🏆 ROLE & BENCHMARK PODIUM LEADERS (1st 🥇 · 2nd 🥈 · 3rd 🥉)"
    out = []
    if color:
        clean_title = title + (" " * max(0, inner_w - 2 - display_len(title)))
        out.extend([
            f"{C_GOLD}╭" + ("─" * inner_w) + f"╮{C_RESET}",
            f"{C_GOLD}│{C_RESET} {C_BOLD}{C_WHITE}{clean_title}{C_RESET} {C_GOLD}│{C_RESET}",
            f"{C_GOLD}╰" + ("─" * inner_w) + f"╯{C_RESET}",
            "",
        ])
    else:
        out.extend(["=" * (inner_w + 2), f" {title}", "=" * (inner_w + 2)])

    head, bot = _cli_table_frame(headers, color)
    out.extend(head)
    medal_pool = [m for m in models_list if not m.get("signal_mirror_of")]
    medal_colors = [C_GOLD, C_SILVER, C_BRONZE]
    for idx, spec in enumerate(_PODIUM_SPECS):
        bg = BG_ODD if (idx % 2 == 1) else BG_EVEN
        winners = _podium_winners(medal_pool, spec)
        cells = [(spec[0], C_BOLD + C_CYAN, 26, "<")]
        for pos in range(3):
            if pos < len(winners):
                m, val = winners[pos]
                txt = f"{m['display'][:18]} {pool_badge(m['pool'], color=False)} ({val})"
                cells.append((txt, medal_colors[pos], 32, "<"))
            else:
                cells.append(("—", C_GRAY, 32, "<"))
        out.append(_format_cli_row(cells, bg, color))
    out.append(bot)
    return "\n".join(out)


def render_sub_table_md(sub_models, title, top_n=10):
    """Render markdown sub-table for single-source / emerging models."""
    if not sub_models:
        return ""
    lines = [
        f"### {title}",
        "",
        "| Rank | Model | Pool / Tier | Best Role | Q (Cap) | $/Task | Cursor (%) | FC2 (%) | Arena Elo | AA Intel | Raw $/M |",
        "| :---: | :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]
    for i, m in enumerate(sub_models[:top_n], 1):
        sm = _sub_metrics(m)
        sub = f"`{m['pool'].upper()}` ({m['tier']})"
        q = f"**{sm['q_str']}**" if bc._is_num(sm["q"]) else "—"
        cost = format_compact_price(m.get("price_in"), m.get("price_out"))
        lines.append(f"| #{i} | **{m['display']}** | {sub} | {sm['role']} | {q} | {sm['c_str']} | {sm['cur_str']} | {sm['fc2_str']} | {sm['elo_str']} | {sm['aa_str']} | {cost} |")
    lines.append("")
    return "\n".join(lines)


def render_sub_table_html(sub_models, title, top_n=10):
    """Render HTML sub-table for single-source / emerging models."""
    if not sub_models:
        return ""
    trs = []
    for i, m in enumerate(sub_models[:top_n], 1):
        sm = _sub_metrics(m)
        pool_cls = _POOL_HTML_CLS.get(m["pool"], "")
        trs.append(f"""        <tr>
            <td style="font-weight:700; text-align:center;">#{i}</td>
            <td style="font-weight:600;">{html.escape(m['display'])}</td>
            <td><span class="badge {pool_cls}">{m['pool'].upper()}</span></td>
            <td>{html.escape(sm['role'])}</td>
            <td style="font-weight:700; color:#2563eb;">{sm['q_str']}</td>
            <td>{sm['c_str']}</td>
            <td style="font-weight:600; color:#10b981;">{sm['cur_str']}</td>
            <td style="font-weight:600; color:#f59e0b;">{sm['fc2_str']}</td>
            <td>{sm['elo_str']}</td>
            <td>{sm['aa_str']}</td>
            <td>{format_compact_price(m.get('price_in'), m.get('price_out'))}</td>
        </tr>""".strip())
    trs_html = "\n            ".join(trs)
    return f"""
    <h3>{html.escape(title)}</h3>
    <table>
        <thead>
            <tr>
                <th>Rank</th><th>Model</th><th>Pool</th><th>Best Role</th>
                <th>Q (Cap)</th><th>$/Task</th><th>CursorBench</th><th>FrontierCode</th>
                <th>Arena Elo</th><th>AA Intel</th><th>Price In/Out</th>
            </tr>
        </thead>
        <tbody>{trs_html}</tbody>
    </table>
    """.strip()


def _md_role_leaders(models: list[dict], role_key: str, limit: int = 3) -> str:
    scored = sorted((m for m in models if _role_val(m, role_key) is not None), key=lambda m: _role_val(m, role_key) or 0.0, reverse=True)
    items = [f"**{m['display']}** ({_role_val(m, role_key):.1f})" for m in scored[:limit]]
    return ", ".join(items) if items else "—"


def _render_dynamic_insights_md(models_list, pareto_ids) -> list[str]:
    non_mirrors = [m for m in models_list if not m.get("signal_mirror_of")]
    pareto_names = [m["display"] for m in non_mirrors if m["display"] in pareto_ids or m.get("model_id") in pareto_ids][:5]
    pareto_txt = ", ".join(pareto_names) if pareto_names else "—"
    return [
        "",
        "## 5. Key Insights & Task-Role Routing",
        "",
        f"- **⭐ Pareto Frontier Models**: Undefeated capability-vs-cost frontier ({pareto_txt}).",
        f"- **🏗️ System Architecture & Spec Lock**: {_md_role_leaders(non_mirrors, 'architecture')}.",
        f"- **💻 Agentic Software Development**: {_md_role_leaders(non_mirrors, 'software_dev')}.",
        f"- **🎨 UI / UX & Frontend Design**: {_md_role_leaders(non_mirrors, 'design')}.",
        f"- **🔬 Academic Research & Grounded Synthesis**: {_md_role_leaders(non_mirrors, 'research')}.",
        "- **Thinking-Level Discipline**: Medium/High thinking often matches or beats Max effort at 30–70% lower empirical $/task while avoiding over-thinking step loops.",
        "",
        f"_Generated by `llm_benchmark_aggregator.py` (`bcheck`) on {dt.datetime.now(dt.UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}._",
    ]


def _md_main_row(m: dict, pareto_ids: set) -> str:
    _, is_pareto = _model_flags(m, set(), pareto_ids)
    mid = f"⭐ **{m['display']}**" if is_pareto else f"**{m['display']}**"
    conf = coverage_label(sum(signal_coverage(m).values()))
    bm = bc._as_dict(m.get("base_metrics"))
    return (
        f"| {conf} | {mid} | `{m['pool'].upper()}` | "
        f"{_fmt_num(m.get('capability_q'), '**{:.1f}**')} | "
        f"{_fmt_num(_role_val(m, 'architecture'), '{:.1f}')} | "
        f"{_fmt_num(_role_val(m, 'software_dev'), '{:.1f}')} | "
        f"{_fmt_num(_role_val(m, 'design'), '{:.1f}')} | "
        f"{_fmt_num(_role_val(m, 'research'), '{:.1f}')} | "
        f"{_fmt_num(m.get('effective_cost'), '${:.2f}')} | "
        f"{_fmt_num(bm.get('cursor_score'), '{:.1f}%')} | "
        f"{_fmt_num(bm.get('fc2_score'), '{:.1f}%')} | "
        f"{format_compact_price(m.get('price_in'), m.get('price_out'))} |"
    )


def _md_podium_row(non_mirrors: list[dict], spec: tuple) -> str:
    winners = _podium_winners(non_mirrors, spec)
    places = [
        f"**{winners[pos][0]['display']}** `{pool_badge(winners[pos][0]['pool'], color=False)}` ({winners[pos][1]})"
        if pos < len(winners) else "—"
        for pos in range(3)
    ]
    return f"| **{spec[1]}** | {places[0]} | {places[1]} | {places[2]} |"


def _md_partial_section(partitions: dict, unmatched_models) -> list[str]:
    out = ["", "## 2. Emerging / Single-Authority Models", ""]
    for k, _, md_t in _SUB_TABLE_SPECS:
        if partitions[k]:
            out.append(render_sub_table_md(partitions[k], md_t, top_n=10))
    all_unmatched = _merge_unmatched_models(unmatched_models, partitions.get("unmatched", []))
    if all_unmatched:
        out.append(render_unmatched_models_md(all_unmatched))
    return out


def render_markdown_report(models_list, title=None, pareto_ids=None, top_n: int | None = 30, unmatched_models=None):
    """Render Markdown report: 7-authority Q & 4-role leaderboard, podium, and routing guide."""
    pareto_ids = compute_priced_pareto_frontier(models_list) if pareto_ids is None else pareto_ids
    title = title or f"Consolidated LLM Benchmark & Task-Role Report ({dt.datetime.now(dt.UTC).date().isoformat()})"
    partitions = partition_models_by_benchmark_coverage(models_list)
    display_models = _clip_models(models_list, top_n)
    conf_summary = " · ".join(f"[{n}/7] {c}" for n, c in partitions["counts"].items())

    lines = [
        f"# {title}\n",
        "Consolidated capability, role, and empirical `$/task` radar across **Artificial Analysis v5.0.1**, **Vals Index**, **LMArena**, **LiveBench**, **Cognition FrontierCode 2.0**, **FrontierSWE**, and **CursorBench 4.0**.",
        "",
        "## 1. Consensus Master Leaderboard (Q-ranked · Confidence [k/7] · Distinct Thinking Levels)",
    ]
    if len(display_models) < len(models_list):
        lines.append(f"_Showing top {len(display_models)} of {len(models_list)} ranked models._")
    lines.extend([
        f"_Confidence: {conf_summary} — James-Stein shrinkage (λ=0.20) prevents single-source outliers from leapfrogging multi-authority consensus._",
        "",
        "| Conf | Model | Pool | Q (Cap) | Arch | Soft Dev | Design | Research | $/Task | Cursor (%) | FC2 (%) | Raw $/M |",
        "| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
        *(_md_main_row(m, pareto_ids) for m in display_models),
        *_md_partial_section(partitions, unmatched_models),
    ])

    non_mirrors = [m for m in models_list if not m.get("signal_mirror_of")]
    lines.extend([
        "",
        "## 3. Role & Benchmark Podium Leaders (1st 🥇 · 2nd 🥈 · 3rd 🥉)",
        "",
        "| Metric / Role | 🥇 1st Place (Gold) | 🥈 2nd Place (Silver) | 🥉 3rd Place (Bronze) |",
        "| :--- | :--- | :--- | :--- |",
        *(_md_podium_row(non_mirrors, spec) for spec in _PODIUM_SPECS),
    ])
    role_recs = compute_role_recommendations(non_mirrors, context="bcheck")
    if role_recs:
        lines.extend(["", "## 4. Dynamic Function & Role Recommendations (Weighted Scoring)", "", render_role_recommendations_md(role_recs)])
    lines.extend(_render_dynamic_insights_md(models_list, pareto_ids))
    return "\n".join(lines)


def _html_model_label(m: dict, is_added: bool, is_pareto: bool) -> str:
    esc = html.escape(m["display"])
    if is_added:
        return f"<span style='color:#10b981; font-weight:700;'>+{esc}</span> <span class='badge badge-new'>+NEW</span>"
    if is_pareto:
        return f"<span style='color:#d29922; font-weight:700;'>{esc}</span> <span style='background:rgba(210,153,34,0.18); color:#d29922; border:1px solid #d29922; padding:1px 5px; border-radius:3px; font-size:10px; font-weight:600;'>PARETO</span>"
    return esc


def _html_main_row(m: dict, added_ids: set, pareto_ids: set) -> str:
    bm = bc._as_dict(m.get("base_metrics"))
    is_added, is_pareto = _model_flags(m, added_ids, pareto_ids)
    pool_cls = _POOL_HTML_CLS.get(m["pool"], "")
    name_html = _html_model_label(m, is_added, is_pareto)
    row_cls_parts = (["added"] if is_added else []) + (["pareto"] if is_pareto else [])
    row_cls = f" class='{' '.join(row_cls_parts)}'" if row_cls_parts else ""
    cov_n = sum(signal_coverage(m).values())
    cov_color = "#10b981" if cov_n >= 5 else ("#2563eb" if cov_n >= 3 else ("#d29922" if cov_n == 2 else "#8b949e"))
    return f"""        <tr{row_cls}>
            <td><span style="font-weight:600; color:{cov_color};">{coverage_label(cov_n)}</span></td>
            <td style="font-weight:600;">{name_html}</td>
            <td><span class="badge {pool_cls}">{m['pool'].upper()}</span></td>
            <td>{html.escape(m.get('best_role') or m['tier'])}</td>
            <td style="font-weight:700; color:#2563eb;">{_fmt_num(m.get('capability_q'), '{:.1f}')}</td>
            <td style="font-weight:600; color:#8b5cf6;">{_fmt_num(_role_val(m, 'architecture'), '{:.1f}')}</td>
            <td style="font-weight:600; color:#10b981;">{_fmt_num(_role_val(m, 'software_dev'), '{:.1f}')}</td>
            <td style="font-weight:600; color:#06b6d4;">{_fmt_num(_role_val(m, 'design'), '{:.1f}')}</td>
            <td style="font-weight:600; color:#f59e0b;">{_fmt_num(_role_val(m, 'research'), '{:.1f}')}</td>
            <td>{_fmt_num(m.get('effective_cost'), '${:.2f}')}</td>
            <td>{_fmt_num(bm.get('cursor_score'), '{:.1f}%')}</td>
            <td>{_fmt_num(bm.get('fc2_score'), '{:.1f}%')}</td>
            <td>{_fmt_num(bm.get('speed_tps'), '{:.0f} t/s')}</td>
            <td>{format_compact_price(m.get('price_in'), m.get('price_out'))}</td>
        </tr>""".strip()


def _html_removed_section(removed_models) -> str:
    if not removed_models:
        return ""
    rem_tags = []
    for rm in removed_models:
        rm_id = html.escape(rm.get("display") or rm.get("model_id", "unknown"))
        pool_str = rm.get("pool", "").upper()
        q = rm.get("capability_q") or bc._as_dict(rm.get("benchmarks")).get("capability_q")
        q_s = f"Q {q:.1f}" if bc._is_num(q) else "Q —"
        rem_tags.append(f'<span class="removed-tag">❌ <b>{rm_id}</b> <span class="mid">({pool_str}, {q_s})</span></span>')
    return f"""
        <div class="removed-section">
          <div class="removed-title">🔻 Removed / Deprecated Benchmark Models ({len(removed_models)})</div>
          <div class="sub" style="margin-bottom:8px;">These models were present in the previous benchmark catalog snapshot but are no longer active in the current benchmark leaderboard:</div>
          <div>{"".join(rem_tags)}</div>
        </div>
        """


def _html_podium_rows(non_mirrors: list[dict]) -> list[str]:
    rows = []
    for spec in _PODIUM_SPECS:
        winners = _podium_winners(non_mirrors, spec)
        cells = [
            f"<b>{html.escape(winners[pos][0]['display'])}</b> <small style='color:#94a3b8;'>{pool_badge(winners[pos][0]['pool'], color=False)}</small> <span style='color:#f59e0b;'>({winners[pos][1]})</span>"
            if pos < len(winners) else "—"
            for pos in range(3)
        ]
        rows.append(f'<tr><td style="font-weight:600; color:#38bdf8;">{spec[0]}</td><td>{cells[0]}</td><td>{cells[1]}</td><td>{cells[2]}</td></tr>')
    return rows


def render_html_report(models_list, pareto_ids=None, added_ids=None, removed_models=None, stale_note=None, top_n: int | None = 30, unmatched_models=None):
    """Render standalone HTML dashboard across all 7 authorities and 4 task roles."""
    pareto_ids = compute_priced_pareto_frontier(models_list) if pareto_ids is None else pareto_ids
    added_ids = added_ids or set()
    removed_models = removed_models or []

    partitions = partition_models_by_benchmark_coverage(models_list)
    display_models = _clip_models(models_list, top_n)
    non_mirrors = [m for m in models_list if not m.get("signal_mirror_of")]
    role_recs = compute_role_recommendations(non_mirrors, context="bcheck")
    role_recs_html = render_role_recommendations_html(role_recs) if role_recs else ""

    trs = [_html_main_row(m, added_ids, pareto_ids) for m in display_models]
    podium_trs = _html_podium_rows(non_mirrors)
    sub_tables_html = [render_sub_table_html(partitions[k], cli_t, top_n=10) for k, cli_t, _ in _SUB_TABLE_SPECS if partitions[k]]
    all_unmatched = _merge_unmatched_models(unmatched_models, partitions.get("unmatched", []))
    if all_unmatched:
        sub_tables_html.append(render_unmatched_models_html(all_unmatched))
    trs_html = "\n            ".join(trs)
    sub_tables_joined = "\n".join(sub_tables_html)
    podium_trs_html = "\n            ".join(podium_trs)

    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Consolidated LLM Benchmark & Task-Role Dashboard</title>
    <style>{HTML_CSS_COMMON}</style>
</head>
<body>
<div class="wrap">
    <h1>Consolidated LLM Benchmark & Task-Role Dashboard</h1>
    <div class="sub">Artificial Analysis v5.0.1 · Vals Index · LMArena · LiveBench · Cognition FrontierCode 2.0 · FrontierSWE · CursorBench 4.0</div>
    {f'<div class="legend">⚠ {html.escape(stale_note)}</div>' if stale_note else ""}

    <h2>1. Consensus Master Leaderboard (Q-ranked · Confidence [k/7] · Distinct Thinking Levels)</h2>
    <p class="sub">5 shrunk orthogonal axes (Reasoning, Coding, Design, Research, Economics; λ=0.20) → 4 task roles (Architecture, Software Dev, Design, Research).</p>
    <table id="tbl">
        <thead>
            <tr>
                <th>Conf</th><th>Model</th><th>Pool</th><th>Best Role</th>
                <th>Q (Cap)</th><th>Arch</th><th>Soft Dev</th><th>Design</th>
                <th>Research</th><th>$/Task</th><th>CursorBench</th><th>FrontierCode</th>
                <th>Speed</th><th>Price In/Out</th>
            </tr>
        </thead>
        <tbody>{trs_html}</tbody>
    </table>

    <h2>2. Emerging / Single-Authority Models</h2>
    {sub_tables_joined}

    <h2>3. Role & Benchmark Podium Leaders (1st 🥇 · 2nd 🥈 · 3rd 🥉)</h2>
    <table>
        <thead>
            <tr><th>Metric / Role</th><th>🥇 1st Place (Gold)</th><th>🥈 2nd Place (Silver)</th><th>🥉 3rd Place (Bronze)</th></tr>
        </thead>
        <tbody>{podium_trs_html}</tbody>
    </table>

    {_html_removed_section(removed_models)}
    {role_recs_html}
</div>
{HTML_SORT_SCRIPT}
</body>
</html>
"""


def save_baseline(models_list, catalog_diff, path=None):
    """Persist the authoritative 7-source, 5-axis, 4-role baseline in benchmarks.json."""
    p = pathlib.Path(path) if path else (DATA / "benchmarks.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    non_mirrors = [m for m in models_list if not m.get("signal_mirror_of")]
    payload = {
        "generated_at": dt.datetime.now(dt.UTC).isoformat(),
        "authority_total": len(COVERAGE_SOURCES),
        "authorities": list(COVERAGE_SOURCES),
        "catalog_diff": {
            "added": sorted(str(x) for x in catalog_diff["added_ids"]),
            "removed": sorted(str(x) for x in catalog_diff["removed_ids"]),
            "total_current": len(models_list),
        },
        "role_recommendations": compute_role_recommendations(non_mirrors, context="bcheck"),
        "models": models_list,
    }
    bc.atomic_write_text(p, json.dumps(payload, indent=2))
    return p


# ==============================================================================
# 4. MAIN CLI LOGIC
# ==============================================================================

_SORT_KEY_MAP = {
    "composite": (lambda m: m.get("composite_score") or 0.0, True),
    "arch": (lambda m: _role_val(m, "architecture") or 0.0, True),
    "architecture": (lambda m: _role_val(m, "architecture") or 0.0, True),
    "dev": (lambda m: _role_val(m, "software_dev") or 0.0, True),
    "software_dev": (lambda m: _role_val(m, "software_dev") or 0.0, True),
    "design": (lambda m: _role_val(m, "design") or 0.0, True),
    "research": (lambda m: _role_val(m, "research") or 0.0, True),
    "avi": (lambda m: m.get("avi_score") or 0.0, True),
    "coding": (lambda m: bc._as_dict(m.get("axes")).get("coding") or 0.0, True),
    "reasoning": (lambda m: bc._as_dict(m.get("axes")).get("reasoning") or 0.0, True),
    "speed": (lambda m: bc._as_dict(m.get("base_metrics")).get("speed_tps") or 0.0, True),
    "live": (lambda m: _lb_overall(m) or 0.0, True),
    "vals": (lambda m: m.get("vals_overall") or 0.0, True),
    "cursor": (lambda m: bc._as_dict(m.get("base_metrics")).get("cursor_score") or 0.0, True),
    "fc2": (lambda m: bc._as_dict(m.get("base_metrics")).get("fc2_score") or 0.0, True),
    "fswe": (lambda m: bc._as_dict(m.get("base_metrics")).get("fswe_overall") or 0.0, True),
    "price": (lambda m: m.get("price_in") if m.get("price_in") is not None else 999.0, False),
    "effective_cost": (lambda m: m.get("effective_cost") if m.get("effective_cost") is not None else 999.0, False),
    "empirical_cost": (lambda m: m.get("empirical_cost") if m.get("empirical_cost") is not None else 999.0, False),
}


def _filter_by_pool(models: list, pool: str) -> list:
    if pool in ("accessible", "my-pools"):
        return [m for m in models if m["pool"] in ("claude", "agy", "ocgo")]
    if pool == "post-claude":
        return [m for m in models if m["pool"] in ("agy", "ocgo")]
    if pool != "all":
        return [m for m in models if m["pool"] == pool]
    return models


def _launch_checkerz_tui(args) -> None:
    bin_rel = ROOT / "checkerz" / "target" / "release" / "checkerz"
    bin_dbg = ROOT / "checkerz" / "target" / "debug" / "checkerz"
    cargo_toml = ROOT / "checkerz" / "Cargo.toml"
    cmd = None
    if shutil.which("checkerz"):
        cmd = ["checkerz"]
    elif bin_rel.exists():
        cmd = [str(bin_rel)]
    elif bin_dbg.exists():
        cmd = [str(bin_dbg)]
    elif cargo_toml.exists() and shutil.which("cargo"):
        cmd = ["cargo", "run", "--manifest-path", str(cargo_toml), "--"]

    if not cmd:
        print("bcheck --tui moved to the Rust checkerz binary: cargo run --manifest-path checkerz/Cargo.toml [-- --all -n 50]", file=sys.stderr)
        return
    extra = (["--all"] if args.all else []) + (["-n", str(args.top)] if args.top is not None else [])
    try:
        subprocess.run(cmd + extra)
    except Exception as e:
        print(f"Error launching checkerz: {e}", file=sys.stderr)


def _parse_cli_args():
    parser = argparse.ArgumentParser(
        description="Consolidate benchmarks across 7 upstream authorities with distinct thinking levels and 4 task roles."
    )
    parser.add_argument("--pool", choices=["all", "accessible", "my-pools", "post-claude", "ocgo", "agy", "claude", "frontier", "api", "hetzner", "nvidia"], default="all", help="Filter by ecosystem (default: all)")
    parser.add_argument("--sort", choices=list(_SORT_KEY_MAP), default="composite", help="Sort criterion (default: composite)")
    parser.add_argument("-n", "--top", type=int, default=30, help="Number of top models to display in report (default: 30; use --all for full catalog)")
    parser.add_argument("--all", action="store_true", help="Display all tracked models across the catalog (disables top-30 limit)")
    parser.add_argument("--podium", "--winners", action="store_true", help="Display top 3 winners podium table across every metric/role")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    parser.add_argument("--md", type=str, nargs="?", const="stdout", help="Output Markdown report")
    parser.add_argument("--html", type=str, nargs="?", const="docs/reports/benchmarks.html", help="Generate HTML dashboard")
    parser.add_argument("--fetch", "--refresh", action="store_true", help="Refresh 24h cache across all 7 authorities and update benchmarks.json baseline.")
    parser.add_argument("--save-baseline", action="store_true", help="Write docs/data/benchmarks.json from current cached snapshots without network fetch.")
    parser.add_argument("--plain", "--no-color", action="store_true", help="Disable ANSI colors and box drawing")
    parser.add_argument("--slim", action="store_true", help="Force compact table layout (for split panes)")
    parser.add_argument("--wide", action="store_true", help="Force full wide table layout")
    parser.add_argument("-1", "--one-shot", action="store_true", help="Display unified one-shot capabilities table with 5-axis pillars")
    parser.add_argument("-i", "--tui", "--interactive", action="store_true", help="Launch interactive checkerz TUI dashboard")
    return parser.parse_args()


def _emit_cli_or_tui(args, models: list[dict], top_n: int | None, added_ids: set, removed_models: list, stale_note: str | None, unmatched_catalog: list) -> None:
    if args.tui:
        _launch_checkerz_tui(args)
        return
    use_color = False if args.plain else None
    if args.podium:
        print(render_podium_table(models, color=use_color))
        return
    slim_opt = True if args.slim else (False if args.wide else None)
    renderer = render_one_shot_cli_table if args.one_shot else render_cli_table
    print(renderer(models, color=use_color, slim=slim_opt, wide=args.wide, added_ids=added_ids, removed_models=removed_models, stale_note=stale_note, top_n=top_n, unmatched_models=unmatched_catalog))


def _emit_doc_outputs(args, models: list[dict], top_n: int | None, added_ids: set, removed_models: list, stale_note: str | None, unmatched_catalog: list) -> bool:
    if args.json:
        print(json.dumps(models[:top_n] if top_n else models, indent=2))
        return True
    if args.md:
        md_text = render_markdown_report(models, top_n=top_n, unmatched_models=unmatched_catalog)
        if args.md == "stdout":
            print(md_text)
        else:
            bc.atomic_write_text(pathlib.Path(args.md), md_text)
            print(f"Wrote Markdown report to {args.md}")
    if args.html:
        html_text = render_html_report(models, added_ids=added_ids, removed_models=removed_models, stale_note=stale_note, top_n=top_n, unmatched_models=unmatched_catalog)
        bc.atomic_write_text(pathlib.Path(args.html), html_text)
        print(f"Wrote HTML dashboard to {args.html}")
    return bool(args.md or args.html)


def main():
    args = _parse_cli_args()
    do_fetch = bool(args.fetch)
    top_n = None if (args.all or args.top <= 0) else args.top
    catalog = build_universal_catalog(
        live_map=load_livebench_data(fetch=do_fetch),
        lm_map=load_lmarena_data(fetch=do_fetch),
        aa_map=load_aa_data(fetch=do_fetch),
        vals_map=load_vals_data(fetch=do_fetch),
        fc2_map=load_frontiercode_data(fetch=do_fetch),
        fswe_map=load_frontierswe_data(fetch=do_fetch),
        cursor_map=load_cursor_data(fetch=do_fetch),
    )
    calculate_composite_scores(catalog)

    unmatched_catalog = [m for m in catalog.values() if m.get("unmatched")]
    models = [m for m in catalog.values() if not m.get("unmatched")]
    models.sort(key=lambda m: m.get("composite_score") or 0.0, reverse=True)
    catalog_diff = diff_model_catalog(models, load_previous_snapshot(DATA / "benchmarks.json"), id_key="display")
    models = catalog_diff["rows"]
    if do_fetch or args.save_baseline:
        p = save_baseline(models, catalog_diff)
        if not args.json:
            print(f"  updated NEW-baseline -> {p.relative_to(ROOT)}", file=sys.stderr)

    models = _filter_by_pool(models, args.pool)
    unmatched_catalog = _filter_by_pool(unmatched_catalog, args.pool)
    sort_key, sort_rev = _SORT_KEY_MAP[args.sort]
    models.sort(key=sort_key, reverse=sort_rev)
    stale_note = cache_staleness_note()
    if _emit_doc_outputs(args, models, top_n, catalog_diff["added_ids"], catalog_diff["removed_models"], stale_note, unmatched_catalog):
        return
    _emit_cli_or_tui(args, models, top_n, catalog_diff["added_ids"], catalog_diff["removed_models"], stale_note, unmatched_catalog)


if __name__ == "__main__":
    main()
