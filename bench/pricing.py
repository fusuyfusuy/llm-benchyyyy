"""$/token table -- Anthropic models only, matching v1's provider scope.

CLI-harness runs on non-Anthropic models (Codex/OpenAI, Antigravity/Gemini,
etc.) use the harness's own self-reported cost from its JSON output instead
of a lookup here -- see harness/cli_adapter.py.
"""
from __future__ import annotations

# USD per million tokens.
PRICING_PER_MTOK = {
    "claude-sonnet-5": {"input": 3.0, "output": 15.0},
    "claude-opus-5": {"input": 15.0, "output": 75.0},
    "claude-haiku-4-5-20251001": {"input": 0.8, "output": 4.0},
}
_DEFAULT_RATES = {"input": 3.0, "output": 15.0}


def cost_usd(model: str, input_tokens: int | None, output_tokens: int | None) -> float | None:
    if input_tokens is None or output_tokens is None:
        return None
    rates = PRICING_PER_MTOK.get(model, _DEFAULT_RATES)
    return (input_tokens / 1_000_000) * rates["input"] + (output_tokens / 1_000_000) * rates["output"]
