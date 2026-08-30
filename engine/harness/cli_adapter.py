"""Generic adapter driving any HarnessConfig: run its CLI in the sandbox, parse
its own JSON/JSONL output for response text + tokens + cost + tool-call-count.

One class, five configs (configs.py) -- not five bespoke adapters.
"""
from __future__ import annotations

import json
import shlex
import threading
import time
from dataclasses import dataclass

from .. import sandbox as sandbox_mod
from .configs import HarnessConfig

_VERSION_CACHE: dict[str, str] = {}
_VERSION_LOCK = threading.Lock()


class UsageExtractionError(RuntimeError):
    """A harness run produced no trustworthy metrics: either a *configured*
    usage/cost path extracted nothing from an otherwise successful run
    (field-map drift, not a free run — recording None lets cost aggregates
    read as $0.00), or the run timed out (exit 124) and its truncated
    output must not be scored at all. cmd_run counts the trial errored
    instead."""


def _require_extracted(
    config: HarnessConfig, proc, extracted: list[tuple[str, list[str] | None, object]]
) -> None:
    """Fail loud on configured-but-missing metrics, mirroring the
    response-path rule in _extract_fields."""
    if proc.returncode != 0:
        return  # crashed/truncated run: partial metrics are a separate issue
    missing = [f"{name} path {path}" for name, path, value in extracted
               if path is not None and value is None]
    if missing:
        raise UsageExtractionError(
            f"{config.name}: harness succeeded but no value at configured "
            + "; ".join(missing)
        )


def harness_version(config: HarnessConfig, sb: sandbox_mod.Sandbox) -> str:
    """Version of the CLI as it runs INSIDE the sandbox image, cached once
    per harness per session.

    Capture must be in-container: the record has to attribute the version
    that actually ran (metrics.md), and the host may carry a different CLI
    — or none at all (codex resolved to the bare name host-side while the
    image had it). The bare-name fallback is a loud WARN: an unpinned
    version invalidates comparison over time."""
    with _VERSION_LOCK:
        if config.name in _VERSION_CACHE:
            return _VERSION_CACHE[config.name]
        version = None
        cmd = shlex.join(config.version_argv) if config.version_argv else None
        if cmd:
            try:
                # --version is pure-local: no egress, short bound; a CLI
                # that hangs or misses degrades to the WARN below.
                proc = sandbox_mod.exec_in(sb, cmd, timeout=60, network=False)
                if proc.returncode == 0 and proc.stdout.strip():
                    version = proc.stdout.strip().splitlines()[0]
            except OSError as e:
                # docker client missing/daemon dead
                print(f"bench: WARN harness_version({config.name}): {type(e).__name__}: {e}")
        if version is None:
            print(
                f"bench: WARN harness_version({config.name}): could not capture "
                f"{cmd!r} in-container; recording the bare harness name — this "
                "run has an UNPINNED version and is not comparable over time "
                "(metrics.md layer attribution)"
            )
            version = config.name
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
        extracted = (
            _as_int(_dig(obj, config.input_tokens_path)),
            _as_int(_dig(obj, config.output_tokens_path)),
            _as_float(_dig(obj, config.cost_path)),
            _as_int(_dig(obj, config.tool_call_count_path)),
        )
        _require_extracted(config, proc, [
            ("input_tokens", config.input_tokens_path, extracted[0]),
            ("output_tokens", config.output_tokens_path, extracted[1]),
            ("cost", config.cost_path, extracted[2]),
            ("tool_call_count", config.tool_call_count_path, extracted[3]),
        ])
        return (str(response_text), *extracted)
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
    _require_extracted(config, proc, [
        ("input_tokens", config.input_tokens_path, input_tokens),
        ("output_tokens", config.output_tokens_path, output_tokens),
        ("cost", config.cost_path, cost_usd),
        # tool_call_count here comes from event-type counting, not a json
        # path: a legitimate zero-tool-call run must not look like drift.
        ("tool_call_count", None, tool_call_count),
    ])
    return (str(response_text), input_tokens, output_tokens, cost_usd, tool_call_count)


def run(config: HarnessConfig, sb: sandbox_mod.Sandbox, prompt: str, model: str | None = None) -> HarnessRunResult:
    argv = _build_argv(config, prompt, model)
    command_str = " ".join(shlex.quote(a) for a in argv)

    start = time.monotonic()
    proc = sandbox_mod.run(sb, command_str, timeout=config.timeout_seconds)
    elapsed = time.monotonic() - start

    if proc.returncode == 124:
        # sandbox.run's timeout convention carries PARTIAL stdout: parsing
        # truncated JSONL would mint a clean-looking trial with
        # undercounted tokens/cost. Honor the exit code instead — error it.
        raise UsageExtractionError(
            f"{config.name}: harness timed out after {config.timeout_seconds}s "
            f"(exit 124); truncated output is not scorable"
        )

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

__all__ = ["HarnessRunResult", "UsageExtractionError", "harness_version", "run"]
