#!/usr/bin/env python3
"""
Local Evaluation Runner: Zero-external-dependency test harness for benchmarking
models across Architecture, Agentic Coding, and Formal Reasoning.
"""

import os
import sys
import json
import time
import re
import subprocess
import urllib.request
import urllib.error
from typing import Dict, List, Any, Optional

BENCHMARK_TASKS = [
    # -------------------------------------------------------------------------
    # 1. ARCHITECTURE & DESIGN (Modular structure, state boundaries, strict contracts)
    # -------------------------------------------------------------------------
    {
        "id": "arch_order_state_machine",
        "domain": "Architecture & Design",
        "description": "Pure state machine with boundary transition enforcement and domain exceptions.",
        "prompt": """Write a pure Python state machine class named `OrderStateMachine`.
Rules:
1. Valid states: 'DRAFT', 'SUBMITTED', 'PAID', 'FULFILLED', 'CANCELLED'.
2. Initial state must be 'DRAFT'.
3. Permitted transitions:
   - 'DRAFT' -> 'SUBMITTED' (event 'submit') or 'CANCELLED' (event 'cancel')
   - 'SUBMITTED' -> 'PAID' (event 'pay') or 'CANCELLED' (event 'cancel')
   - 'PAID' -> 'FULFILLED' (event 'fulfill') or 'CANCELLED' (event 'cancel')
   - 'FULFILLED' and 'CANCELLED' are terminal states (no further transitions permitted).
4. Calling `sm.transition(event_name)` must update `sm.state` on success.
5. If an illegal transition is attempted, raise a `ValueError` with message: "Invalid transition '<event>' from state '<state>'".
Provide ONLY the Python code block (inside ```python ... ```). Do not include explanation text.""",
        "verification_script": """
sm = OrderStateMachine()
assert sm.state == 'DRAFT', f"Expected DRAFT, got {sm.state}"
sm.transition('submit')
assert sm.state == 'SUBMITTED', f"Expected SUBMITTED, got {sm.state}"

try:
    sm.transition('fulfill')
    raise AssertionError("Should have raised ValueError on illegal transition")
except ValueError as e:
    assert "Invalid transition 'fulfill' from state 'SUBMITTED'" in str(e), f"Unexpected message: {e}"

sm.transition('pay')
assert sm.state == 'PAID'
sm.transition('fulfill')
assert sm.state == 'FULFILLED'

try:
    sm.transition('cancel')
    raise AssertionError("Terminal state should reject transitions")
except ValueError:
    pass

print("OK")
"""
    },
    {
        "id": "arch_event_dispatcher",
        "domain": "Architecture & Design",
        "description": "Deterministic event bus with handler prioritization and cycle-safe dispatch.",
        "prompt": """Write a Python class named `PriorityEventBus`.
Rules:
1. Method `subscribe(event_type: str, handler_fn, priority: int = 10)`: registers a handler. Higher priority number executes first. If priorities are equal, preserve insertion order.
2. Handler registration with the same function for the same event must not duplicate execution.
3. Method `publish(event_type: str, payload: dict) -> list`: calls handlers in priority order, passing `payload`. Returns list of handler return values in execution order.
4. If a handler raises an exception, catch it, append `None` to the results list, and continue executing remaining handlers.
Provide ONLY the Python code block (inside ```python ... ```). Do not include explanation text.""",
        "verification_script": """
bus = PriorityEventBus()
calls = []
def h1(payload): calls.append('h1'); return 1
def h2(payload): calls.append('h2'); return 2
def h_err(payload): calls.append('err'); raise RuntimeError('boom')
def h3(payload): calls.append('h3'); return 3

bus.subscribe('user_created', h1, priority=10)
bus.subscribe('user_created', h_err, priority=50)
bus.subscribe('user_created', h2, priority=100)
bus.subscribe('user_created', h3, priority=10)
bus.subscribe('user_created', h1, priority=10)

results = bus.publish('user_created', {'id': 42})
assert calls == ['h2', 'err', 'h1', 'h3'], f"Execution order wrong: {calls}"
assert results == [2, None, 1, 3], f"Results wrong: {results}"
print("OK")
"""
    },

    # -------------------------------------------------------------------------
    # 2. AGENTIC CODING & SURGICAL PATCHING (Constraint satisfaction, parsing)
    # -------------------------------------------------------------------------
    {
        "id": "agentic_composite_duration_parser",
        "domain": "Agentic Coding",
        "description": "Parse composite duration strings with arbitrary whitespace and unit variations.",
        "prompt": """Write a Python function `parse_duration(duration_str: str) -> int`.
It parses human-readable duration strings into total elapsed seconds.
Supported unit suffixes:
- 's' or 'sec': seconds
- 'm' or 'min': minutes (60s)
- 'h' or 'hr': hours (3600s)
- 'd' or 'day': days (86400s)
Rules:
1. Handle arbitrary whitespace and commas, e.g. '1h 30m 10s', '2 days, 4 hr', '45min 15sec'.
2. If the string is empty or contains invalid tokens/units, raise `ValueError`.
3. Return integer total seconds.
Provide ONLY the Python code block (inside ```python ... ```). Do not include explanation text.""",
        "verification_script": """
assert parse_duration('10s') == 10
assert parse_duration('5m') == 300
assert parse_duration('2h') == 7200
assert parse_duration('1d') == 86400
assert parse_duration('1h 30m 10s') == 5410
assert parse_duration('2 days, 4 hr') == (2 * 86400 + 4 * 3600)
assert parse_duration('45min 15sec') == (45 * 60 + 15)

for bad in ['', '   ', 'abc', '10x', '10 s 20']:
    try:
        parse_duration(bad)
        raise AssertionError(f"Should raise ValueError on '{bad}'")
    except ValueError:
        pass
print("OK")
"""
    },
    {
        "id": "agentic_unified_diff_patcher",
        "domain": "Agentic Coding",
        "description": "Apply standard unified diff chunk to multi-line source text.",
        "prompt": """Write a Python function `apply_simple_diff(original_text: str, patch_text: str) -> str`.
The patch text consists of unified diff format lines starting with:
- ' ' (context line, must match original line)
- '-' (deleted line)
- '+' (inserted line)
Ignore standard diff headers like '---' or '+++' or '@@ ... @@' if present.
Return the updated text reconstructed after applying additions and deletions.
If context or deleted line doesn't match original sequence, raise `ValueError`.
Provide ONLY the Python code block (inside ```python ... ```). Do not include explanation text.""",
        "verification_script": """
orig = "line 1\\nline 2\\nline 3\\nline 4"
patch = \"\"\"
@@ -1,4 +1,4 @@
 line 1
-line 2
+line 2 modified
 line 3
 line 4
\"\"\"
res = apply_simple_diff(orig, patch)
assert res == "line 1\\nline 2 modified\\nline 3\\nline 4", f"Diff failed: {res}"

patch2 = \"\"\"
 line 1
 line 2 modified
-line 3
 line 4
+line 5
\"\"\"
res2 = apply_simple_diff(res, patch2)
assert res2 == "line 1\\nline 2 modified\\nline 4\\nline 5", f"Diff 2 failed: {res2}"
print("OK")
"""
    },

    # -------------------------------------------------------------------------
    # 3. FORMAL REASONING & DEDUCTIVE LOGIC (Topological constraints, intervals)
    # -------------------------------------------------------------------------
    {
        "id": "reasoning_dependency_dag_waves",
        "domain": "Formal Reasoning",
        "description": "Compute optimal sequential deployment waves under DAG & mutual exclusion constraints.",
        "prompt": """Write a Python function `compute_deploy_waves(dependencies: dict[str, list[str]], exclusive_pairs: list[tuple[str, str]]) -> list[list[str]]`.
Args:
- `dependencies`: maps task -> list of tasks that MUST complete before this task can start.
- `exclusive_pairs`: pairs of tasks that CANNOT execute in the same wave (must be separated into different waves).
Rules:
1. Each task must appear exactly once in the returned waves.
2. A task can only be scheduled in wave `W` if all its dependencies are in waves `< W`.
3. No two tasks in the same wave can belong to `exclusive_pairs`.
4. Tasks in the same wave should be sorted alphabetically.
5. Minimize the total number of waves. If tie, prefer earlier waves for earlier alphabetical tasks.
6. If a cycle or impossible condition exists, raise `ValueError("Unresolvable dependencies")`.
Provide ONLY the Python code block (inside ```python ... ```). Do not include explanation text.""",
        "verification_script": """
deps = {
    'A': [],
    'B': ['A'],
    'C': ['A'],
    'D': ['B', 'C'],
    'E': ['D'],
}
excl = [('B', 'C')]

waves = compute_deploy_waves(deps, excl)
assert len(waves) == 5, f"Expected 5 waves, got {len(waves)}: {waves}"
assert waves[0] == ['A'], f"Wave 0: {waves[0]}"
b_wave = next(i for i, w in enumerate(waves) if 'B' in w)
c_wave = next(i for i, w in enumerate(waves) if 'C' in w)
assert b_wave != c_wave, "B and C must not share a wave"
assert b_wave in (1, 2) and c_wave in (1, 2)
assert waves[3] == ['D']
assert waves[4] == ['E']

cycle_deps = {'X': ['Y'], 'Y': ['X']}
try:
    compute_deploy_waves(cycle_deps, [])
    raise AssertionError("Should raise on cycle")
except ValueError:
    pass
print("OK")
"""
    },
    {
        "id": "reasoning_interval_override_merge",
        "domain": "Formal Reasoning",
        "description": "Merge discontinuous time intervals with tier-priority override resolution.",
        "prompt": """Write a Python function `resolve_interval_overrides(intervals: list[tuple[int, int, int]]) -> list[tuple[int, int, int]]`.
Each interval is `(start, end, priority)` where `start < end`.
Higher priority completely overrides lower priority on overlapping spans.
Rules:
1. Resolve all overlaps: overlapping segments take the priority of the highest-priority interval active during that segment.
2. Contiguous or overlapping segments with the SAME priority must be merged into a single interval `(start, end, priority)`.
3. Return intervals sorted chronologically by `start`.
Provide ONLY the Python code block (inside ```python ... ```). Do not include explanation text.""",
        "verification_script": """
ivs = [(0, 10, 1), (3, 7, 5)]
res = resolve_interval_overrides(ivs)
assert res == [(0, 3, 1), (3, 7, 5), (7, 10, 1)], f"Expected split, got {res}"

ivs2 = [(0, 5, 2), (5, 10, 2)]
res2 = resolve_interval_overrides(ivs2)
assert res2 == [(0, 10, 2)], f"Expected merge, got {res2}"

ivs3 = [(0, 20, 1), (5, 15, 3), (8, 12, 10)]
res3 = resolve_interval_overrides(ivs3)
assert res3 == [(0, 5, 1), (5, 8, 3), (8, 12, 10), (12, 15, 3), (15, 20, 1)], f"Nested fail: {res3}"
print("OK")
"""
    }
]


