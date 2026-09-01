# Scope 3: Cost Analyzers Audit Report (ocheck / ccheck)

**Date:** 2026-09-01
**Target Files:**
- `checkers/opencode_cost_benefit_analyzer.py` (2189 lines, `ocgo_check.py`)
- `checkers/commandcode_cost_benefit_analyzer.py` (1179 lines, `cc_check.py`)
- `checkers/test_opencode_cost_benefit_analyzer.py` (15 tests)
- `checkers/test_commandcode_cost_benefit_analyzer.py` (12 tests)
- Supporting: `checkers/benchmark_common.py`

**Method:** `mimori slice` on `main`/`parse_ocgo_docs`/`parse_cc_docs` + targeted `read_file`, live offline runs of both checkers (`--check --plain`) against the 20260901 snapshot set, direct reproduction of the scoring path, and full test-suite runs. No subagents spawned.

**Health Score: 7.8 / 10 (Moderate)** — ccheck: 8.8; ocheck: 7.2.

---

## 1. Executive Summary

Both checkers are structurally sound: offline-by-default, pure stdlib, snapshot staleness labeled from filenames, atomic snapshot writes, fail-fast with loud WARNs (no silent `except Exception: pass` swallow sites remain), and both suites pass (27/27). The invariant "every limits view must label usage provenance" holds in code and live output (`usage: rolling 1% used ... [cached ocgo_usage_20260901.json]`).

**One critical correctness defect is live and confirmed:** `ocheck` fabricates benchmark scores for models with **zero** cross-source coverage. `compute_capability_q(cz=0.0)` returns the z=0 center `78.0`, so a completely unscored free model (`ox-alpha-free`) renders as `Q(Cap)=78.0 · P(Succ)=67.3% · AVI=825.8` with a **🥇 AVI column medal** and joins the **Pareto frontier** (gold-bold) as *undominated* — a phantom ranking that beats genuinely scored models. `ccheck` contains the identical historical bug, was fixed with an explicit guard (cc lines 885–905, covered by `test_unscored_models_sort_last_and_show_dash`), and its live output shows `—` for the same class of model. The fix is known, proven, and simply was never ported back to ocheck.

No invariant breaches found in the scope of this audit (usage provenance, offline default, `--check` never writes, env-only keys, stdlib-only, no swallowed exceptions). The prior audit's `except Exception: pass` sites (ocheck ~1612/1663/1686–1695) have all been narrowed to `except (ValueError, TypeError)` or converted to logged WARNs.

### Dimension Scores

| Dimension | ocheck | ccheck |
| :--- | :---: | :---: |
| Correctness (parsing, ID norm, cost math, quotas, QVI/AVI/FGI) | 7.0 | 9.0 |
| Robustness (offline, staleness, malformed HTML, error isolation) | 8.8 | 9.0 |
| Performance (parsing throughput, memory) | 9.5 | 9.5 |
| Security (key handling, path safety) | 9.0 | 9.5 (no keys) |
| Complexity (main() CC, bug-coupling) | 7.0 | 8.0 |

---

## 2. Top Findings

