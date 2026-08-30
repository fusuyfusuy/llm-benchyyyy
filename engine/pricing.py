"""$/token table -- Anthropic models only, matching v1's provider scope.

CLI-harness runs on non-Anthropic models (Codex/OpenAI, Antigravity/Gemini,
etc.) use the harness's own self-reported cost from its JSON output instead
of a lookup here -- see harness/cli_adapter.py.
"""
from __future__ import annotations

import sys

# USD per million tokens. Keys are canonical undated ids (memory.md rule 4);
# the old dated haiku slug resolves through _ALIASES, never through the
# default tier -- falling to Sonnet rates overstated haiku cost ~3.75x.
PRICING_PER_MTOK = {
    "claude-sonnet-5": {"input": 3.0, "output": 15.0},
    "claude-opus-5": {"input": 15.0, "output": 75.0},
    "claude-haiku-4-5": {"input": 0.8, "output": 4.0},
}
_ALIASES = {"claude-haiku-4-5-20251001": "claude-haiku-4-5"}
_DEFAULT_RATES = {"input": 3.0, "output": 15.0}
_WARNED: set[str] = set()


def normalize(model: str) -> str:
    """Canonical pricing id for a (possibly dated, pre-rule-4) model string."""
    return _ALIASES.get(model, model)


def known(model: str) -> bool:
    """True when a real rate entry backs this id (callers use this instead
    of `in PRICING_PER_MTOK` so aliases resolve the same way cost does)."""
    return normalize(model) in PRICING_PER_MTOK


def cost_usd(model: str, input_tokens: int | None, output_tokens: int | None) -> float | None:
    if input_tokens is None or output_tokens is None:
        return None
    key = normalize(model)
    if key in PRICING_PER_MTOK:
        rates = PRICING_PER_MTOK[key]
    else:
        # Never a silent Sonnet-rate fallback: an unpriced id misprices by
        # up to 5x (opus vs default). Warn once per id, then best-effort.
        if model not in _WARNED:
            _WARNED.add(model)
            print(f"pricing: WARN no entry for {model}, using default tier",
                  file=sys.stderr)
        rates = _DEFAULT_RATES
    return (input_tokens / 1_000_000) * rates["input"] + (output_tokens / 1_000_000) * rates["output"]
