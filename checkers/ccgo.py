#!/usr/bin/env python3
"""
ccgo — CommandCode Provider Quota, Credits & Usage Monitor

  - Base URL: https://api.commandcode.ai
      * GET /alpha/whoami
      * GET /alpha/billing/credits
      * GET /alpha/billing/subscriptions
      * GET /alpha/usage/summary
  - Credential source: ~/.commandcode/auth.json ("apiKey")
                       or env var COMMAND_CODE_API_KEY / CMD_API_KEY
"""

import argparse
import concurrent.futures
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

API_BASE = "https://api.commandcode.ai"
DEFAULT_AUTH_FILE = Path.home() / ".commandcode/auth.json"

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
    "free": 0.0,
}


def resolve_api_key(explicit_key: str | None = None) -> tuple[str | None, str]:
    """Locate CommandCode API key from --key, env, or auth.json."""
    if explicit_key:
        return explicit_key.strip(), "argument (--key)"
    env_key = os.getenv("COMMAND_CODE_API_KEY") or os.getenv("CMD_API_KEY")
    if env_key:
        return env_key.strip(), "environment variable"
    if not DEFAULT_AUTH_FILE.exists():
        return None, "not found"
    try:
        with open(DEFAULT_AUTH_FILE, encoding="utf-8") as f:
            key = json.load(f).get("apiKey")
    except Exception as e:
        return None, f"error reading {DEFAULT_AUTH_FILE}: {e}"
    return (key.strip(), str(DEFAULT_AUTH_FILE)) if key else (None, "not found")


def format_tokens(num: int | float | None) -> str:
    """Format token count cleanly (B/M/k)."""
    if not bc._is_num(num):
        return "0"
    n = float(num)
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.2f}B"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return f"{n:,.0f}"


