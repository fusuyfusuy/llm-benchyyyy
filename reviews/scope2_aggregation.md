# Scope 2 — Core Aggregation (`benchmark_common.py` + `llm_benchmark_aggregator.py`) Audit

- **Auditor:** Scope2AggCore
- **Date:** 2026-08-30
- **Files audited (on-disk state, incl. uncommitted changes):**
  - `checkers/benchmark_common.py` (1501 ln)
  - `checkers/llm_benchmark_aggregator.py` (2015 ln)
  - `checkers/test_benchmark_common.py` (282 ln), `checkers/test_llm_benchmark_aggregator.py` (345 ln)
  - `docs/data/benchmarks.json`, `docs/data/raw/` snapshots (offline probes)
- **Method:** full reads of both modules + both test files; offline parser probes against `docs/data/raw/`; python3 repro one-liners for every math/matching claim; monkeypatched-network proof for the fetch path; scope unittests (`Ran 27 tests … OK`). No edits made.

## Verdict

**Health score: 5.0 / 10 (Critical band).** The statistical core (z-scores, Q/P/T_mult/AVI/FGI/BFI, clamping, sigmoid) is correct and well-guarded; offline never-fetch guarantee, diff-before-pool-filter ordering, missing-snapshot degradation, and all five parsers verified healthy against real snapshots (no silent-zero recurrence). However the uncommitted `--fetch` refactor left the cache-refresh path **silently dead** (NameError swallowed), the version-safe matcher demonstrably attributes **another model's scores** to two catalog rows in today's data, and the irrecoverable `benchmarks.json` baseline is written **non-atomically**.

| Severity | Count |
|---|---|
| Critical | 3 |
| Moderate | 3 |
| Minor | 3 |

---

## Critical findings

### C1 — `--fetch` is silently a no-op for LiveBench / LMArena / Artificial Analysis (regression in uncommitted diff)

**Where:** `checkers/llm_benchmark_aggregator.py:948`, `:982`, `:1011` (`if do_fetch:` inside `load_livebench_data`, `load_lmarena_data`, `load_aa_data`), swallowed by the surrounding `except Exception: pass` at `:962-963`, `:991-992`, `:1020-1021`.

**Mechanism:** the working-tree refactor changed the signatures from `(verbose, offline, do_fetch)` to `(verbose, fetch)` (confirmed via `git diff` — the old parameter *was* named `do_fetch`), but the three save-gating lines still reference `do_fetch`. At module scope `do_fetch` is never assigned — it is only a *local* in `main()` (`:1893`). With `fetch=True`, execution reaches `if do_fetch:` → `NameError` → caught by the bare `except Exception: pass` → the live payload is discarded *and* no snapshot is written. With `fetch=False` (default offline path) the line is never reached, so tests and normal runs pass — exactly why 27/27 green unittests missed it.

**Impact:** the advertised cache-refresh contract (`--fetch` help text: "fetch … live, save dated snapshots … update the benchmarks.json NEW baseline", `:1885-1886`) is dead for 3 of 4 sources. Current caches are already 53–59 h old (`cached responses >24h — run with --fetch: LiveBench 59h old, LMArena 53h old, Artificial Analysis 58h old`) and the remedy it prescribes cannot work. Worse, `main()` still runs `save_baseline()` under `if do_fetch:` (`:1949-1951`) and prints `updated NEW-baseline -> …`, a **false success signal** that re-stamps `generated_at` and rewrites the diff baseline from stale data. ARC is unaffected (`load_arc_data` uses the `fetch` parameter correctly, `:1055-1070`).

**Repro (python3, network mocked, repo writes isolated):**
```
== module-level 'do_fetch' exists?
   False <- False => NameError path
== load_lmarena_data(fetch=True) silently discards live payload?
  offline entries: 0  fetch=True entries: 0
  'probe-model-9' present after fetch=True: False
  new files written into real docs/data/raw: []
  tmp snapshot files: []
== NameError proof (bypass bare except): evaluate the body directly
  module-level `do_fetch =` assignments: []
```
(`fetch_url` was monkeypatched to return valid LMArena HTML containing `probe-model-9`; a working fetch path must yield 1 entry. It yields 0 — payload discarded, nothing saved.)

**Fix:** replace `if do_fetch:` with `if fetch:` at `:948/:982/:1011`, and replace the three `except Exception: pass` with logged warnings (the sibling loaders already do `print(f"  WARN …", file=sys.stderr)`, e.g. `:1071-1072`) so future scoping errors surface instead of vanishing.

### C2 — Variant matcher attributes a *different* model's live scores to catalog rows (proven on today's data)

**Where:** `checkers/llm_benchmark_aggregator.py` — the shared `find_*` variant rule `if cn in kn or kn in cn:` + digit-substring "version preservation", `:797-801` (livebench), `:833-837` (lmarena), `:869-873` (aa), `:904-908` (arc).

