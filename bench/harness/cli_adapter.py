"""Generic adapter driving any HarnessConfig: run its CLI in the sandbox, parse
its own JSON/JSONL output for response text + tokens + cost + tool-call-count.

One class, five configs (configs.py) -- not five bespoke adapters.
"""
from __future__ import annotations

import json
import shlex
import subprocess
import threading
import time
from dataclasses import dataclass

from .. import sandbox as sandbox_mod
from .configs import HarnessConfig

_VERSION_CACHE: dict[str, str] = {}
_VERSION_LOCK = threading.Lock()


def harness_version(config: HarnessConfig) -> str:
    """Real CLI version via config.version_argv, cached; name on any failure."""
    with _VERSION_LOCK:
        if config.name in _VERSION_CACHE:
            return _VERSION_CACHE[config.name]
        version = config.name
        if config.version_argv:
            try:
                proc = subprocess.run(
                    list(config.version_argv), capture_output=True, text=True, timeout=15
                )
                if proc.returncode == 0 and proc.stdout.strip():
                    version = proc.stdout.strip().splitlines()[0]
            except OSError:
                pass
        _VERSION_CACHE[config.name] = version
        return version


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
        elif isinstance(cur, list):
            # pi's message.content is a list of typed blocks (thinking/text/...);
            # step into the first block carrying the requested key AND take that
            # key's value, so ["message","content","text"] yields the string.
            block = next((item for item in cur if isinstance(item, dict) and key in item), None)
            if block is None:
                return None
            cur = block[key]
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


Metrics = tuple[int | None, int | None, float | None]


def _as_int(val) -> int | None:
    try:
        return int(val) if isinstance(val, (int, float)) and not isinstance(val, bool) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _as_float(val) -> float | None:
    try:
        return float(val) if isinstance(val, (int, float)) and not isinstance(val, bool) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _sum_metrics(events: list[dict], event_types: tuple[str, ...], paths: tuple[list[str] | None, ...]) -> Metrics:
    """Sum numeric metric values across events of the given types (per-turn
    usage must be summed over a multi-turn run, not last-value-wins)."""
    totals: list[float] = [0.0, 0.0, 0.0]
    seen = [False, False, False]
    for ev in events:
        if ev.get("type") not in event_types:
            continue
        for i, path in enumerate(paths):
            val = _dig(ev, path)
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                totals[i] += val
                seen[i] = True
    return (
        _as_int(totals[0]) if seen[0] else None,
        _as_int(totals[1]) if seen[1] else None,
        totals[2] if seen[2] else None,
    )


def _extract_fields(config: HarnessConfig, proc) -> tuple[str, int | None, int | None, float | None, int | None]:
    """Parse a finished harness process's stdout into (response, in_toks, out_toks, cost, tool_calls)."""
    if config.parse == "single-json":
        try:
            obj = json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            raise RuntimeError(
                f"{config.name}: expected single JSON on stdout (exit {proc.returncode}), "
                f"got unparseable output; stderr tail: {proc.stderr[-500:]!r}"
            ) from e
        response_text = _dig(obj, config.response_path)
        if response_text is None:
            raise RuntimeError(
                f"{config.name}: response path {config.response_path} missing from JSON output"
            )
        return (
            str(response_text),
            _as_int(_dig(obj, config.input_tokens_path)),
            _as_int(_dig(obj, config.output_tokens_path)),
            _as_float(_dig(obj, config.cost_path)),
            _as_int(_dig(obj, config.tool_call_count_path)),
        )
    events = _parse_jsonl(proc.stdout)
    if not events and proc.returncode != 0:
        raise RuntimeError(
            f"{config.name}: no JSONL events parsed and exit={proc.returncode}; "
            f"stderr tail: {proc.stderr[-500:]!r}"
        )
    if not events:
        raise RuntimeError(f"{config.name}: no JSONL events parsed from stdout")
    response_text = _find_last(events, config.response_path)
    if response_text is None:
        raise RuntimeError(
            f"{config.name}: response path {config.response_path} missing from JSONL events"
        )
    tool_call_count = (
        sum(1 for ev in events if ev.get("type") in config.tool_call_event_types) or None
        if config.tool_call_event_types
        else None
    )
    if config.sum_usage_event_types:
        input_tokens, output_tokens, cost_usd = _sum_metrics(
            events,
            config.sum_usage_event_types,
            (config.input_tokens_path, config.output_tokens_path, config.cost_path),
        )
    else:
        input_tokens = _as_int(_find_last(events, config.input_tokens_path))
        output_tokens = _as_int(_find_last(events, config.output_tokens_path))
        cost_usd = _as_float(_find_last(events, config.cost_path))
    return (
        str(response_text),
        input_tokens,
        output_tokens,
        cost_usd,
        tool_call_count,
    )


def run(config: HarnessConfig, sb: sandbox_mod.Sandbox, prompt: str, model: str | None = None) -> HarnessRunResult:
    argv = _build_argv(config, prompt, model)
    command_str = " ".join(shlex.quote(a) for a in argv)

    start = time.monotonic()
    proc = sandbox_mod.run(sb, command_str, timeout=config.timeout_seconds)
    elapsed = time.monotonic() - start

    response_text, input_tokens, output_tokens, cost_usd, tool_call_count = _extract_fields(config, proc)

    return HarnessRunResult(
        response_text=response_text if isinstance(response_text, str) else str(response_text),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
        tool_call_count=tool_call_count,
        wall_clock_seconds=elapsed,
        raw_exit_code=proc.returncode,
    )


def run_host_text(config: HarnessConfig, prompt: str, model: str | None = None) -> str:
    """Run a harness CLI once on the host (no sandbox, no metrics) and return
    its response text. Used by the judge ensemble -- grading needs one CLI call,
    not a benchmarked agent run."""
    argv = _build_argv(config, prompt, model)
    command_str = " ".join(shlex.quote(a) for a in argv)
    try:
        proc = subprocess.run(
            ["bash", "-lc", command_str], capture_output=True, text=True,
            timeout=config.timeout_seconds,
        )
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"{config.name}: judge call timed out after {config.timeout_seconds}s") from e
    response_text, _, _, _, _ = _extract_fields(config, proc)
    return response_text if isinstance(response_text, str) else str(response_text)


__all__ = ["HarnessRunResult", "harness_version", "run", "run_host_text"]