def query_gemini_api(model: str, prompt: str, api_key: str, timeout: int = 60, max_retries: int = 6) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 8192}
    }).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    
    last_err = None
    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                parts = data["candidates"][0]["content"]["parts"]
                return "".join(p.get("text", "") for p in parts)
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code in (429, 500, 502, 503, 504) and attempt < max_retries - 1:
                sleep_sec = 4 * (attempt + 1)
                time.sleep(sleep_sec)
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as e:
            last_err = e
            if attempt < max_retries - 1:
                time.sleep(2)
                continue
            raise
    raise last_err


def query_openrouter_api(model: str, prompt: str, api_key: str, timeout: int = 60, max_retries: int = 4) -> str:
    url = "https://openrouter.ai/api/v1/chat/completions"
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 4096,
    }).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://github.com/fusuyfusuy/llm-benchyyyy",
        "X-Title": "LocalEvalHarness"
    })
    last_err = None
    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code in (429, 500, 502, 503, 504) and attempt < max_retries - 1:
                sleep_sec = 2 ** (attempt + 1)
                time.sleep(sleep_sec)
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as e:
            last_err = e
            if attempt < max_retries - 1:
                time.sleep(2)
                continue
            raise
    raise last_err


def clean_extracted_code(raw_response: str) -> str:
    pattern = r"```(?:python)?\s*(.*?)(?:```|$)"
    matches = re.findall(pattern, raw_response, re.DOTALL)
    if matches and matches[0].strip():
        return matches[0].strip()
    lines = raw_response.strip().splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def query_agy_cli(model: str, prompt: str, timeout: int = 120) -> str:
    cmd = [
        "agy",
        "-p",
        prompt,
        "--model",
        model,
        "--disable-slash-commands",
        "--dangerously-skip-permissions"
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        err = proc.stderr.strip() or f"exit code {proc.returncode}"
        raise RuntimeError(f"agy CLI error: {err[:120]}")
    return proc.stdout


def run_test_sandboxed(code: str, verification_script: str, timeout: int = 8) -> tuple[bool, str]:
    full_source = code + "\n\n# --- Verification Suite ---\n" + verification_script
    try:
        proc = subprocess.run(
            [sys.executable, "-c", full_source],
            capture_output=True,
            text=True,
            timeout=timeout
        )
        if proc.returncode == 0 and "OK" in proc.stdout:
            return True, "PASSED"
        err = proc.stderr.strip() or proc.stdout.strip()
        last_line = err.splitlines()[-1] if err.splitlines() else "Non-zero exit"
        return False, last_line[:120]
    except subprocess.TimeoutExpired:
        return False, f"Timeout ({timeout}s expired - likely infinite loop)"
    except Exception as e:
        return False, str(e)[:120]


def benchmark_model(
    model_identifier: str,
    provider: str,
    api_key: str,
    tasks: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    if tasks is None:
        tasks = BENCHMARK_TASKS

    results = {
        "model": model_identifier,
        "provider": provider,
        "total_tasks": len(tasks),
        "passed": 0,
        "failed": 0,
        "pass_rate_pct": 0.0,
        "total_duration_sec": 0.0,
        "task_results": [],
        "domain_scores": {}
    }

    t0_all = time.time()
    for t in tasks:
        t_id = t["id"]
        domain = t["domain"]
        sys.stdout.write(f"  [{domain[:12]}] {t_id:<32} ... ")
        sys.stdout.flush()

        t0 = time.time()
        success = False
        error_msg = ""
        latency = 0.0

        try:
            if provider == "gemini":
                raw_resp = query_gemini_api(model_identifier, t["prompt"], api_key)
            elif provider == "openrouter":
                raw_resp = query_openrouter_api(model_identifier, t["prompt"], api_key)
            elif provider == "agy":
                raw_resp = query_agy_cli(model_identifier, t["prompt"])
            else:
                raise ValueError(f"Unknown provider: {provider}")

            latency = round(time.time() - t0, 2)
            code = clean_extracted_code(raw_resp)
            success, error_msg = run_test_sandboxed(code, t["verification_script"])

        except Exception as e:
            latency = round(time.time() - t0, 2)
            success = False
            error_msg = f"API Error: {str(e)[:100]}"

        if success:
            sys.stdout.write(f"✅ PASS ({latency}s)\n")
            results["passed"] += 1
        else:
            sys.stdout.write(f"❌ FAIL ({latency}s) -> {error_msg}\n")
            results["failed"] += 1

        results["task_results"].append({
            "id": t_id,
            "domain": domain,
            "passed": success,
            "latency_sec": latency,
            "error": error_msg if not success else None
        })

        if domain not in results["domain_scores"]:
            results["domain_scores"][domain] = {"passed": 0, "total": 0}
        results["domain_scores"][domain]["total"] += 1
        if success:
            results["domain_scores"][domain]["passed"] += 1
        time.sleep(3)

    results["total_duration_sec"] = round(time.time() - t0_all, 2)
    results["pass_rate_pct"] = round((results["passed"] / len(tasks)) * 100, 1)
    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--provider", choices=["gemini", "openrouter", "agy"], required=True)
    parser.add_argument("--output", help="Save JSON results to file")
    args = parser.parse_args()

    key = ""
    if args.provider == "gemini":
        key = os.environ.get("GEMINI_API_KEY_DAVAY") or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    elif args.provider == "openrouter":
        key = os.environ.get("OPENROUTER_API_KEY")
    else:
        key = "agy-native"

    if not key:
        print(f"Error: Missing API key for {args.provider}")
        sys.exit(1)

    print(f"\n🚀 Running Local Eval Battery on {args.model} ({args.provider})...")
    res = benchmark_model(args.model, args.provider, key)
    print(f"\n📈 Final Result: {res['passed']}/{res['total_tasks']} ({res['pass_rate_pct']}%) in {res['total_duration_sec']}s")

    if args.output:
        with open(args.output, "w") as f:
            json.dump(res, f, indent=2)
        print(f"Saved results to {args.output}")