**Mechanism:** raw substring containment accepts *family-suffix* variants as the same model whenever the digit tokens merely appear anywhere in the other slug. `mimo-v2-5` ⊂ `mimo-v2-5-pro`, and versions `["2","5"]` are trivially "in" the longer key. Exact match fails upstream (AA has no `mimo-v2-5` row), so the fallback fires and `main()` (`:1921-1927`) overwrites the base model's `aa_quality`/`aa_coding`/`speed_tps` with **Pro's** numbers — while the separate `MiMo V2.5 Pro` catalog row exact-matches the *same* upstream record. One upstream row now feeds two different-priced models; the static catalog values (80.5 / 115 t/s for the base; 85.0 / 60 t/s for Pro) are destroyed for scoring.

**Repro (offline, real snapshot data, `find_aa`):**
```
AA has exact 'mimo-v2-5'? False | has 'mimo-v2-5-pro'? True
pro rec: {'intelligenceIndex': 42.8796821546836, 'codingIndex': 60.189520044389, 'medianTps': 41.845357662131}
find_aa(MiMo-V2.5) -> mimo-v2-5-pro
post-update MiMo-V2.5: {'aa_quality': 42.8796821546836, ...}
find_aa(MiMo V2.5 Pro).slug = mimo-v2-5-pro
find_aa(MiMo-V2.5).slug     = mimo-v2-5-pro
```
And from a real offline `--json` run today:
```
MiMo V2.5 Pro | Q 74.2 | aa_quality 42.8796821546836 | speed 41.845357662131
MiMo-V2.5     | Q 71.2 | aa_quality 42.8796821546836 | speed 41.845357662131
GPT-5.2 Codex | Q 79.9 | arc 52.9 | arc_display GPT-5.2 (XHigh)
```
Second proven instance: **GPT-5.2 Codex** picks up plain **GPT-5.2 (XHigh)**'s ARC-AGI-2 score (52.9 replaces the static 48.0) via *reverse* containment (`kn`="gpt-5-2" ⊂ `cn`="gpt-5-2-codex") — `arc_display` is the smoking gun persisted right in the row. The LiveBench `LB~…-max-effort` / `-xhigh-effort` hits for the Claude rows are the intended effort-suffix trade-off (LiveBench only publishes effort-suffixed rows); `-pro` / bare-base-vs-Codex are not — the catalog itself lists those as distinct models.

**Fix:** make the variant step token-aware instead of character-aware: split both normalized slugs on `-`; accept only if all digits align **and** every surplus token on the longer side is in the known effort/tier allow-list (reuse `ARC_TIER_RE` vocabulary `max|x-?high|high|medium|low|thinking|preview|cot|effort|reasoning|flagship|bedrock` plus `auto`); reject other surplus tokens (`pro`, `codex`, …) outright.

### C3 — `benchmarks.json` baseline written non-atomically; a torn write silently destroys the only `first_seen` history

**Where:** `checkers/llm_benchmark_aggregator.py:1857` — `p.write_text(json.dumps(payload, indent=2), encoding="utf-8")` over the 41 KB live baseline in place (`save_baseline`).

