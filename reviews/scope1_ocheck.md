# Scope 1 — Live Scraper (ocheck) Audit

**Target:** `checkers/opencode_cost_benefit_analyzer.py` (2298 ln), `checkers/test_opencode_cost_benefit_analyzer.py`, artifacts `docs/data/ocgo_live.json` + `docs/reports/ocgo_cost_benefit.html`
**Date:** 2026-08-30 · **Mode:** diagnostic only, zero edits · **Rubric:** Critical <7 / Moderate 7.0–8.4 / Minor 8.5–9.4 / Exemplary 9.5–10

## Scorecard

| Field | Value |
|---|---|
| **Health score** | **5.4 / 10 (Critical band)** |
| Critical | 4 |
| Moderate | 3 |
| Minor | 3 |
| Scope tests | 10/10 pass (`python3 -m unittest checkers.test_opencode_cost_benefit_analyzer` — 0.597s) |
| Smoke runs | `--offline --check` exit 0; `--offline --check --limits` exit 0; artifacts on disk were regenerated 2026-08-30T01:55Z |
| XSS hypothesis | **Refuted by execution** — `render_html` escapes every scraped string (see D4) |
| Parser record loss | **Refuted on current snapshots** — 0 dropped records in AA/OR/LiveBench/docs (see probes) |

## Verification log (offline probes backing all claims)

| Probe | Method | Result |
|---|---|---|
| P1 docs parser | `parse_ocgo_docs(opencode_go_docs_20260822.html)` | 4 tables; pricing table 29 body rows → 23 models; **0 rows dropped, 0 <6-cell rows**; 6 tier-duplicate rows deduped keeping the cheaper row (verified pair-by-pair, e.g. GPT-5.6-Luna kept ≤272K $0.20/1.20 over >272K $0.40/1.80) → intended behavior; requests table 22/22; token estimates 27 |
| P2 AA parser | `parse_aa(artificial_analysis_20260827.html)` (4.6 MB) | 623 records in 0.40 s; 610 with `intelligenceIndex`, 235 `codingIndex`, 177 `agenticIndex`; identical to `bc.parse_aa` — no loss |
| P3 OpenRouter | `parse_openrouter(openrouter_models_20260830.json)` | 396 items in / 396 keys out; 0 missing-id, 0 duplicate-collapse |
| P4 LiveBench | `parse_livebench` per CSV | 20260108: 121/121, 20260625: 46/46, 20260823: 46/46, 20260827: 49/49; header is 1 `model` + 23 task cols, no summary column double-counted; category keys match code lookups exactly |
| P5 match audit | per-model matcher runs vs snapshots + stored JSON | AA tier distribution over the 34 live rows: **exact=27, contains=4, prefix=1, miss=2**; LMArena **9 of 28 hits are fuzzy/wrong-model**; LiveBench **5 suspect matches incl. two from the Jan snapshot** |
| P6 escaping | hostile `model_id`, `aa_slug`, removed-name through `render_html` | all hostile strings appear only in escaped form (`&lt;svg`, `&quot;&gt;&lt;img`); sole raw `<script` is bc's static sort script; role-rec HTML escapes names (`benchmark_common.py:1248-1251`) |
| P7 first_seen | compare `git show HEAD:docs/data/ocgo_live.json` vs working copy | 6 non-docs models carry `is_new: True` with `first_seen` **equal to each run's timestamp** (2026-08-27T22:37 → 2026-08-30T01:55); same 6 legacy models both runs |
| P8 crash surfaces | offline w/ zero raw files, corrupt snapshot JSON, missing categories | all guarded (`try/except` + fallback chains 1526→1554, 1596, 1619, 1642) — no crash-loop reachable |

---

## Findings

### 🔴 C1 — `find_aa_for_ocgo` contains/prefix fallbacks match across model variants, silently scoring the wrong model
**File:504-528 (contains 514-520, prefix 521-527) · Priority P1 · Confidence 0.95 · Critical (silent data corruption of shipped artifacts)**

