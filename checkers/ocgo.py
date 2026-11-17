#!/usr/bin/env python3
"""
ocgo — OpenCode Go Provider Quota & Usage Monitor

  - Endpoint: GET https://opencode.ai/zen/go/v1/usage
  - Catalog:  GET https://opencode.ai/zen/go/v1/models
  - Credential source: ~/.local/share/opencode/auth.json ("opencode-go".key)
                       or env var OPENCODE_GO_KEY / OPENCODE_API_KEY
"""

import argparse
import datetime as dt
import json
import os
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import benchmark_common as bc
from benchmark_common import C_BOLD, C_RED, C_RESET

USAGE_URL = "https://opencode.ai/zen/go/v1/usage"
MODELS_URL = "https://opencode.ai/zen/go/v1/models"
DEFAULT_AUTH_FILE = Path.home() / ".local/share/opencode/auth.json"
_WINDOWS = (
    ("rolling", "5-Hour Rolling Window", "5-hour high-burst rate limit"),
    ("weekly", "Weekly Window", "7-day rolling allocation limit"),
    ("monthly", "Monthly Window", "30-day billing cycle quota"),
)


def resolve_api_key(explicit_key: str | None = None) -> tuple[str | None, str]:
    """Locate OpenCode Go API key from --key, env, or auth.json."""
    if explicit_key:
        return explicit_key.strip(), "argument (--key)"
    env_key = os.getenv("OPENCODE_GO_KEY") or os.getenv("OPENCODE_API_KEY")
    if env_key:
        return env_key.strip(), "environment variable"
    if not DEFAULT_AUTH_FILE.exists():
        return None, "not found"
    try:
        with open(DEFAULT_AUTH_FILE, encoding="utf-8") as f:
            key = json.load(f).get("opencode-go", {}).get("key")
    except Exception as e:
        return None, f"error reading {DEFAULT_AUTH_FILE}: {e}"
    return (key.strip(), str(DEFAULT_AUTH_FILE)) if key else (None, "not found")


def parse_iso_datetime(iso_str: str | None) -> dt.datetime | None:
    """Parse ISO-8601 timestamp into UTC-aware datetime."""
    return bc.parse_iso_utc(iso_str)


def format_relative_time(target: dt.datetime | None, now: dt.datetime | None = None) -> str:
    """Delegate naive/aware countdown formatting to shared benchmark_common helper."""
    return bc.format_relative_time(target, now)


def _fetch_json(url: str, api_key: str, timeout: int = 15) -> tuple[dict | None, str | None]:
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {api_key}", "User-Agent": "ocgo/1.0", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8")), None
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8")
            err_data = json.loads(body)
            msg = err_data.get("error", {}).get("message") or err_data.get("message") or body
        except Exception:
            msg = body or str(e)
        return None, f"HTTP {e.code} ({e.reason}): {msg}"
    except Exception as e:
        return None, f"Connection failed: {e}"


def fetch_usage(api_key: str, timeout: int = 15) -> tuple[dict | None, str | None]:
    return _fetch_json(USAGE_URL, api_key, timeout=timeout)


def fetch_models(api_key: str, timeout: int = 15) -> tuple[list[str] | None, str | None]:
    data, err = _fetch_json(MODELS_URL, api_key, timeout=timeout)
    if err or not isinstance(data, dict):
        return None, err
    return sorted(m["id"] for m in data.get("data", []) if "id" in m), None


def _render_window_lines(w_data: dict, name: str, desc: str, now: dt.datetime, color: bool) -> list[str]:
    c_b, c_d, c_w, c_g, c_r = (C_BOLD, bc.C_DIM, bc.C_WHITE, bc.C_GREEN, C_RESET) if color else ("", "", "", "", "")
    percent = bc._safe_float(w_data.get("percent"), 0.0, strip_currency=False)
    status = w_data.get("status") or "ok"
    resets_dt = parse_iso_datetime(w_data.get("resetsAt"))
    rel_time = format_relative_time(resets_dt, now)

    status_tag = (f"{c_g}OK{c_r}" if status == "ok" else f"{C_BOLD}{C_RED}RATE-LIMITED{c_r}") if color else status.upper()
    pct_col = bc.get_percent_color(percent) if color else ""
    pct_str = f"{pct_col}{percent:5.1f}%{c_r}"
    bar = bc.format_bar(percent, width=22, colorize=color)

    reset_info = f" · Reset time: {resets_dt.astimezone().strftime('%Y-%m-%d %H:%M %Z')}" if resets_dt else ""
    return [
        f"  {c_b}{name:<25}{c_r} [{status_tag}]",
        f"    Usage: {bar} {pct_str}   {c_d}Resets in:{c_r} {c_w}{rel_time}{c_r}",
        f"    {c_d}{desc}{reset_info}{c_r}",
        "",
    ]