### F1 — CRITICAL: ocheck fabricates scores for uncovered models → phantom rankings + Pareto pollution
**File:** `checkers/opencode_cost_benefit_analyzer.py`
**Lines:** [1785–1807](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/opencode_cost_benefit_analyzer.py#L1785-L1807) (weighted composite: `tot_w = sum(weights) or 1.0; cz = sum(z_parts) / tot_w if weights else 0.0; q_score = compute_capability_q(cz)`), driven by [1799–1801](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/opencode_cost_benefit_analyzer.py#L1799-L1801).

**Evidence (live offline run, 2026-09-01 snapshots):**
```
#28 ox-alpha-free    Free   —   —   78.0   67.3%   —   0.0  825.8¹  43.1   —   —
```
- `compute_capability_q(0.0)` = `78.0` (bc [284–291](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/benchmark_common.py#L284-L291)) — the z=0 center, semantically "average model", here meaning "no data".
- Downstream: `p_success=67.3`, `t_mult=2.07`, `AVI=825.8` — reproduced deterministically in a standalone script; the 🥇 AVI medal comes from `compute_column_medals` over the row set.
- Pareto sweep (`cand` includes rows with `capability_q is not None`, [1875](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/opencode_cost_benefit_analyzer.py#L1875)): reproduced `ox-alpha-free` as **undominated** at (cost=0.0, Q=78.0) against glm-5.3/mimo-v2.5 → gold-bold frontier membership.
- Because `ox-alpha-free` has no price, `_eff_cost` gives it `0.0` (real-cost rule [1860–1861](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/opencode_cost_benefit_analyzer.py#L1860-L1861)), which is correct *only if* its score is genuine — it isn't.
- `role recommendations` pick `muse-spark-1.2-contributor` (Q=78, TPS-heavy) as "Fast Boilerplate" — Q=78 is itself the unscored center bleeding into a scored-looking row for a real model that only has TPS coverage. Same root cause.

**Known-fixed in sibling:** ccheck [885–905](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/commandcode_cost_benefit_analyzer.py#L885-L905) (`if not weights:` → set every Q/AVI/FGI/P score to None, `continue`), tested by `test_unscored_models_sort_last_and_show_dash` (cc test [141–159](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/test_commandcode_cost_benefit_analyzer.py#L141-L159)). Not ported to ocheck.

---

### F2 — HIGH: ocheck usage percent unit mismatch — "79% remaining" rendered when 79% is *used*
**File:** `checkers/opencode_cost_benefit_analyzer.py`
**Lines:** [1679–1701](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/opencode_cost_benefit_analyzer.py#L1679-L1701) (remaining built from `usage_percents`), display [798–812](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/opencode_cost_benefit_analyzer.py#L798-L812), header label at [665–669](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/opencode_cost_benefit_analyzer.py#L665-L669) and [677–686](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/opencode_cost_benefit_analyzer.py#L677-L686).

**Evidence (live offline run):** `usage: rolling 1% used, weekly 0% used, monthly 79% used` (cached `ocgo_usage_20260901.json`), yet every row's Remain column shows **`21%(…)`**. The cached payload (raw `ocgo_usage_20260901.json`) is `percent: 79` for monthly = **used**, and the code *correctly* computes `pct_rem = 100 − pct_used` for the internal `remaining[]` — but the **header label** "Remain" (percent) plus the row format `{overall:.0f}%` [803](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/opencode_cost_benefit_analyzer.py#L803) and the color gate `overall > 50 → green` [849](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/opencode_cost_benefit_analyzer.py#L849) all read naturally as *remaining*. With 79% of the monthly quota already consumed, showing a green `21%` in a "Remain" column is a materially misleading signal for quota planning — the only way to catch it is to cross-read the header line above the table.
**Suggested one-line fix:** display `Remain: {overall:.0f}%` → `{100-overall:.0f}% used` (or label the column "Used"), and note it in the metric guide. The `render_limits_table` variant already does the math correctly (balance = `w_cap * (100−used)/100`).

---

### F3 — MEDIUM: ccheck `--fetch` never fetches (and no offline-write discipline for it)
**File:** `checkers/commandcode_cost_benefit_analyzer.py`
**Lines:** [661–684](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/commandcode_cost_benefit_analyzer.py#L661-L684).

The `--fetch` branch only ever runs when `pricing_live` is empty (the `if not pricing_live:` guard at [686](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/commandcode_cost_benefit_analyzer.py#L686) is checked after the fetch block, but the fetch block *itself* is conditioned on `if do_fetch:` **and** the docs fetch is inside it, so the code path exists). Verified issue: OpenRouter/AA/LMArena are fetched **only when `do_fetch` and the writes go to raw/ unconditionally when `do_write`** — this part is fine — **but** there is no `--fetch`-only gating of the *docs* re-parse, and more importantly the checker has **no usage endpoint at all** (GOAT has no public usage API in scope), so `--fetch` fetches 4 URLs with a UA header and no keys — safe, but the CLI help overstates parity. The real divergence is the **contract drift**: like ocheck, ccheck writes `cc_live.json`/`cc_cost_benefit.json`/HTML on **every run unless `--check`** — the module docstring admits this is intentional drift vs bcheck/fcheck/scheck ([18–19](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/commandcode_cost_benefit_analyzer.py#L18-L19)). Combined with the stale baseline it is a write-on-run-every-time behavior that repeatedly mutates tracked files (see F4).

---

### F4 — MEDIUM: O(n²) cross-matcher on every row build (perf), plus baseline-write churn
**File:** `checkers/opencode_cost_benefit_analyzer.py`
**Lines:** [1601–1613](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/opencode_cost_benefit_analyzer.py#L1601-L1613).

For every model with `None` pricing, the loop iterates **all 425 OpenRouter records** with a substring test per record (`norm_id(mid) in norm_id(or_id) or ...`), and the same O(n·m) pattern runs through `find_aa_for_ocgo`/`find_lm_for_ocgo`/`find_livebench_for_ocgo` (all bc `norm_model_slug`-based, [831–877](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/benchmark_common.py#L831-L877) etc.). Measured end-to-end runtime is still only **~1.0s** (52 MB RSS, both checkers) because the catalogs are small; this is a scaling hazard, not a current bottleneck — P3.

Also confirmed: `main()` writes `ocgo_live.json` on every non-`--check` run, so `docs/data/ocgo_live.json` and the three report outputs are **modified in the worktree on every invocation** (git status shows them dirty) — the exact contract drift flagged in the prior scope-2 audit (checker_scope_2_ocheck.md F3) and still open.

---

### F5 — LOW: `--podium` and `--json`/`--html` flags are no-ops in both checkers
**Files:** ocheck [1309–1314](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/opencode_cost_benefit_analyzer.py#L1309-L1314), ccheck [637–639](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/commandcode_cost_benefit_analyzer.py#L637-L639).
`--podium` is accepted and never referenced; `--json`/`--html` are documented in ocheck's help as "Output to docs/data/…" but outputs are written regardless of the flags (only `--check` gates writes). Harmless but misleading CLI surface; cc's help text already admits it ("Accepted for parity").

---

## 3. Verified-OK Items (regression sweep vs prior audit)

- **No `except Exception: pass` swallow sites remain.** Prior-audit lines ~1612/1663/1686–1695 are now `except (ValueError, TypeError)` with `continue`/`pass` in narrow conversion contexts; all network/parse failures print loud `WARN … <e>` to stderr ([204–206](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/opencode_cost_benefit_analyzer.py#L204-L206), [1387–1388](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/opencode_cost_benefit_analyzer.py#L1387-L1388), [1460–1461](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/opencode_cost_benefit_analyzer.py#L1460-L1461), etc.). The prior "swallowed exception" finding is **resolved**.
- **Variant-matching fixed**: `find_or_for_ocgo`/`find_aa_for_ocgo`/`find_lm_for_ocgo`/`find_livebench_for_ocgo` are now bc aliases ([429–436](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/opencode_cost_benefit_analyzer.py#L429-L436)) using `norm_model_slug` + `variant_conflict` ([831–877](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/benchmark_common.py#L831-L877)); the scope-2 naive-substring finding (checker_scope_2_ocheck.md F1) is resolved.
- **Cached-write cost now modeled**: `compute_cost` takes `cached_write_per_1m` ([439–445](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/opencode_cost_benefit_analyzer.py#L439-L445)); both checkers pass it (cc always `est_cached_write=0`; oc merges `cw` from docs). Scope-2 F2 resolved. Note: oc's `compute_cost` is called without the write price at [1619](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/opencode_cost_benefit_analyzer.py#L1619) — cached writes never actually enter ocheck's per-request cost (est_cached_write defaults 0) — cosmetic, P3.
- **Usage provenance invariant holds**: `usage_note` is `"live (fetched now)"` or `f"cached {name}{staleness_tag}"` or absent; every render path (CLI header [715](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/opencode_cost_benefit_analyzer.py#L715), limits table [990](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/opencode_cost_benefit_analyzer.py#L990), HTML [2130](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/opencode_cost_benefit_analyzer.py#L2130), JSON `usage_source` [1950](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/opencode_cost_benefit_analyzer.py#L1950)) carries it. No bare percentages without provenance.
- **Keys are env/agent-store only, never logged or written**: `get_api_key` reads `OPENCODE_GO_API_KEY`/`OPENCODE_API_KEY`/`OPENCODE_GO_KEY` then targeted `~/.pi/agent/auth.json` / opencode auth stores with a *provider-scoped* lookup (`_lookup_provider_key` reads only the `opencode-go`/`opencode` entry, [480–494](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/opencode_cost_benefit_analyzer.py#L480-L494)) — never dumps the store, and the usage snapshot write ([1556–1557](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/opencode_cost_benefit_analyzer.py#L1556-L1557)) stores only the numeric `usage` object, no Authorization header content. `fetch_usage` failure messages carry HTTP status and a 200-char body slice, never the key ([543–550](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/opencode_cost_benefit_analyzer.py#L543-L550)). ccheck needs no key at all.
- **Snapshot writes are atomic + dated**: `bc.atomic_write_text` (tmp sibling + fsync + `os.replace`, bc [147–163](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/benchmark_common.py#L147-L163)); filenames embed `YYYYMMDD`; staleness is judged from the **filename date**, not mtime (bc [218–266](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/benchmark_common.py#L218-L266)); >24h sources produce the WARN banner in `offline_data_note()` ([69–92](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/opencode_cost_benefit_analyzer.py#L69-L92)). Path safety: all snapshot paths are constructed from `RAW = ROOT/docs/data/raw` plus fixed name parts — no user-controlled path components.
- **Malformed-HTML tolerance**: table selection is header-phrase matched (`_table_with`), not positional ([221–229](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/opencode_cost_benefit_analyzer.py#L221-L229)); both test suites include header-matched fixtures (oc test [261–278](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/test_opencode_cost_benefit_analyzer.py#L261-L278), cc test [92–107](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/test_commandcode_cost_benefit_analyzer.py#L92-L107)). Parsers return empty dicts on garbage (no crash).
- **Error isolation**: every snapshot loader is wrapped in try/except with a stderr WARN and falls back to the next source / FALLBACK_PRICING (oc [1392–1516](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/opencode_cost_benefit_analyzer.py#L1392-L1516)); corrupt LiveBench CSVs are skipped loudly, never silently (oc [1521–1535](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/opencode_cost_benefit_analyzer.py#L1521-L1535)).
- **Quota math**: cap scaling `cap_5h = usage × (12/60)`, `cap_wk = usage × 0.5`, `cap_mo = usage` (oc [1622–1627](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/opencode_cost_benefit_analyzer.py#L1622-L1627)); cc uses `credits × 14/70`, `× 35/70`, `credits` ([786–789](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/commandcode_cost_benefit_analyzer.py#L786-L789)) — both consistent with docs, and cc's `test_cost_sanity_against_docs_requests` cross-checks computed request counts against documented values (cc test [36–45](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/test_commandcode_cost_benefit_analyzer.py#L36-L45)).
- **`_safe_float` strictness divergence is intentional and documented** (memory.md S1-M3 note, module comments oc [54–61](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/opencode_cost_benefit_analyzer.py#L54-L61)); `parse_price` handles `$`/`,`/`—` in docs tables. Not a defect.
- **ccheck's unscored-guard is itself a correctness win** (F1's fixed side): verified live — `deepseek-v4-flash-fast`, `glm-5.2-fast`, `laguna-s-2.1-free`, `muse-spark-1.2-contributor`, `qwen-3.7-flash` all render `—` and sort last, and `test_unscored_models_sort_last_and_show_dash` locks it.

---

## 4. Performance Notes

- End-to-end offline runs: **ocheck ~1.03 s, ccheck ~0.4 s** (52 MB RSS), both `--check --plain`. Parsing (regex table extraction, AA 625 entries, OR 425, LM 120, LiveBench 150) is sub-100 ms; the O(n·m) matchers and the pareto sweep are negligible at current catalog sizes. No memory issue (single-pass row build; snapshots streamed per-file).
- F4's O(n·m) matcher loops are the only scaling smell; with 10× catalog growth the per-row OR scan becomes the hot path. Precompute a `norm_model_slug → record` index once per run (P3).

---

## 5. Complexity

- ocheck `main()` spans [1301–1984](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/opencode_cost_benefit_analyzer.py#L1301-L1984) (~680 lines, CC-class 139–205 per prior audits); ccheck `main()` [633–1012](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/commandcode_cost_benefit_analyzer.py#L633-L1012) (~380 lines). Verified current state: **both mains are still oversized**, and the complexity now demonstrably couples to real bugs:
  - F1 exists because the scoring block was appended to `main()` without the coverage guard that the sibling module added when *its* same code was fixed — the duplicated ~200-line scoring/merge block in two files has already drifted (one has the guard, the other doesn't).
  - F2's unit inversion lives in the same long block (`remaining` built at [1679–1701](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/opencode_cost_benefit_analyzer.py#L1679-L1701), displayed ~200 lines later with no shared constant for "used vs remaining").
  - Recommendation: extract `build_rows()` + `score_rows()` into module-level functions (mirroring cc's guard), and add a `--json`/`--html`/`--podium`-free write gate. This is a **P2 maintainability** item with a **P1 correctness** sub-item (port the guard).

---

## 6. Remediations

### P1 (correctness — do first)
1. **Port ccheck's no-coverage guard to ocheck** (`opencode_cost_benefit_analyzer.py:1799`): when `weights` is empty, set `capability_q`, `p_success`, `token_multiplier`, all `effective_*`, `qvi/avi/fgi/bfi` to `None` and `continue`, mirroring cc [885–905](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/commandcode_cost_benefit_analyzer.py#L885-L905). Add ocheck's own `test_unscored_models_sort_last_and_show_dash`-style test (assert `ox-alpha-free` renders `—` and never wins a medal / never joins pareto). This removes the fabricated Q=78/AVI=825.8/🥇 and the phantom Pareto member.

### P2 (correctness/UX — next release)
2. **Fix the Remain column unit inversion** (`opencode_cost_benefit_analyzer.py:798–812` + header): either relabel the column "Used" and show `pct_used`, or keep "Remain" and format `(100−pct_used)%` with a distinct marker; update `_pct_color` gating and the metric guide so the semantics are self-evident. The raw 20260901 snapshot shows monthly 79% used → today's table shows green `21%`, which is read as 21% remaining.
3. **Extract the `main()` scoring/merge block** into module-level `build_rows()`/`score_rows()` in both files so the coverage guard can never drift again; add the extraction to both test modules.

### P3 (hygiene — backlog)
4. **Stop unconditional output writes**: honor `--json`/`--html` in both checkers (or accept `--podium`), so a plain `python3 …/analyzer.py` run doesn't dirty `docs/data/*_live.json` + `docs/reports/*` on every invocation (currently mutates tracked files even in offline mode). Note the intentional-drift comment in cc's docstring should be resolved in the same change.
5. **Precompute a normalized-slug index** for `find_*_for_*` and the OR pricing fallback loop (`opencode_cost_benefit_analyzer.py:1601`) to remove the O(n·m) scan (today ~1 s total, so low urgency).
6. **Pass `cached_write_per_1m` into ocheck's `compute_cost` call** ([1619](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/opencode_cost_benefit_analyzer.py#L1619)) so docs cached-write prices actually enter per-request cost, or delete the now-unused parameter from the call to avoid the false impression it is modeled.

---

## 7. Prior-Audit Reconciliation

| Prior finding (checker_scope_2_ocheck.md) | Status |
| :--- | :--- |
| Naive substring OR matching (L583–584) | **Resolved** — bc aliases with `variant_conflict` |
| Missing cached-write cost factor (L680–685) | **Resolved** — `compute_cost` models it (oc call still passes 0 — see P3-6) |
| CLI contract drift: always writes unless `--check` | **Still open** (documented drift) — see F4/P3-4 |
| Duplicate shadowed primitives | **Won't fix by design** — intentional, documented local contracts (memory.md S1-M3) |
| `except Exception: pass` swallow sites (~1612/1663/1686–1695) | **Resolved** — narrowed to `(ValueError, TypeError)` or logged WARNs |

---

## 8. Verdict

| Tool | Health | Assessment |
| :--- | :---: | :--- |
| ocheck | 7.2 / 10 | Sound architecture and invariants; one critical fabricated-score bug + one misleading quota display. |
| ccheck | 8.8 / 10 | Clean, tested, guard present; CLI/write drift and no-usage-provenance are its only marks. |
| Combined | **7.8 / 10 (Moderate)** | Port the proven guard; fix the Remain unit; extract the shared scoring block. |

**Bottom line:** the two files are the same program with a known fix applied to only one half. The top remediation is a ~15-line port plus one test.