def api_get(endpoint: str, api_key: str, timeout: int = 15) -> tuple[dict | None, str | None]:
    req = urllib.request.Request(
        f"{API_BASE}{endpoint}",
        headers={"Authorization": f"Bearer {api_key}", "User-Agent": "ccgo/1.0", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8")), None
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
    endpoints = {
        "whoami": "/alpha/whoami",
        "credits": "/alpha/billing/credits",
        "subscriptions": "/alpha/billing/subscriptions",
        "summary": "/alpha/usage/summary",
    }
    results, errors = {}, []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        for key, path, (data, err) in executor.map(lambda it: (it[0], it[1], api_get(it[1], api_key, timeout)), endpoints.items()):
            if err:
                errors.append(f"{path}: {err}")
                results[key] = None
            else:
                results[key] = data
    return results, errors


def _monthly_usage_math(raw_plan: str, monthly_rem: float, total_cost: float) -> tuple[float, float, float, bool]:
    cap = PLAN_MONTHLY_CAPS.get(raw_plan, 70.0)
    if monthly_rem + total_cost > cap:
        cap = monthly_rem + total_cost
    used = total_cost if total_cost > 0 else max(0.0, cap - monthly_rem)
    raw_pct = (used / cap * 100.0) if cap > 0 else 0.0
    pct = min(100.0, max(0.0, raw_pct))
    exceeded = cap > 0 and (monthly_rem <= 0 or used >= cap)
    return cap, used, pct, exceeded


def compute_monthly_quota(telemetry: dict, now_utc: dt.datetime | None = None) -> dict:
    """Single source of truth for plan cap, usage, clamp [0..100], and reset countdown."""
    now_utc = now_utc or dt.datetime.now(dt.UTC)
    sub = (telemetry.get("subscriptions") or {}).get("data") or {}
    raw_plan = (sub.get("planId") or "unknown").lower()
    credits_obj = (telemetry.get("credits") or {}).get("credits") or {}
    monthly_rem = bc._safe_float(credits_obj.get("monthlyCredits"), 0.0, strip_currency=False)
    purchased_rem = bc._safe_float(credits_obj.get("purchasedCredits"), 0.0, strip_currency=False)
    free_rem = bc._safe_float(credits_obj.get("freeCredits"), 0.0, strip_currency=False)
    total_cost = bc._safe_float((telemetry.get("summary") or {}).get("totalCost"), 0.0, strip_currency=False)

    cap, used, pct, exceeded = _monthly_usage_math(raw_plan, monthly_rem, total_cost)
    end_dt = bc.parse_iso_utc(sub.get("currentPeriodEnd"))
    return {
        "raw_plan": raw_plan,
        "plan_name": KNOWN_PLANS.get(raw_plan, raw_plan.title()),
        "status": sub.get("status") or "active",
        "monthly_rem": monthly_rem,
        "purchased_rem": purchased_rem,
        "free_rem": free_rem,
        "total_balance": monthly_rem + purchased_rem + free_rem,
        "total_cost": total_cost,
        "cap": cap,
        "used": used,
        "percent": pct,
        "exceeded": exceeded,
        "days_remain": max(0, (end_dt - now_utc).days) if end_dt else None,
        "reset_rel": bc.format_relative_time(end_dt, now_utc),
        "end_dt": end_dt,
        "period_start": sub.get("currentPeriodStart"),
        "period_end": sub.get("currentPeriodEnd"),
    }


def _identity_subtitle(telemetry: dict, auth_source: str) -> str:
    user = (telemetry.get("whoami") or {}).get("user") or {}
    user_name = user.get("name") or user.get("userName") or "Unknown"
    user_login = user.get("userName") or ""
    suffix = f" (@{user_login})" if user_login else ""
    return f" User: {user_name}{suffix} · Source: {auth_source}"


def _window_block_lines(label: str, used: float, cap: float, exceeded: bool, reset_str: str, color: bool) -> list[str]:
    c_b, c_g, c_w, c_r = (C_BOLD, bc.C_GREEN, bc.C_WHITE, C_RESET) if color else ("", "", "", "")
    pct = (used / cap * 100.0) if cap > 0 else 0.0
    bar = bc.format_bar(pct, width=22, colorize=color)
    pct_col = bc.get_percent_color(pct) if color else ""
    st = ("EXCEEDED" if exceeded else "OK") if not color else (f"{C_BOLD}{C_RED}EXCEEDED{c_r}" if exceeded else f"{c_g}OK{c_r}")
    return [
        f"    {c_b}{label}{c_r} [{st}]",
        f"      Used: {bar} {pct_col}{pct:5.1f}%{c_r} (${used:.2f} / ${cap:.2f})",
        f"      Resets in: {c_w}{reset_str}{c_r}",
    ]


def _summary_lines(summary: dict, mid_border: str, color: bool) -> list[str]:
    if not summary:
        return []
    c_b, c_w, c_g, c_r = (C_BOLD, bc.C_WHITE, bc.C_GREEN, C_RESET) if color else ("", "", "", "")
    total_reqs = summary.get("totalCount") or 0
    success_rate = bc._safe_float(summary.get("successRate"), 100.0, strip_currency=False)
    tokens_tot = summary.get("totalTokens") or 0
    tokens_in = summary.get("totalTokensIn") or 0
    tokens_out = summary.get("totalTokensOut") or 0
    avg_cost = bc._safe_float(summary.get("averageCost"), 0.0, strip_currency=False)
    return [
        mid_border,
        f"  {c_b}Billing Cycle Telemetry Summary:{c_r}",
        f"    Requests:    {c_w}{total_reqs:,}{c_r}  (Success: {c_g}{success_rate:.2f}%{c_r})",
        f"    Tokens:      {c_w}{format_tokens(tokens_tot)}{c_r}  (In: {format_tokens(tokens_in)} · Out: {format_tokens(tokens_out)})",
        f"    Avg Cost:    ${avg_cost:.4f} / req",
        "",
    ]


def _credits_section_lines(mq: dict, mid_border: str, color: bool) -> list[str]:
    c_b, c_d, c_c, c_g, c_r = (C_BOLD, bc.C_DIM, bc.C_CYAN, bc.C_GREEN, C_RESET) if color else ("", "", "", "", "")
    sub_col = c_g if mq["status"] == "active" else (C_RED if color else "")
    days_left = f" · {mq['days_remain']}d remaining in cycle" if mq["days_remain"] is not None else ""
    lines = [
        f"  Plan: {c_b}{mq['plan_name']}{c_r} [{sub_col}{mq['status'].upper()}{c_r}]{c_d}{days_left}{c_r}",
        mid_border,
        f"  {c_b}Credits & Balances:{c_r}",
        f"    Monthly Remaining:  {c_g}${mq['monthly_rem']:.2f}{c_r} (active billing pool)",
    ]
    if mq["purchased_rem"] > 0 or mq["free_rem"] > 0:
        lines.extend([
            f"    Purchased Credits:  {c_c}${mq['purchased_rem']:.2f}{c_r}",
            f"    Free Credits:       {c_c}${mq['free_rem']:.2f}{c_r}",
        ])
    lines.extend([
        f"    Total Balance:      {c_b}${mq['total_balance']:.2f}{c_r}",
        f"    Period Spend:       {c_d}${mq['total_cost']:.2f}{c_r}",
        "",
    ])
    return lines


def _monthly_block_lines(mq: dict, color: bool) -> list[str]:
    c_b, c_d, c_w, c_g, c_r = (C_BOLD, bc.C_DIM, bc.C_WHITE, bc.C_GREEN, C_RESET) if color else ("", "", "", "", "")
    m_bar = bc.format_bar(mq["percent"], width=22, colorize=color)
    m_pcol = bc.get_percent_color(mq["percent"]) if color else ""
    m_st = ("EXCEEDED" if mq["exceeded"] else "OK") if not color else (f"{C_BOLD}{C_RED}EXCEEDED{c_r}" if mq["exceeded"] else f"{c_g}OK{c_r}")
    rst_date = f" · Reset: {mq['end_dt'].astimezone().strftime('%Y-%m-%d %H:%M %Z')}" if mq["end_dt"] else ""
    return [
        f"    {c_b}Monthly Quota{c_r} [{m_st}]",
        f"      Used: {m_bar} {m_pcol}{mq['percent']:5.1f}%{c_r} (${mq['used']:.2f} / ${mq['cap']:.2f} · {c_g}${mq['monthly_rem']:.2f} left{c_r})",
        f"      Resets in: {c_w}{mq['reset_rel']}{c_r}{c_d}{rst_date}{c_r}",
        "",
    ]


def render_dashboard(telemetry: dict, auth_source: str, color: bool = True) -> str:
    """Render Unicode/plain CommandCode quota dashboard."""
    now_utc = dt.datetime.now(dt.UTC)
    now_ms = now_utc.timestamp() * 1000.0
    c_b, c_r = (C_BOLD, C_RESET) if color else ("", "")
    box_w = min(max(shutil.get_terminal_size((80, 24)).columns - 4, 60), 84)
    out, mid_border, bot_border = bc.quota_box_chrome(
        "⚡ COMMANDCODE GOAT — PROVIDER QUOTA & USAGE RADAR",
        [_identity_subtitle(telemetry, auth_source)],
        box_w,
        color,
    )
    mq = compute_monthly_quota(telemetry, now_utc)
    out.extend(_credits_section_lines(mq, mid_border, color))

    wl = (telemetry.get("credits") or {}).get("windowLimits") or {}
    h5, wk = wl.get("fiveHour") or {}, wl.get("weekly") or {}
    out.append(f"  {c_b}Pooled Rate Limit Windows & Monthly Quota:{c_r}")
    out.extend(_window_block_lines(
        "5-Hour Window",
        bc._safe_float(h5.get("used"), 0.0, strip_currency=False),
        bc._safe_float(h5.get("cap"), 14.0, strip_currency=False),
        bool(h5.get("exceeded")),
        bc.format_relative_epoch_ms(h5.get("resetAt"), now_ms),
        color,
    ))
    out.extend(_window_block_lines(
        "Weekly Window",
        bc._safe_float(wk.get("used"), 0.0, strip_currency=False),
        bc._safe_float(wk.get("cap"), 35.0, strip_currency=False),
        bool(wk.get("exceeded")),
        bc.format_relative_epoch_ms(wk.get("resetAt"), now_ms),
        color,
    ))
    out.extend(_monthly_block_lines(mq, color))
    out.extend(_summary_lines(telemetry.get("summary") or {}, mid_border, color))
    out.append(bot_border)
    return "\n".join(out)


def render_statusline(telemetry: dict) -> str:
    """Render compact single-line CommandCode quota summary."""
    now_utc = dt.datetime.now(dt.UTC)
    now_ms = now_utc.timestamp() * 1000.0
    mq = compute_monthly_quota(telemetry, now_utc)
    wl = (telemetry.get("credits") or {}).get("windowLimits") or {}
    h5 = wl.get("fiveHour") or {}
    wk = wl.get("weekly") or {}

    h5_used = bc._safe_float(h5.get("used"), 0.0, strip_currency=False)
    h5_cap = bc._safe_float(h5.get("cap"), 14.0, strip_currency=False)
    h5_pct = (h5_used / h5_cap * 100.0) if h5_cap > 0 else 0.0
    wk_used = bc._safe_float(wk.get("used"), 0.0, strip_currency=False)
    wk_cap = bc._safe_float(wk.get("cap"), 35.0, strip_currency=False)
    wk_pct = (wk_used / wk_cap * 100.0) if wk_cap > 0 else 0.0
    h5_rst = bc.format_relative_epoch_ms(h5.get("resetAt"), now_ms)
    return (
        f"[CommandCode {mq['plan_name']}] "
        f"5h: ${h5_used:.2f}/{h5_cap:.0f} ({h5_pct:.0f}%, rst {h5_rst}) · "
        f"wk: ${wk_used:.2f}/{wk_cap:.0f} ({wk_pct:.0f}%) · "
        f"mo: ${mq['used']:.2f}/{mq['cap']:.0f} ({mq['percent']:.0f}%, ${mq['monthly_rem']:.2f} left, rst {mq['reset_rel']})"
    )


def _print_missing_key_error(auth_source: str) -> None:
    detail = f"\n  Detail:   {auth_source}" if auth_source != "not found" else ""
    print(
        f"Error: CommandCode API key could not be located.{detail}\n"
        '  Expected: ~/.commandcode/auth.json ("apiKey")\n'
        "  Or set:   export COMMAND_CODE_API_KEY='your_key'\n"
        "  Login via: commandcode auth login",
        file=sys.stderr,
    )


def main():
    parser = argparse.ArgumentParser(
        description="CommandCode Quota & Usage Monitor (Live telemetry via https://api.commandcode.ai)"
    )
    parser.add_argument("-j", "--json", action="store_true", help="Output combined raw JSON response to stdout")
    parser.add_argument("-s", "--statusline", "--short", action="store_true", help="Output single-line compact status")
    parser.add_argument("--key", type=str, default=None, help="Explicit API key (overrides auth.json and env)")
    parser.add_argument("--plain", "--no-color", action="store_true", help="Disable ANSI color codes")

    args = parser.parse_args()
    use_color = not (args.plain or not sys.stdout.isatty())
    api_key, auth_source = resolve_api_key(args.key)
    if not api_key:
        _print_missing_key_error(auth_source)
        sys.exit(1)

    telemetry, errors = fetch_all_telemetry(api_key)
    if not telemetry.get("credits") and not telemetry.get("subscriptions"):
        print(f"Error fetching CommandCode telemetry: {'; '.join(errors) if errors else 'No data returned'}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        mq = compute_monthly_quota(telemetry)
        payload = {
            "fetched_at": dt.datetime.now(dt.UTC).isoformat(),
            "auth_source": auth_source,
            "monthly_quota": {
                "used": round(mq["used"], 4),
                "cap": round(mq["cap"], 2),
                "remaining": round(mq["monthly_rem"], 4),
                "percent": round(mq["percent"], 2),
                "periodStart": mq["period_start"],
                "periodEnd": mq["period_end"],
            },
            "errors": errors or None,
            **telemetry,
        }
        print(json.dumps(payload, indent=2))
        return
    print(render_statusline(telemetry) if args.statusline else render_dashboard(telemetry, auth_source, color=use_color))


if __name__ == "__main__":
    main()