Mechanism: after exact and norm-exact fail, the contains loop (517: `if n in ns or ns in n`) returns the **first AA slug in document order** whose normalized id is any substring of the query or vice versa — suffix variants (`-pro`, `-next`, `-omni`, `-vision`, `-contributor`) are not excluded. The prefix fallback is worse: 526 checks only that `n.split("-")[1]` appears in the candidate slug; for a dotted family like `qwen3.5-plus` the second normalized token is `"5"` (one char), so almost any qwen3 record passes.

Evidence (live artifacts, `docs/data/ocgo_live.json` generated 2026-08-30T01:55Z):
- `mimo-v2.5` → `aa_slug: mimo-v2-5-pro`, `aa_intelligence: 42.8796821546836` — **byte-identical to the `mimo-v2.5-pro` row's value**. The AA snapshot genuinely has no plain `mimo-v2.5` record, so the report silently substitutes the Pro variant's benchmark.
- `qwen3.8-flash` → `qwen3-8-flash-next` (55.81) — scored on the "next" rolling-preview variant.
- `muse-spark-1.2-contributor` → `muse-spark-1-2` — base model's score attributed to the contributor build.
- `deepseek-v4-flash-vision-exp` → `deepseek-v4-flash-vision`.
- `qwen3.5-plus` → `qwen3-5-omni-plus` (31.34) via the 1-char prefix path — an **omni multimodal** record, 9+ points below sibling variants, feeding the composite.

Impact: `aa_intelligence/coding/agentic/context` feed z-scores with combined weight 0.65 (1882-1921), flagship/value CSS classes (2192-2195), role recommendations, AVI/FGI, and the JSON consumed by the aggregator. Only `aa_slug` hints at the substitution (2210); nothing warns that the row's scores are another model's.

Fix direction: variant-token-aware matching — reject contains hits whose extra trailing tokens are variant suffixes (`pro|max|next|omni|exp|thinking|high|xhigh|preview|contributor|code`); drop the prefix fallback or require all non-numeric tokens present; return `None` on ambiguity and surface "no AA record" explicitly.

### 🔴 C2 — `find_lm_for_ocgo` contains loop has no guard at all: 9/28 catalog rows matched to wrong Arena entries
**File:531-544 (loop 540-543) · Priority P1 · Confidence 0.95 · Critical**

Mechanism: 542 (`if n in ns or ns in n: return rec`) returns the first substring hit with **no quality guard whatsoever** (the AA finder at least requires `intelligenceIndex`), and iteration order is leaderboard rank, so a bare-name entry beats the correct suffixed entry for shorter queries.

Evidence (offline probe vs `lmarena_20260827.html`, 34 current model ids):
`glm-5.3-flash` → **`glm-5`** (an entirely different flagship); `hy3-preview` → `hy3`; `qwen3.7-max` → `qwen3.7-max-preview`; `kimi-k3` → `kimi-k3-max`; `glm-5.3` → `glm-5.3-max`; `glm-5.2` → `glm-5.2-max`; `grok-4.6` → `grok-4.6-high`; `gpt-5.6-luna` → `gpt-5.6-luna-xhigh`; `muse-spark-1.2-contributor` → `muse-spark`; `kimi-k2.5` → `kimi-k2.5-thinking`.

Impact: `lmarena_rank/elo/votes` feed `z_elo` (weight 0.15) and the HTML "LMArena" column (2212) shows **only rank+ELO with no matched-name disclosure** — the reader has no way to notice `glm-5.3-flash`'s ELO is actually `glm-5`'s. Effort-variant ELOs (max/xhigh) differ materially from base configs.

Fix direction: mirror C1's token guard; additionally store/display the matched arena name next to the ELO so mismatches are visible even when heuristics err.

### 🔴 C3 — LiveBench: version digits stripped before fuzzy match + stale entries from 7-month-old CSVs merged in unconditionally
**File:643-647 (digit filter 643), merge loop 1654-1666 · Priority P1 · Confidence 0.92 · Critical**

