#!/usr/bin/env python3
"""
ccgo — CommandCode Provider Quota, Credits & Usage Monitor

Reverse-engineered from open-source CommandCode repository:
  - Base URL: https://api.commandcode.ai
  - Endpoints:
      * GET /alpha/whoami
      * GET /alpha/billing/credits
      * GET /alpha/billing/subscriptions
      * GET /alpha/usage/summary
  - Credential source: ~/.commandcode/auth.json ("apiKey")
                       or env var COMMAND_CODE_API_KEY / CMD_API_KEY
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

API_BASE = "https://api.commandcode.ai"
DEFAULT_AUTH_FILE = Path.home() / ".commandcode/auth.json"

# Known plan names and monthly credit pools (from command-code harness spec)
KNOWN_PLANS = {
    "individual-go": "Individual Go",
    "individual-goat": "Individual GOAT",
    "individual-pro": "Individual Pro",
    "individual-pro-v1": "Individual Pro v1",
    "individual-provider": "Individual Provider",
    "individual-max": "Individual Max",
    "individual-ultra": "Individual Ultra",
    "teams-pro": "Teams Pro",
    "goat": "GOAT",
    "pro": "Pro",
    "free": "Free",
}

PLAN_MONTHLY_CAPS = {
    "individual-go": 10.0,
    "individual-goat": 70.0,
    "individual-pro": 30.0,
    "individual-pro-v1": 80.0,
    "individual-provider": 15.0,
    "individual-max": 150.0,
    "individual-ultra": 300.0,
    "teams-pro": 40.0,
    "goat": 70.0,
    "pro": 30.0,
}

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

    env_key = os.getenv("COMMAND_CODE_API_KEY") or os.getenv("CMD_API_KEY")
    if env_key:
        return env_key.strip(), "environment variable"

    if DEFAULT_AUTH_FILE.exists():
        try:
            with open(DEFAULT_AUTH_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                key = data.get("apiKey")
                if key:
                    return key.strip(), str(DEFAULT_AUTH_FILE)
        except Exception as e:
            return None, f"error reading {DEFAULT_AUTH_FILE}: {e}"

    return None, "not found"


def format_relative_seconds(total_seconds: int) -> str:
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


def format_relative_epoch_ms(epoch_ms: int | float | None, now_ms: float | None = None) -> str:
    if not epoch_ms:
        return "unknown"
    if now_ms is None:
        now_ms = dt.datetime.now(dt.timezone.utc).timestamp() * 1000.0
    diff_s = int((epoch_ms - now_ms) / 1000.0)
    return format_relative_seconds(diff_s)


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


def format_tokens(num: int | float | None) -> str:
    if num is None:
        return "0"
    num = float(num)
    if num >= 1_000_000_000:
        return f"{num / 1_000_000_000:.2f}B"
    if num >= 1_000_000:
        return f"{num / 1_000_000:.2f}M"
    if num >= 1_000:
        return f"{num / 1_000:.1f}k"
    return f"{num:,.0f}"


def api_get(endpoint: str, api_key: str, timeout: int = 15) -> tuple[dict | None, str | None]:
    url = f"{API_BASE}{endpoint}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "ccgo/1.0",
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
            msg = err_data.get("message") or err_data.get("error") or body
        except Exception:
            msg = body or str(e)
        return None, f"HTTP {e.code} ({e.reason}): {msg}"
    except Exception as e:
        return None, f"Connection failed: {e}"


def fetch_all_telemetry(api_key: str, timeout: int = 15) -> tuple[dict, list[str]]:
    import concurrent.futures

    endpoints = {
        "whoami": "/alpha/whoami",
        "credits": "/alpha/billing/credits",
        "subscriptions": "/alpha/billing/subscriptions",
        "summary": "/alpha/usage/summary",
    }
    results = {}
    errors = []

    def _worker(item):
        k, path = item
        return k, path, api_get(path, api_key, timeout=timeout)

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        for key, path, (data, err) in executor.map(_worker, endpoints.items()):
            if err:
                errors.append(f"{path}: {err}")
                results[key] = None
            else:
                results[key] = data

    return results, errors


def render_dashboard(telemetry: dict, auth_source: str, color: bool = True) -> str:
    now_utc = dt.datetime.now(dt.timezone.utc)
    now_ms = now_utc.timestamp() * 1000.0

    c_b = C_BOLD if color else ""
    c_d = C_DIM if color else ""
    c_w = C_WHITE if color else ""
    c_c = C_CYAN if color else ""
    c_g = C_GREEN if color else ""
    c_y = C_YELLOW if color else ""
    c_r = C_RESET if color else ""

    term_w = shutil.get_terminal_size((80, 24)).columns
    box_w = min(max(term_w - 4, 60), 84)

    title = "⚡ COMMANDCODE GOAT — PROVIDER QUOTA & USAGE RADAR"
    top_border = "┌" + "─" * (box_w - 2) + "┐" if color else "-" * box_w
    mid_border = "├" + "─" * (box_w - 2) + "┤" if color else "-" * box_w
    bot_border = "└" + "─" * (box_w - 2) + "┘" if color else "-" * box_w

    out = []
    out.append(f"{c_d}{top_border}{c_r}")
    title_line = f" {c_b}{c_c}{title}{c_r}"
    padding = box_w - 2 - len(title) - 1
    out.append(f"{c_d}│{c_r}{title_line}{' ' * max(0, padding)}{c_d}│{c_r}" if color else f"| {title}")

    # Identity block
    whoami = telemetry.get("whoami") or {}
    user = whoami.get("user") or {}
    user_name = user.get("name") or user.get("userName") or "Unknown"
    user_login = user.get("userName") or ""
    login_suffix = f" (@{user_login})" if user_login else ""
    auth_str = f" User: {user_name}{login_suffix} · Source: {auth_source}"
    if len(auth_str) > box_w - 4:
        auth_str = auth_str[: box_w - 7] + "..."
    auth_pad = box_w - 2 - len(auth_str)
    out.append(f"{c_d}│{c_r}{c_d}{auth_str}{c_r}{' ' * max(0, auth_pad)}{c_d}│{c_r}" if color else f"|{auth_str}")

    # Subscription block
    sub = (telemetry.get("subscriptions") or {}).get("data") or {}
    raw_plan = sub.get("planId") or "unknown"
    plan_name = KNOWN_PLANS.get(raw_plan.lower(), raw_plan.title())
    status = sub.get("status") or "active"
    status_str = f"{c_g}{status.upper()}{c_r}" if status == "active" else f"{C_RED}{status.upper()}{c_r}"
    if not color:
        status_str = status.upper()

    period_end_raw = sub.get("currentPeriodEnd")
    days_left = ""
    if period_end_raw:
        try:
            end_dt = dt.datetime.fromisoformat(period_end_raw.replace("Z", "+00:00"))
            delta = end_dt - now_utc
            d_remain = max(0, delta.days)
            days_left = f" · {d_remain}d remaining in cycle"
        except Exception:
            pass

    out.append(f"{c_d}{mid_border}{c_r}")
    plan_line = f"  Plan: {c_b}{plan_name}{c_r} [{status_str}]{c_d}{days_left}{c_r}"
    out.append(plan_line)

    # Credits block
    credits_obj = (telemetry.get("credits") or {}).get("credits") or {}
    monthly_rem = float(credits_obj.get("monthlyCredits") or 0.0)
    purchased_rem = float(credits_obj.get("purchasedCredits") or 0.0)
    free_rem = float(credits_obj.get("freeCredits") or 0.0)
    total_balance = monthly_rem + purchased_rem + free_rem

    summary = telemetry.get("summary") or {}
    total_cost = float(summary.get("totalCost") or 0.0)

    out.append(f"{c_d}{mid_border}{c_r}")
    out.append(f"  {c_b}Credits & Balances:{c_r}")
    out.append(f"    Monthly Remaining:  {c_g}${monthly_rem:.2f}{c_r} (active billing pool)")
    if purchased_rem > 0 or free_rem > 0:
        out.append(f"    Purchased Credits:  {c_c}${purchased_rem:.2f}{c_r}")
        out.append(f"    Free Credits:       {c_c}${free_rem:.2f}{c_r}")
    out.append(f"    Total Balance:      {c_b}${total_balance:.2f}{c_r}")
    out.append(f"    Period Spend:       {c_d}${total_cost:.2f}{c_r}")
    out.append("")

    # Monthly Quota calculation
    monthly_cap = PLAN_MONTHLY_CAPS.get(raw_plan.lower(), 70.0)
    if monthly_rem + total_cost > monthly_cap:
        monthly_cap = monthly_rem + total_cost

    monthly_used = total_cost if total_cost > 0 else max(0.0, monthly_cap - monthly_rem)
    monthly_pct = (monthly_used / monthly_cap * 100.0) if monthly_cap > 0 else 0.0
    monthly_pct = min(100.0, max(0.0, monthly_pct))

    monthly_rst = "unknown"
    monthly_reset_date = ""
    if period_end_raw:
        try:
            end_dt = dt.datetime.fromisoformat(period_end_raw.replace("Z", "+00:00"))
            delta = end_dt - now_utc
            monthly_rst = format_relative_seconds(int(delta.total_seconds()))
            monthly_reset_date = f" · Reset: {end_dt.astimezone().strftime('%Y-%m-%d %H:%M %Z')}"
        except Exception:
            pass

    monthly_bar = format_bar(monthly_pct, width=22, colorize=color)
    monthly_pct_color = get_percent_color(monthly_pct) if color else ""
    monthly_status = f"{c_g}OK{c_r}" if monthly_rem > 0 and monthly_used < monthly_cap else f"{C_BOLD}{C_RED}EXCEEDED{c_r}"
    if not color:
        monthly_status = "EXCEEDED" if monthly_rem <= 0 or monthly_used >= monthly_cap else "OK"

    # Window Limits block
    window_limits = (telemetry.get("credits") or {}).get("windowLimits") or {}
    five_hour = window_limits.get("fiveHour") or {}
    weekly = window_limits.get("weekly") or {}

    out.append(f"  {c_b}Pooled Rate Limit Windows & Monthly Quota:{c_r}")

    # 5-Hour
    h5_used = float(five_hour.get("used") or 0.0)
    h5_cap = float(five_hour.get("cap") or 14.0)
    h5_pct = (h5_used / h5_cap * 100.0) if h5_cap > 0 else 0.0
    h5_rst = format_relative_epoch_ms(five_hour.get("resetAt"), now_ms)
    h5_bar = format_bar(h5_pct, width=22, colorize=color)
    h5_pct_color = get_percent_color(h5_pct) if color else ""
    h5_status = f"{c_g}OK{c_r}" if not five_hour.get("exceeded") else f"{C_BOLD}{C_RED}EXCEEDED{c_r}"
    if not color:
        h5_status = "EXCEEDED" if five_hour.get("exceeded") else "OK"

    out.append(f"    {c_b}5-Hour Window{c_r} [{h5_status}]")
    out.append(f"      Used: {h5_bar} {h5_pct_color}{h5_pct:5.1f}%{c_r} (${h5_used:.2f} / ${h5_cap:.2f})")
    out.append(f"      Resets in: {c_w}{h5_rst}{c_r}")

    # Weekly
    wk_used = float(weekly.get("used") or 0.0)
    wk_cap = float(weekly.get("cap") or 35.0)
    wk_pct = (wk_used / wk_cap * 100.0) if wk_cap > 0 else 0.0
    wk_rst = format_relative_epoch_ms(weekly.get("resetAt"), now_ms)
    wk_bar = format_bar(wk_pct, width=22, colorize=color)
    wk_pct_color = get_percent_color(wk_pct) if color else ""
    wk_status = f"{c_g}OK{c_r}" if not weekly.get("exceeded") else f"{C_BOLD}{C_RED}EXCEEDED{c_r}"
    if not color:
        wk_status = "EXCEEDED" if weekly.get("exceeded") else "OK"

    out.append(f"    {c_b}Weekly Window{c_r} [{wk_status}]")
    out.append(f"      Used: {wk_bar} {wk_pct_color}{wk_pct:5.1f}%{c_r} (${wk_used:.2f} / ${wk_cap:.2f})")
    out.append(f"      Resets in: {c_w}{wk_rst}{c_r}")

    # Monthly Quota
    out.append(f"    {c_b}Monthly Quota{c_r} [{monthly_status}]")
    out.append(f"      Used: {monthly_bar} {monthly_pct_color}{monthly_pct:5.1f}%{c_r} (${monthly_used:.2f} / ${monthly_cap:.2f} · {c_g}${monthly_rem:.2f} left{c_r})")
    out.append(f"      Resets in: {c_w}{monthly_rst}{c_r}{c_d}{monthly_reset_date}{c_r}")
    out.append("")

    # Usage Summary
    if summary:
        out.append(f"{c_d}{mid_border}{c_r}")
        total_reqs = summary.get("totalCount") or 0
        success_rate = float(summary.get("successRate") or 100.0)
        tokens_tot = summary.get("totalTokens") or 0
        tokens_in = summary.get("totalTokensIn") or 0
        tokens_out = summary.get("totalTokensOut") or 0
        avg_cost = float(summary.get("averageCost") or 0.0)

        out.append(f"  {c_b}Billing Cycle Telemetry Summary:{c_r}")
        out.append(f"    Requests:    {c_w}{total_reqs:,}{c_r}  (Success: {c_g}{success_rate:.2f}%{c_r})")
        out.append(f"    Tokens:      {c_w}{format_tokens(tokens_tot)}{c_r}  (In: {format_tokens(tokens_in)} · Out: {format_tokens(tokens_out)})")
        out.append(f"    Avg Cost:    ${avg_cost:.4f} / req")
        out.append("")

    out.append(f"{c_d}{bot_border}{c_r}")
    return "\n".join(out)


def render_statusline(telemetry: dict) -> str:
    now_utc = dt.datetime.now(dt.timezone.utc)
    now_ms = now_utc.timestamp() * 1000.0
    sub = (telemetry.get("subscriptions") or {}).get("data") or {}
    raw_plan = sub.get("planId") or "goat"
    plan_name = KNOWN_PLANS.get(raw_plan.lower(), raw_plan.title())

    credits_obj = (telemetry.get("credits") or {}).get("credits") or {}
    monthly_rem = float(credits_obj.get("monthlyCredits") or 0.0)

    summary = telemetry.get("summary") or {}
    total_cost = float(summary.get("totalCost") or 0.0)

    monthly_cap = PLAN_MONTHLY_CAPS.get(raw_plan.lower(), 70.0)
    if monthly_rem + total_cost > monthly_cap:
        monthly_cap = monthly_rem + total_cost

    monthly_used = total_cost if total_cost > 0 else max(0.0, monthly_cap - monthly_rem)
    monthly_pct = (monthly_used / monthly_cap * 100.0) if monthly_cap > 0 else 0.0
    monthly_pct = min(100.0, max(0.0, monthly_pct))

    period_end_raw = sub.get("currentPeriodEnd")
    monthly_rst = "unknown"
    if period_end_raw:
        try:
            end_dt = dt.datetime.fromisoformat(period_end_raw.replace("Z", "+00:00"))
            delta = end_dt - now_utc
            monthly_rst = format_relative_seconds(int(delta.total_seconds()))
        except Exception:
            pass

    window_limits = (telemetry.get("credits") or {}).get("windowLimits") or {}
    five_hour = window_limits.get("fiveHour") or {}
    weekly = window_limits.get("weekly") or {}

    h5_used = float(five_hour.get("used") or 0.0)
    h5_cap = float(five_hour.get("cap") or 14.0)
    h5_pct = (h5_used / h5_cap * 100.0) if h5_cap > 0 else 0.0

    wk_used = float(weekly.get("used") or 0.0)
    wk_cap = float(weekly.get("cap") or 35.0)
    wk_pct = (wk_used / wk_cap * 100.0) if wk_cap > 0 else 0.0

    h5_rst = format_relative_epoch_ms(five_hour.get("resetAt"), now_ms)

    return (
        f"[CommandCode {plan_name}] "
        f"5h: ${h5_used:.2f}/{h5_cap:.0f} ({h5_pct:.0f}%, rst {h5_rst}) · "
        f"wk: ${wk_used:.2f}/{wk_cap:.0f} ({wk_pct:.0f}%) · "
        f"mo: ${monthly_used:.2f}/{monthly_cap:.0f} ({monthly_pct:.0f}%, ${monthly_rem:.2f} left, rst {monthly_rst})"
    )


def main():
    parser = argparse.ArgumentParser(
        description="CommandCode Quota & Usage Monitor (Live telemetry via https://api.commandcode.ai)"
    )
    parser.add_argument("-j", "--json", action="store_true", help="Output combined raw JSON response to stdout")
    parser.add_argument("-s", "--statusline", "--short", action="store_true", help="Output single-line compact status")
    parser.add_argument("--key", type=str, default=None, help="Explicit API key (overrides auth.json and env)")
    parser.add_argument("--plain", "--no-color", action="store_true", help="Disable ANSI color codes")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose error output")

    args = parser.parse_args()
    use_color = not (args.plain or not sys.stdout.isatty())

    api_key, auth_source = resolve_api_key(args.key)
    if not api_key:
        err_msg = (
            f"Error: CommandCode API key could not be located.\n"
            f"  Expected: ~/.commandcode/auth.json (\"apiKey\")\n"
            f"  Or set:   export COMMAND_CODE_API_KEY='your_key'\n"
            f"  Login via: commandcode auth login"
        )
        print(err_msg, file=sys.stderr)
        sys.exit(1)

    telemetry, errors = fetch_all_telemetry(api_key)
    if not telemetry.get("credits") and not telemetry.get("subscriptions"):
        err_str = "; ".join(errors) if errors else "No data returned"
        print(f"Error fetching CommandCode telemetry: {err_str}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        sub = (telemetry.get("subscriptions") or {}).get("data") or {}
        raw_plan = sub.get("planId") or "goat"
        credits_obj = (telemetry.get("credits") or {}).get("credits") or {}
        monthly_rem = float(credits_obj.get("monthlyCredits") or 0.0)
        summary = telemetry.get("summary") or {}
        total_cost = float(summary.get("totalCost") or 0.0)
        monthly_cap = PLAN_MONTHLY_CAPS.get(raw_plan.lower(), 70.0)
        if monthly_rem + total_cost > monthly_cap:
            monthly_cap = monthly_rem + total_cost
        monthly_used = total_cost if total_cost > 0 else max(0.0, monthly_cap - monthly_rem)
        monthly_pct = (monthly_used / monthly_cap * 100.0) if monthly_cap > 0 else 0.0

        monthly_quota = {
            "used": round(monthly_used, 4),
            "cap": round(monthly_cap, 2),
            "remaining": round(monthly_rem, 4),
            "percent": round(monthly_pct, 2),
            "periodStart": sub.get("currentPeriodStart"),
            "periodEnd": sub.get("currentPeriodEnd"),
        }

        payload = {
            "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "auth_source": auth_source,
            "monthly_quota": monthly_quota,
            "errors": errors if errors else None,
            **telemetry,
        }
        print(json.dumps(payload, indent=2))
        return

    if args.statusline:
        print(render_statusline(telemetry))
        return

    print(render_dashboard(telemetry, auth_source, color=use_color))


if __name__ == "__main__":
    main()