def _render_models_section(models: list[str], box_w: int, mid_border: str, color: bool) -> list[str]:
    c_b, c_d, c_r = (C_BOLD, bc.C_DIM, C_RESET) if color else ("", "", "")
    cols = 3 if box_w >= 75 else 2
    chunk = (len(models) + cols - 1) // cols
    grid = [models[i * chunk : (i + 1) * chunk] for i in range(cols)]
    lines = [mid_border, f"  {c_b}Available Go Models ({len(models)} total):{c_r}"]
    for row in range(chunk):
        items = [f"{grid[c][row]:<26}" for c in range(cols) if row < len(grid[c])]
        lines.append(f"   {c_d}•{c_r} " + "  ".join(items))
    lines.append("")
    return lines


def render_dashboard(data: dict, auth_source: str, color: bool = True, models: list[str] | None = None) -> str:
    """Render Unicode/plain OpenCode Go quota dashboard."""
    usage = data.get("usage") or {}
    now = dt.datetime.now(dt.UTC)
    term_w = shutil.get_terminal_size((80, 24)).columns
    box_w = min(max(term_w - 4, 60), 84)
    out, mid_border, bot_border = bc.quota_box_chrome(
        "⚡ OPENCODE GO — PROVIDER QUOTA & USAGE RADAR",
        [f" Source: {auth_source}"],
        box_w,
        color,
    )
    for key, name, desc in _WINDOWS:
        out.extend(_render_window_lines(usage.get(key) or {}, name, desc, now, color))
    if models:
        out.extend(_render_models_section(models, box_w, mid_border, color))
    out.append(bot_border)
    return "\n".join(out)


def render_statusline(data: dict) -> str:
    """Render compact single-line OpenCode Go quota summary."""
    usage = data.get("usage") or {}
    now = dt.datetime.now(dt.UTC)
    rolling = usage.get("rolling") or {}
    weekly = usage.get("weekly") or {}
    monthly = usage.get("monthly") or {}

    r_pct = bc._safe_float(rolling.get("percent"), 0.0, strip_currency=False)
    w_pct = bc._safe_float(weekly.get("percent"), 0.0, strip_currency=False)
    m_pct = bc._safe_float(monthly.get("percent"), 0.0, strip_currency=False)
    m_rst = format_relative_time(parse_iso_datetime(monthly.get("resetsAt")), now)
    r_rst = format_relative_time(parse_iso_datetime(rolling.get("resetsAt")), now)
    return f"[OpenCode Go] 5h: {r_pct:.0f}% (rst {r_rst}) · wk: {w_pct:.0f}% · mo: {m_pct:.0f}% (rst {m_rst})"


def _print_missing_key_error(auth_source: str) -> None:
    detail = f"\n  Detail:   {auth_source}" if auth_source != "not found" else ""
    print(
        f"Error: OpenCode Go API key could not be located.{detail}\n"
        '  Expected: ~/.local/share/opencode/auth.json ("opencode-go".key)\n'
        "  Or set:   export OPENCODE_GO_KEY='your_key'\n"
        "  Login via: opencode auth login",
        file=sys.stderr,
    )


def main():
    parser = argparse.ArgumentParser(
        description="OpenCode Go Quota & Usage Monitor (Live telemetry via https://opencode.ai/zen/go/v1/usage)"
    )
    parser.add_argument("-j", "--json", action="store_true", help="Output raw JSON response to stdout")
    parser.add_argument("-s", "--statusline", "--short", action="store_true", help="Output single-line compact status")
    parser.add_argument("-m", "--models", action="store_true", help="Include active OpenCode Go models catalog")
    parser.add_argument("--key", type=str, default=None, help="Explicit API key (overrides auth.json and env)")
    parser.add_argument("--plain", "--no-color", action="store_true", help="Disable ANSI color codes")

    args = parser.parse_args()
    use_color = not (args.plain or not sys.stdout.isatty())
    api_key, auth_source = resolve_api_key(args.key)
    if not api_key:
        _print_missing_key_error(auth_source)
        sys.exit(1)

    data, err = fetch_usage(api_key)
    if err:
        print(f"Error fetching OpenCode Go quota: {err}", file=sys.stderr)
        sys.exit(1)

    models = fetch_models(api_key)[0] if args.models else None
    if args.json:
        payload = {"fetched_at": dt.datetime.now(dt.UTC).isoformat(), "auth_source": auth_source, **data}
        if models:
            payload["models"] = models
        print(json.dumps(payload, indent=2))
        return
    print(render_statusline(data) if args.statusline else render_dashboard(data, auth_source, color=use_color, models=models))


if __name__ == "__main__":
    main()