Mechanism (two compounding defects):
1. The token fallback filters out **every pure-digit token** (`not t.isdigit()`), which is exactly where model versions live: `qwen3.7-plus` → tokens `["qwen3","plus"]` (the "7" is dropped) → first slug containing both → `qwen3.6-plus`.
2. The merge loop `live_map.update(data)` folds *all* `livebench_*.csv` snapshots oldest→newest, so entries retired from current leaderboards persist forever (merged map = 150 entries from `20260108`/`20260625`/`20260827`).
3. Any per-CSV parse exception is swallowed with `except Exception: pass` (1665-1666) — zero signal on corruption.

Evidence (probe): `mimo-v2.5` → `mimo-v2-pro` overall **58.35, sourced from livebench_20260108.csv; the entry is absent from the 20260827 leaderboard** (wrong model + stale score); `qwen3.7-plus` → `qwen3.6-plus` (68.99); `qwen3.5-plus` → `qwen3.6-plus` (wrong version); `gpt-5.6-luna` → `gpt-5.6-luna-max`; `kimi-k2.6` → `kimi-k2.6-thinking`.

Impact: the matched record is embedded verbatim in `ocgo_live.json` (1868) and its `overall` carries composite weight 0.20 (1920-1921). Three current models (mimo-v2.5, mimo-v2.5-pro, qwen3.5-plus) receive *no* correct LiveBench score in any CSV, so **any** fuzzy hit is by definition fabricated data for them.

Fix direction: use the newest CSV only (fall back to older only for keys missing there, marking provenance); never drop digit tokens (compare `qwen3` + `7` jointly — e.g. split `([a-z]+)([0-9.]+)` family/version); log skipped files.

### 🔴 C4 — `_find_key_recursive` can send a third-party provider credential to opencode.ai as the Bearer token
**File:691-704 + 725-731, consumed at 740 · Priority P1 · Confidence 0.7 · Critical-conditional (credential confidentiality)**

Mechanism: when the targeted lookups miss, `get_api_key` runs `_find_key_recursive` over `~/.local/share/opencode/auth.json` — **opencode's multi-provider credential store** (each user provider is an entry such as `{"<provider>": {"type":…, "key"/"token": …}}`). The helper returns the first string value under any key containing `key`/`token`/`secret` in **file insertion order**, with no provider check. `fetch_usage` (740) then sends it as `Authorization: Bearer …` to `OCGO_USAGE_API`. A user whose auth.json lists e.g. Anthropic or GitHub-Copilot before any opencode entry leaks that provider's credential to a third-party endpoint on every live run. The sibling path for `~/.pi/agent/auth.json` (718-722) does it right — it targets the `opencode-go`/`opencode` entries explicitly — proving the recursive hunt is an oversight, not design.

Scope-1 host check: this machine's file contains only `opencode-go` (structure-only inspection, no values read), so no current local impact; the defect is the code path under standard multi-provider usage.

Fix direction: replace lines 725-733 with the same targeted `d.get("opencode-go") or d.get("opencode")` lookup used for pi's auth.json; delete `_find_key_recursive`. Secondary note: `--key` (1444, 708) puts the secret in `argv`, visible in process listings — prefer env-only.

### 🟠 M1 — first_seen/NEW-badge self-expiry invariant violated for non-docs models: re-stamped "brand new" every run
**File:2010-2013, 2058-2077; mechanism in `benchmark_common.py:1365-1367` + `ocheck:1396-1399` (bc diff) · Priority P2 · Confidence 0.97 · Moderate**

Mechanism: the invariant (project memory: *"diff runs catalog-wide BEFORE pool filtering; NEW renders green 7d then self-expires"*) is honored in *placement* (line 2013 diffs `rows_sorted` full catalog) — but `diff_model_catalog` skips baseline entries lacking `is_docs_model` when the snapshot has `catalog_diff` (bc:1366). Non-docs rows therefore never find themselves in `prev_models_map` → `is_brand_new=True` (bc:1396) → `first_seen` re-stamped to *now* and `is_new=True` **permanently**, every run.