**Mechanism:** `write_text` truncates the target then streams; a crash, OOM kill, or ENOSPC mid-write leaves a truncated file. The reader side — `bc.load_previous_snapshot` (`benchmark_common.py:1279-1287`) — catches *any* parse error and returns `None`, and `diff_model_catalog` treats `None` as cold start: removed-model detection goes blank, and every surviving `first_seen`/green-window memory (the 7-day NEW highlight, `:1334-1335`) is gone with no error surfaced. This file is the only store of first-seen history — it is not regenerable from `docs/data/raw/` (raw snapshots carry no observation timestamps). Per rubric, torn write of this artifact = silent data loss = Critical. (Note: no atomic-write pattern exists anywhere in `checkers/` — this is the file where the gap actually loses data; the same pattern under C1's false-success save makes it reachable in normal operation.)

**Suggested fix (`save_baseline`):**
```python
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(tmp, p)
```

---

## Moderate findings

### M1 — `compute_pareto_frontier` treats `effective_cost == 0.0` as missing → free models scored at cost 999

**Where:** `checkers/benchmark_common.py:233` and `:237` — `a.get("effective_cost") or (a.get("price_in", 999) + a.get("price_out", 999)) or 999`.

**Repro:**
```
pareto with eff=0.0 FreeX: ['CheapY'] <- FreeX dropped? 0.0 treated as 999
```
A genuinely free frontier model (`effective_cost` 0.0 — exact `round(0.0 * t, 2)`, or `price_in`+`price_out` = 0) is assigned pseudo-cost 999 and loses the Pareto sweep to any equal-Q paid model — the *worst* possible treatment of a free model. bcheck's 30 catalog rows all have non-zero blended prices so this is latent for bcheck's tables today, but the same primitive computes gold-row highlighting for every checker (and `render_cli_table`/`render_html_report` call it by default, `:1219`, `:1674`); any zero-cost row (free pool, promo pricing) triggers it. Also, if a row has `"price_in": None`, the expression raises `TypeError` (`None + float`). Fix: explicit `is None` / `or`-free chain with `math.isfinite`-style guards.

### M2 — staleness check keys on file *mtime*, so a fresh `git clone`/checkout masks weeks-old cached scores

**Where:** `checkers/llm_benchmark_aggregator.py:1030` — `newest = max(os.path.getmtime(p) for p in matches)`.

`git` sets checkout mtimes to checkout time, and the filenames already carry the authoritative date (`arc_agi_20260830.json`, `lmarena_20260827.html`). A user who clones the repo gets a 9-month-old `livebench_20260108.csv` with today's mtime → `cache_staleness_note()` returns `""` → the leaderboard renders ancient LiveBench numbers with **no** warning, defeating the only staleness defense in the offline design. Fix: derive age from the 8-digit date in the stem (fall back to mtime when absent). The `> CACHE_TTL_H` comparison itself is correct (no off-by-one; message text matches).

### M3 — Test-adequacy gap: the exact contract that broke is untested

Both files run green (27/27, `python3 -m unittest checkers.test_benchmark_common checkers.test_llm_benchmark_aggregator` → `OK`), and math edge coverage is decent (`get_z_scores([])`, `[10.0]`, Q/P/T clamps, `compute_effective_cost`, first_seen 0/3/8-day windows, epoch s/ms equivalence, save/load roundtrip). Gaps, ranked by what they'd have caught:

1. **No test exercises any `load_*_data(fetch=True)` path** — this is precisely how C1 (a `NameError` swallowed by a bare `except`) shipped. A single monkeypatched-`fetch_url` + temp-`RAW` test (pattern already established in `test_newest_snapshot_age_and_staleness:276-299`) closes it.
2. No same-value input (`std=0`) case for `get_z_scores` — behavior is correct ([0,0,0] verified) but only by accident of `v-mean==0`; untested contract.
3. `parse_aa` tests a single `"models":[` array only — the "largest array carrying scores" selection over the repeated nav/marketing copy (`benchmark_common.py:457-487`) is untested.
4. No corrupt/truncated `benchmarks.json` fallback test pinning the (lossy) `load_previous_snapshot → None` contract, and none asserting write atomicity (C3).
5. Nothing pins the "diff-before-pool-filter" ordering invariant (verified manually here: `main()` diffs the full catalog at `:1945-1946` before the `--pool` filter at `:1954-1959` — HOLDS, but silently breakable).

---

## Minor findings

- **m1 — `--html`/`--md` default paths are CWD-relative, `OUT` constant dead** (`:1883-1884`, `:46`): `--html` with no argument writes `docs/reports/benchmarks.html` relative to the *invocation* directory, not `ROOT`. Proven: run from `/tmp/scope2cwd` created `/tmp/scope2cwd/docs/reports/benchmarks.html` (37 KB) outside the repo while the intended tree stays stale. `OUT = ROOT / "docs" / "reports"` is defined and never used.
- **m2 — falsy-chain fallback in `parse_livebench`** (`benchmark_common.py:369-375`): `cat_scores.get("Coding") or cat_scores.get("coding") or _safe_float(...)` silently drops a legitimate `0.0` category average into the next fallback. bcheck consumes only `overall`, so impact is confined to sibling checkers reading `.coding`/`.reasoning`.
- **m3 — `display_len`/`color_cell` strip and emit only SGR sequences** (`benchmark_common.py:563`, `:588`): non-SGR escapes (OSC-8 hyperlinks, cursor codes) inside a rendered string would count as printable width (table misalignment) and pass through raw (escape smuggling). **No reachable vector in bcheck today** — every rendered name is a static catalog literal; scraped strings enter only as numbers, and `removed_models` names come from the repo-owned baseline. Flagged as a hardening note for the shared primitive (the vector is real wherever a checker renders raw upstream names — seam/sibling scope).

---

## Invariant / requirement checklist (per assignment dimensions)

| Check | Result | Evidence |
|---|---|---|
| z-scores std=0 / len<2 | **HOLDS** | `get_z_scores([5,5,5])=[0,0,0]`, `[None,3]=[0,0]`, `[]=[]` (probe) |
| `compute_capability_q`/`p_success`/`token_multiplier`/`effective_cost`/`avi`/`fgi`/`bfi` bounds & clamps | **HOLDS** | formulas at `bc:153-208`; live Q range 64.9–87.7; unittest pass |
| blended price 0.8·in + 0.2·out; BFI-gross vs AVI-net split | **HOLDS** (as documented) | `agg:1172-1183`; weights sum verified via unittest |
| medal/rank computation (column top-3, rank order) | **HOLDS** | `bc:679-700`; `eff_cost`/`price` correctly `reverse=False` (`agg:1202`, `:1209`) |
| `score_color_avi` calibration (ADR 2026-08-27) | **HOLDS** | no ADR text in repo (git log -S: only refactor commits); empirical live AVI distribution 98.5 / p25 163.3 / med 194.7 / p75 265.1 / max 595.5 matches docstring's "~100-600" → 140/200/300 ladder is a sane quartile split |
| created_date/first_seen flow (ARC `modelReleaseDate`) | **HOLDS** | 214/214 ARC recs carry `released` (probe); precedence r→prev→created (`bc:1382-1405`); green-window roundtrip test passes |
| silent-zero regression (0/249 history) | **CLEAR** | AA 616/616/623 entries parsed, 13 upstream-null intel (never 100%), zero parsed as 0: 0; livebench 150 entries, `overall_None=0`; lmarena 394 merged, `elo_None=0`; `capability_q==78.0` fingerprint count in baseline: **0** |
| 24 h cache staleness (off-by-one/timezone) | HOLDS | `age > 24` vs message; mtime→**M2** caveat |
| never-fetch offline guarantee | **HOLDS** | `fetch_url` monkeypatched to raise; default run + empty cache rendered full 30-row table, zero network calls |
| baseline read / corrupt-JSON fallback | HOLDS (silent) | try/except→None, but silent-loss path amplifies **C3** |
| atomic write of benchmarks.json | **VIOLATED** | **C3** |
| diff-before-pool-filter | **HOLDS** | `:1945-1946` vs `:1954-1959` (code order) |
| missing-snapshot crash behavior | HOLDS | empty-`RAW` run exits 0 with "missing" staleness banner |
| dict mutation aliasing across stages | benign | shared `livebench` rec dict referenced by multiple rows; renderers read-only. `mimo` case is data *misattribution* (C2), not aliasing |
| perf: O(n²) joins/frontier at n≈30 (bcheck) / 623 (maps) | non-issue | full offline run ≈ 1.8–2.2 s; `norm_model_slug` recomputed per pair (~19 k regex calls) — acceptable at this scale |
| HTML escaping of scraped strings into shared template | HOLDS in bcheck | name/tier/stale-note/removed/pool all `html.escape`d (`agg:1696-1793`, `bc:1237-1272`); scraped ARC/livebench *names* never rendered (`arc_display` persisted but unused) |
| `--sort live` crash with livebench-less rows | **REFUTED by execution** | 7 rows lack `livebench`; expression `:1976` falls back `None→0` via `or`; run exits 0 |

## Parser offline probe — record counts (`docs/data/raw/`, 2026-08-30)

| Parser | Source | Records | Null scores |
|---|---|---|---|
| `parse_aa` | artificial_analysis 0822 / 0823 / 0827 | 616 / 616 / 623 | 13 upstream null `intelligenceIndex` (all snapshots), 0 zeros |
| `parse_lmarena` | lmarena 0822 / 0823 / 0827 (merged, newest-wins) | 393 / 394 / 394 → 394 | 0 null elo |
| `parse_livebench` (`load_livebench_data`) | 4 CSVs incl. 20260108 + cost-excluded 20260625 | 150 | 0 null overall |
| `parse_openrouter` | openrouter_models_20260830 | 396 (21 free, 0 stealth) | 0 null prompt price |
| `load_arc_data` + `parse_arc` | arc_agi 0828/0830 (newest) | 214 keys / 88 groups | 0 null score, 0 null release |
| baseline | `docs/data/benchmarks.json` | 30 models, 22 `first_seen`, 5 `is_new`, diff {added:5, removed:0} | — |

## P1 / P2 backlog

**P1 (fix before next merge):**
1. C1 — `if do_fetch:` → `if fetch:` at `agg:948/982/1011`; log instead of swallow at the 3 loaders' except blocks; then re-run `--fetch` and confirm a `lmarena_20260830.html`-class snapshot actually lands (caches are 53–59 h stale and cannot self-heal today).
2. C2 — token-level tier allow-list in all four `find_*` variant branches; re-verify `MiMo-V2.5` and `GPT-5.2 Codex` rows revert to static values and `find_aa(mimo-v2.5)` returns None while `find_aa(mimo-v2.5-pro)` exact-matches.
3. C3 — tmp+`os.replace` in `save_baseline` (`agg:1857`).

**P2 (next cycle):** M1 None-safe Pareto fallback; M2 date-from-filename staleness; M3 fetch-path/std=0/multi-array/corrupt-baseline tests; m1 ROOT-anchor `--html`/`--md` defaults (use `OUT`).
