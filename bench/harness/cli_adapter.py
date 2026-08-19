"""Generic adapter driving any HarnessConfig: run its CLI in the sandbox, parse
its own JSON/JSONL output for response text + tokens + cost + tool-call-count.

One class, five configs (configs.py) -- not five bespoke adapters.
"""
from __future__ import annotations

import json
import shlex
import time
from dataclasses import dataclass

from .. import sandbox as sandbox_mod
from .configs import HarnessConfig


@dataclass
class HarnessRunResult:
    response_text: str
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: float | None
    tool_call_count: int | None
    wall_clock_seconds: float
    raw_exit_code: int


def _dig(obj, path: list[str] | None):
    if path is None or obj is None:
        return None
    cur = obj
    for key in path:
        if isinstance(cur, dict) and key in cur:
            cur = cur[key]
        else:
            return None
    return cur


def _parse_jsonl(text: str) -> list[dict]:
    events = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            events.append(obj)
    return events


def _find_last(events: list[dict], path: list[str] | None):
    if path is None:
        return None
    for ev in reversed(events):
        val = _dig(ev, path)
        if val is not None:
            return val
    return None


def _build_argv(config: HarnessConfig, prompt: str, model: str | None) -> list[str]:
    argv = [prompt if tok == "{prompt}" else tok for tok in config.command]
    if model and config.model_flag:
        argv += [tok.replace("{model}", model) for tok in config.model_flag]
    return argv


def run(config: HarnessConfig, sb: sandbox_mod.Sandbox, prompt: str, model: str | None = None) -> HarnessRunResult:
    argv = _build_argv(config, prompt, model)
    command_str = " ".join(shlex.quote(a) for a in argv)

    start = time.monotonic()
    proc = sandbox_mod.run(sb, command_str, timeout=config.timeout_seconds)
    elapsed = time.monotonic() - start

    if config.parse == "single-json":
        try:
            obj = json.loads(proc.stdout)
        except json.JSONDecodeError:
            obj = {}
        response_text = _dig(obj, config.response_path) or proc.stdout
        input_tokens = _dig(obj, config.input_tokens_path)
        output_tokens = _dig(obj, config.output_tokens_path)
        cost_usd = _dig(obj, config.cost_path)
        tool_call_count = _dig(obj, config.tool_call_count_path)
    else:
        events = _parse_jsonl(proc.stdout)
        response_text = _find_last(events, config.response_path) or proc.stdout
        input_tokens = _find_last(events, config.input_tokens_path)
        output_tokens = _find_last(events, config.output_tokens_path)
        cost_usd = _find_last(events, config.cost_path)
        tool_call_count = (
            sum(1 for ev in events if ev.get("type") in config.tool_call_event_types) or None
            if config.tool_call_event_types
            else None
        )

    return HarnessRunResult(
        response_text=response_text if isinstance(response_text, str) else str(response_text),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
        tool_call_count=tool_call_count,
        wall_clock_seconds=elapsed,
        raw_exit_code=proc.returncode,
    )