Evidence (P7): identical 6 legacy models (`mimo-v2-pro`, `hy3-preview`, `mimo-v2-omni`, `qwen3.5-plus`, `glm-5`, `kimi-k2.5` — all pre-existing `FALLBACK_PRICING` keys) show `is_new: True` at HEAD (2026-08-27 run) and again at 2026-08-30 run with `first_seen` equal to the new run's clock. Fake *removals* are correctly prevented (the same filter protects `removed`), and `removed=[]` today is accurate — but `catalog_diff.total_previous: 34` vs `total_current: 28` (2073-2074) compares the full baseline against the docs subset: an inconsistent pair written every run.

Fix direction: in the catalog-wide pass, index prev by id *without* the docs filter for first_seen carry-over; keep the `is_docs_model` filter only for the added/removed display pass; align `total_previous` to the docs subset.

### 🟠 M2 — no atomic write for the tracked baseline or reports: partial write silently erases diff history
**File:2081, 2088, 2095 (outputs); 1492, 1513, 1591, 1614, 1637 (snapshots) · Priority P2 · Confidence 0.9 · Moderate**

Mechanism: all artifacts use `Path.write_text` directly. A crash/ENOSPC mid-write of `docs/data/ocgo_live.json` leaves truncated JSON; next run `load_previous_snapshot` swallows the parse error (`benchmark_common.py:1283-1286` → `None`) → the run proceeds as a cold start: every `first_seen` re-initialized, `added`/`removed` empty, previously-removed models never reported again. No warning distinguishes "no baseline" from "corrupt baseline". The file is git-tracked, so a truncated intermediate can be committed by automation.

Fix direction: `tmp = path.with_suffix(path.suffix + ".tmp"); tmp.write_text(...); os.replace(tmp, path)`; on corrupt-but-existing baseline, emit a loud WARN.

### 🟠 M3 — "Live check" label with silent stale-snapshot substitution and no age warning; `fetch()` has no retry
**File:161-172 (fetch), 1596/1619/1642 (fallbacks), 2240 (HTML subtitle) · Priority P2 · Confidence 0.85 · Moderate**

Mechanism: any fetch exception → `None` (170-172, no retry/backoff); parsers returning `{}` (including the realistic 200-but-challenge-page case — AA behind a bot wall returns HTML with no `"models":[` array) fall through to `pick_latest_raw` and use whatever snapshot exists — here 3 days old — with no age banner. bcheck enforces a 24h staleness warning; ocheck prints only the filename. The HTML report still titles itself "Live check" with today's date (2115, 2240) while pricing/benchmarks may be days stale. Also: pricing live-vs-snapshot transitions differ per source independently (docs could be fresh while AA is 3-day-old), and `parse_ocgo_docs` positional assumptions (tables[0]/tables[1], 185/226; literal `"requests per month"` anchor, 247) mean an upstream layout change degrades to 7/21-stale `FALLBACK_PRICING`/`FALLBACK_TOKENS` (73-105, 119-151) with only a `WARN` on stderr — a mispriced report still writes.

Fix direction: share bcheck's snapshot-age gate (>24h → banner in CLI *and* HTML header); one retry on transient errors.

### 🟡 m1 — `--out` is a dead flag
**File:1471-1472 vs 2079-2095 · Priority P3 · Confidence 0.95**
`out_dir = Path(args.out)` is created but never used: JSON goes to `DATA`, cost-benefit JSON/HTML go to global `OUT` (2086-2094). `--out override output dir` (1443) silently does nothing.

### 🟡 m2 — `--check --fetch` still writes files while printing "no files written"
**File:1465, 1490-1493/1511-1514/1589-1592/1612-1615/1635-1638, 2099 · Priority P3 · Confidence 0.95**
Snapshot writes are gated on `do_fetch` only, but the help (1441) promises "do not write outputs" and the run concludes `(check-only, no files written)`.

### 🟡 m3 — `norm_id` diverges from `bc.norm_id` (dots→hyphens, no None guard) and shadows it
**File:46 (import) + 381-382 · Priority P3 · Confidence 0.85**
Nine names imported from `benchmark_common` (40-54) are redefined later in the module (`norm_id:381, parse_aa:385, parse_openrouter:487, parse_livebench:564, _safe_float:659, _safe_int:676, _safe_int_round:683, display_len:784, color_cell:796`) — the imports for these are dead code, and the local `_safe_float` rejects `"$"`-prefixed values (668) while bc's strips them (documented intentional divergence, kept on purpose 2026-08-27). Not triggerable to a crash through ocheck's own call graph today (all `norm_id` inputs are guarded strings), but the shadowing invites the next "fix bc's parser" patch to land in the wrong function: `bc.parse_aa` improvements are invisible to ocheck unless its local copy is edited separately — the exact silent-breakage class that bit this repo on 2026-08-27 (project memory). Fix direction: delete the nine dead import entries (or rename locals) so shadowing is explicit.

