#!/usr/bin/env python3
"""
ocgo — OpenCode Go Provider Quota & Usage Monitor

Reverse-engineered from open-source OpenCode repository:
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

USAGE_URL = "https://opencode.ai/zen/go/v1/usage"
MODELS_URL = "https://opencode.ai/zen/go/v1/models"
DEFAULT_AUTH_FILE = Path.home() / ".local/share/opencode/auth.json"

# ANSI color codes
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_DIM = "\033[2m"
C_GREEN = "\033[32m"
C_YELLOW = "\033[33m"
C_RED = "\033[31m"
C_CYAN = "\033[36m"
C_MAGENTA = "\033[35m"
C_WHITE = "\033[37m"
C_GRAY = "\033[90m"


def resolve_api_key(explicit_key: str | None = None) -> tuple[str | None, str]:
    if explicit_key:
        return explicit_key.strip(), "argument (--key)"

    env_key = os.getenv("OPENCODE_GO_KEY") or os.getenv("OPENCODE_API_KEY")
    if env_key:
        return env_key.strip(), "environment variable"

    if DEFAULT_AUTH_FILE.exists():
        try:
            with open(DEFAULT_AUTH_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                key = data.get("opencode-go", {}).get("key")
                if key:
                    return key.strip(), str(DEFAULT_AUTH_FILE)
        except Exception as e:
            return None, f"error reading {DEFAULT_AUTH_FILE}: {e}"

    return None, "not found"


def parse_iso_datetime(iso_str: str | None) -> dt.datetime | None:
    if not iso_str:
        return None
    cleaned = iso_str.replace("Z", "+00:00")
    try:
        return dt.datetime.fromisoformat(cleaned)
    except Exception:
        return None


def format_relative_time(target: dt.datetime | None, now: dt.datetime | None = None) -> str:
    if not target:
        return "unknown"
    if now is None:
        now = dt.datetime.now(dt.timezone.utc)
    delta = target - now
    total_seconds = int(delta.total_seconds())
    if total_seconds <= 0:
        return "now"

    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600) // 60

    if days > 0:
        return f"{days}d {hours}h" if hours > 0 else f"{days}d"
    if hours > 0:
        return f"{hours}h {minutes}m" if minutes > 0 else f"{hours}h"
    return f"{minutes}m"


def format_bar(percent: float, width: int = 20, colorize: bool = True) -> str:
    percent = max(0.0, min(100.0, percent))
    filled_len = int(round((percent / 100.0) * width))
    empty_len = width - filled_len
    bar = "█" * filled_len + "░" * empty_len

    if not colorize:
        return f"[{bar}]"

    if percent >= 90.0:
        bar_color = C_BOLD + C_RED
    elif percent >= 70.0:
        bar_color = C_YELLOW
    elif percent >= 40.0:
        bar_color = C_CYAN
    else:
        bar_color = C_GREEN

    return f"{bar_color}[{bar}]{C_RESET}"


def get_percent_color(percent: float) -> str:
    if percent >= 90.0:
        return C_BOLD + C_RED
    if percent >= 70.0:
        return C_YELLOW
    if percent >= 40.0:
        return C_CYAN
    return C_GREEN


def fetch_usage(api_key: str, timeout: int = 15) -> tuple[dict | None, str | None]:
    req = urllib.request.Request(
        USAGE_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "ocgo/1.0",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data, None
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


def fetch_models(api_key: str, timeout: int = 15) -> tuple[list[str] | None, str | None]:
    req = urllib.request.Request(
        MODELS_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "ocgo/1.0",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = [m["id"] for m in data.get("data", []) if "id" in m]
            return sorted(models), None
    except Exception as e:
        return None, str(e)


def render_dashboard(data: dict, auth_source: str, color: bool = True, models: list[str] | None = None) -> str:
    usage = data.get("usage", {})
    now = dt.datetime.now(dt.timezone.utc)
    out = []

    c_b = C_BOLD if color else ""
    c_d = C_DIM if color else ""
    c_w = C_WHITE if color else ""
    c_c = C_CYAN if color else ""
    c_g = C_GREEN if color else ""
    c_r = C_RESET if color else ""

    term_w = shutil.get_terminal_size((80, 24)).columns
    box_w = min(max(term_w - 4, 60), 84)

    title = "⚡ OPENCODE GO — PROVIDER QUOTA & USAGE RADAR"
    top_border = "┌" + "─" * (box_w - 2) + "┐" if color else "-" * box_w
    mid_border = "├" + "─" * (box_w - 2) + "┤" if color else "-" * box_w
    bot_border = "└" + "─" * (box_w - 2) + "┘" if color else "-" * box_w

    out.append(f"{c_d}{top_border}{c_r}")
    title_line = f" {c_b}{c_c}{title}{c_r}"
    padding = box_w - 2 - len(title) - 1
    out.append(f"{c_d}│{c_r}{title_line}{' ' * max(0, padding)}{c_d}│{c_r}" if color else f"| {title}")
    
    auth_str = f" Source: {auth_source}"
    if len(auth_str) > box_w - 4:
        auth_str = auth_str[: box_w - 7] + "..."
    auth_pad = box_w - 2 - len(auth_str)
    out.append(f"{c_d}│{c_r}{c_d}{auth_str}{c_r}{' ' * max(0, auth_pad)}{c_d}│{c_r}" if color else f"|{auth_str}")
    out.append(f"{c_d}{mid_border}{c_r}")

    windows = [
        ("rolling", "5-Hour Rolling Window", "5-hour high-burst rate limit"),
        ("weekly", "Weekly Window", "7-day rolling allocation limit"),
        ("monthly", "Monthly Window", "30-day billing cycle quota"),
    ]

    for key, name, desc in windows:
        w_data = usage.get(key, {})
        percent = float(w_data.get("percent", 0))
        status = w_data.get("status", "ok")
        resets_at_raw = w_data.get("resetsAt")
        resets_dt = parse_iso_datetime(resets_at_raw)
        rel_time = format_relative_time(resets_dt, now)

        status_tag = f"{c_g}OK{c_r}" if status == "ok" else f"{C_BOLD}{C_RED}RATE-LIMITED{c_r}"
        if not color:
            status_tag = status.upper()

        pct_color = get_percent_color(percent) if color else ""
        pct_str = f"{pct_color}{percent:5.1f}%{c_r}"
        bar = format_bar(percent, width=22, colorize=color)

        line1 = f"  {c_b}{name:<25}{c_r} [{status_tag}]"
        line2 = f"    Usage: {bar} {pct_str}   {c_d}Resets in:{c_r} {c_w}{rel_time}{c_r}"
        if resets_dt:
            local_dt = resets_dt.astimezone()
            line3 = f"    {c_d}{desc} · Reset time: {local_dt.strftime('%Y-%m-%d %H:%M %Z')}{c_r}"
        else:
            line3 = f"    {c_d}{desc}{c_r}"

        out.append(line1)
        out.append(line2)
        out.append(line3)
        out.append("")

    if models:
        out.append(f"{c_d}{mid_border}{c_r}")
        out.append(f"  {c_b}Available Go Models ({len(models)} total):{c_r}")
        cols = 3 if box_w >= 75 else 2
        chunk_size = (len(models) + cols - 1) // cols
        grid = [models[i * chunk_size : (i + 1) * chunk_size] for i in range(cols)]
        for row in range(chunk_size):
            row_items = []
            for c in range(cols):
                if row < len(grid[c]):
                    row_items.append(f"{grid[c][row]:<26}")
            out.append(f"   {c_d}•{c_r} " + "  ".join(row_items))
        out.append("")

    out.append(f"{c_d}{bot_border}{c_r}")
    return "\n".join(out)


def render_statusline(data: dict) -> str:
    usage = data.get("usage", {})
    now = dt.datetime.now(dt.timezone.utc)

    rolling = usage.get("rolling", {})
    weekly = usage.get("weekly", {})
    monthly = usage.get("monthly", {})

    r_pct = rolling.get("percent", 0)
    w_pct = weekly.get("percent", 0)
    m_pct = monthly.get("percent", 0)

    m_rst = format_relative_time(parse_iso_datetime(monthly.get("resetsAt")), now)
    r_rst = format_relative_time(parse_iso_datetime(rolling.get("resetsAt")), now)

    return f"[OpenCode Go] 5h: {r_pct:.0f}% (rst {r_rst}) · wk: {w_pct:.0f}% · mo: {m_pct:.0f}% (rst {m_rst})"


def main():
    parser = argparse.ArgumentParser(
        description="OpenCode Go Quota & Usage Monitor (Live telemetry via https://opencode.ai/zen/go/v1/usage)"
    )
    parser.add_argument("-j", "--json", action="store_true", help="Output raw JSON response to stdout")
    parser.add_argument("-s", "--statusline", "--short", action="store_true", help="Output single-line compact status")
    parser.add_argument("-m", "--models", action="store_true", help="Include active OpenCode Go models catalog")
    parser.add_argument("--key", type=str, default=None, help="Explicit API key (overrides auth.json and env)")
    parser.add_argument("--plain", "--no-color", action="store_true", help="Disable ANSI color codes")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose error output")

    args = parser.parse_args()
    use_color = not (args.plain or not sys.stdout.isatty())

    api_key, auth_source = resolve_api_key(args.key)
    if not api_key:
        err_msg = (
            f"Error: OpenCode Go API key could not be located.\n"
            f"  Expected: ~/.local/share/opencode/auth.json (\"opencode-go\".key)\n"
            f"  Or set:   export OPENCODE_GO_KEY='your_key'\n"
            f"  Login via: opencode auth login"
        )
        print(err_msg, file=sys.stderr)
        sys.exit(1)

    data, err = fetch_usage(api_key)
    if err:
        print(f"Error fetching OpenCode Go quota: {err}", file=sys.stderr)
        sys.exit(1)

    models = None
    if args.models:
        models, _ = fetch_models(api_key)

    if args.json:
        payload = {
            "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "auth_source": auth_source,
            **data,
        }
        if models:
            payload["models"] = models
        print(json.dumps(payload, indent=2))
        return

    if args.statusline:
        print(render_statusline(data))
        return

    print(render_dashboard(data, auth_source, color=use_color, models=models))


if __name__ == "__main__":
    main()