---

## Dimension notes

1. **Correctness — parsers:** record-loss hypothesis refuted for AA/OR/LiveBench/docs on all current snapshots (P1-P4: 0 dropped). Tier dedupe verified to keep the cheaper row. Cost math: no division-by-zero reachable (`cost_req>0` guard 1754; truthy guards 1791-1793; `compute_token_multiplier` clamps p≥0.02 → t_mult≥1, no 1951 div-zero; `parse_price` handles `$`/em-dash). Unknown-new-model default (1571) hardcodes `usage: 60` for API ids missing from both docs pricing and fallback — not triggered by today's catalog (all 4 new models priced from docs, verified in artifact) but would silently misprice the caps if a docs row fails `model_to_id`.
2. **Robustness:** no crash-loop with zero raw files or corrupt snapshot JSON (P8); usage-API percent fallback chain (1686) ambiguously mixes `percent`/`usedPercent`/`used` units — unverifiable offline, worth a schema check against the live API next session.
3. **Performance:** whole-file buffering measured acceptable: `parse_aa` 0.40 s / 4.6 MB; fuzzy loops 34×623 (AA), 34×396 (OR) — O(n·m) with n=34 is trivial; pareto O(n²) n=28. Live mode re-fetches 4.6 MB AA + 2.7 MB Arena per invocation by design (it *is* the live checker). No finding.
4. **Security:** stored-XSS hypothesis **refuted** — `model_id` (2122), `aa_slug` (2164), removed names (2222), title/work sentence (2239/2263) all pass `html_lib.escape`; hostile-input render probe shows escaped-only (P6); no `eval/exec/subprocess/shell` anywhere; all URLs hardcoded https; `--fetch` integrity risk limited to generated artifacts (M3), no code-execution path (generic `model_to_id` fallback 376-377 constrains scraped ids to `[a-z0-9.-]+`). Residual risk is C4 (credential routing), not HTML.

## Invariant compliance

| Invariant | Status |
|---|---|
| Diff runs catalog-wide before pool filtering | Placement honored (2013); **first_seen still re-stamped for non-docs (M1)**; `total_previous/total_current` compare different sets (2073-2074) |
| NEW badge shows ≤7d then self-expires | **Violated for 6 non-docs models: permanent `is_new=True` (M1)**; docs models correct |
| No fake-REMOVE from subset diff | Honored — `is_docs_model` prev-filter (bc:1366) blocks it; `removed=[]` verified accurate |
| Scraped strings never enter HTML unescaped | Honored (P6) |
| Baseline JSON integrity | At risk under crash (M2) |

## Test-coverage gaps
- `test_catalog_diff_logic` (tests:89-123) uses only `is_docs_model: True` prev entries → cannot catch M1.
- No test pins AA/LMArena/LiveBench matcher results to *specific* expected slugs per catalog model → C1-C3 regressions invisible; recommend a golden match table (exact tier only) + "ambiguous ⇒ None" assertions.
- No atomicity/round-trip test for `ocgo_live.json` (M2).

## Remediation backlog
**P1 (this cycle):** C1+C2+C3 shared fix — one variant-guarded matcher utility used by all three finders (reject suffix-variant contains; keep digits in token matching; newest-CSV-only with provenance); C4 targeted provider-key lookup; M2 atomic writes + corrupt-baseline WARN.
**P2 (next):** M1 first_seen carry-over fix; M3 staleness banner + retry; C3 stale-merge purge; golden match-table tests.
**P3:** m1/m2 flag fixes; m3 dead-import cleanup; 1571 unknown-model default — require explicit pricing instead of `usage: 60`.
