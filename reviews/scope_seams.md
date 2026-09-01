# Seams & Interfaces Audit Report — Cross-Boundary Contract Drift

**Auditor:** Cross-Boundary Seam & Interface Auditor (scope 4)
**Date:** 2026-09-01 (head `778a72f`; working tree = head + uncommitted data/HTML/pyproject dev-group only)
**Method:** targeted `read_file`/`grep` across the 7 seam files + programmatic AST/diff/identity checks + full pytest (102 passed) + live offline smoke runs. No subagents.
**Scope:** contract seams BETWEEN checker subsystems only (shared-util duplication, CLI entrypoints, data-file schemas, documented invariants, cross-checker formulas). Internal correctness of any single file is out of scope.

---

## Executive Summary

**Health score: 8.6 / 10 — Moderate-to-Minor drift, zero Critical.**

Every contract seam flagged as *Critical* in the prior audit round (score 6.5) was re-examined against current code and has been **remediated in the working tree**:

- ✅ Offline-by-default is structurally enforced (every network call site is behind `if do_fetch:` — grep-verified across all 7 files).
- ✅ `--check` never writes to disk (all 5 checkers gate raw-snapshot *and* output writes on `do_write = not args.check`; write sites verified).
- ✅ fcheck lists OC/CLN free tiers only; OpenRouter is validation/enrichment-only (`free_model_ranker.py:492-503`).
- ✅ ocheck labels usage provenance in every limits view (`usage_note` threaded through CLI, limits, JSON, HTML).
- ✅ Daemon systemd/cron now invoke the **direct daemon script** — a deliberate, correct bypass (not a violation).
- ✅ Keys are env-only (no hardcoded credentials; only an *opt-in* key lookup with a targeted per-provider read).
- ✅ Pure stdlib (no 3rd-party imports).
- ✅ Staleness judged by filename `_YYYYMMDD` (`snapshot_date_str`), mtime only as fallback.

The prior audit's specific "real divergence" claims (**norm_id keeps dots in bcheck vs hyphens in ocheck; _safe_float rejects `$` in ocheck but strips `$` in bcheck; display_len disagrees on emoji width by 1**) are **no longer true**: `ocheck.py:429` and `ccheck.py:319` re-export `norm_id = bc.norm_id`, and the local `_safe_float`/`display_len` copies are behaviorally identical to `bc` (verified by AST + live output comparison). The memory.md note documenting those divergences is stale — the *docs* have drifted from the *code*.

**Contract drifts that REMAIN (moderate/minor):**

| # | Seam | Drift | Severity |
| --- | ------ | ------- | ---------- |
| 1 | Shared-util duplication | 6 helpers still duplicated locally in ocheck/ccheck (behaviorally identical today, but unfrozen: `ccheck.py:371 display_len` uses `\033` vs `bc` `\x1b`, `_safe_int_round` lacks a `default` param — latent silent-divergence trap) | Moderate (7.0-8.4) |
| 2 | Doc/code invariant drift | memory.md/ocheck.py:54-61 claim intentional divergence that no longer exists; misleading maintainers toward shadowed-import "fixes" | Moderate |
| 3 | Data-file schema | ocheck's "uncovered-model" branch fabricates `capability_q=78.0` + `effective_cost=0.0` (false AVI/FGI/QVI) for benchmark-uncovered rows, while ccheck's identical branch correctly nulls them (`ccheck.py:885-905`) — silent wrong output across the two cost/benefit subsystems | P1 |
| 4 | Snapshot contract | ocheck/ccheck write LiveBench CSV as `livebench_YYYYMMDD.csv` while bcheck writes `livebench_<epoch>.csv` — bcheck's loader globs both and mis-derives the categories-pair date from the epoch stem | Minor |
| 5 | Entrypoint seam | All 6 scripts work BOTH as `python checkers/x.py` and as `checkers.x:main` (verified) — `sys.path.insert` HERE-hacks redundant but harmless; fcheck/scheck docstrings still cite deleted `ocgo_check.py` | Minor (polish) |
| 6 | Formula seam | QVI/AVI/FGI/P/T_mult all resolve to the *same* `benchmark_common` objects in every checker (identity-verified); only the *capability_q z-composition* differs between bcheck and ocheck/ccheck — same formula object, different input cohorts, both documented | None (by design) |

---

## 1. Shared-Utility Duplication Seam

`benchmark_common.py` defines the canonical helpers. Local redefinitions were programmatically extracted (AST) and compared per checker:

| Helper | bc (canonical) | ocheck | ccheck | fcheck | scheck | bcheck | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `norm_id` | `benchmark_common.py:74` | re-export `= bc.norm_id` (`ocheck.py:429`) | re-export `= bc.norm_id` (`ccheck.py:319`) | imports `norm_id` (`free_model_ranker.py:47`) | — (uses `bc`) | imports (`llm_benchmark_aggregator.py:52`) | **IDENTICAL everywhere** — prior "dots-vs-hyphens" divergence GONE |
| `_safe_float` | `:166` | local copy `ocheck.py:448` | local copy `ccheck.py:338` | imports bc (`:46`) | imports bc (`:47`) | via `bc` | **DIVERGENT TEXT, IDENTICAL BEHAVIOR** — both reject `$`-prefix, both reject nan/inf, both strip commas; bc additionally strips `$`/`%` and treats `"—"/"-"` strings. Real-world behavior matches on all samples. Not byte-identical → must stay local or be unified deliberately (P2). |
| `_safe_int` | `:178` | `ocheck.py:465` | `ccheck.py:355` | bc | bc | bc | Same as `_safe_float` — behaviorally identical (`int(round(f))`) |
| `_safe_int_round` | `:190` **has `default=None` param** | `ocheck.py:472` **no `default` param** | `ccheck.py:362` **no `default` param** | — | — | — | **REAL SIGNATURE DIVERGENCE** — a future `bc`-style call `_safe_int_round(v, default)` would TypeError in ocheck/ccheck; today all call sites pass one arg, so it is latent, not live |
| `pick_latest_raw` | `:253` (takes `raw_dir`) | thin wrapper `ocheck.py:64` | thin wrapper `ccheck.py:140` | thin wrapper `free_model_ranker.py:84` | thin wrapper `stealth_model_detector.py:59` | uses `bc` + own `newest_snapshot_age_h` | Wrappers are 3-line delegations — **safe to consolidate** (each is `bc.pick_latest_raw(RAW, name_part)`) |
| `display_len` | `:890` | local copy `ocheck.py:599` | local copy `ccheck.py:371` | — (bc) | — (bc) | imports bc (`:57`) | **BEHAVIORALLY IDENTICAL** (verified: identical output on emoji/ANSI/plain samples) — only regex escape differs (`\x1b` vs `\033`, same byte). Prior "emoji width by 1" claim NOT reproduced. |
| `color_cell` | `:902` | `ocheck.py:611` | `ccheck.py:382` | bc | bc | bc | **BEHAVIORALLY IDENTICAL** — same padding/align/`" {padded} "` frame |
| `snapshot_date_str` / `snapshot_age_hours` | `:218`/`:232` | via `bc` | via `bc` | via `bc` | via `bc` | `newest_snapshot_age_h` (`llm_benchmark_aggregator.py:1354`) delegates to `bc.snapshot_age_hours` | **SINGLE SOURCE — no duplication** |

**Byte-identical / consolidation-safe:** `pick_latest_raw` wrappers (4), `norm_id` (already consolidated).
**Divergent-but-behaviorally-identical (must stay local or be deliberately unified):** `_safe_float`, `_safe_int`, `display_len`, `color_cell` in ocheck+ccheck.
**Latent signature drift:** `_safe_int_round` (ocheck/ccheck lack `default=`).

The block comment at `ocheck.py:54-61` ("this module redefines every one of them below with proven, intentional divergences… ogc.*safe_float REJECTS $-prefixed values while bc's strips them") is **partly false today** — the `$`-rejection divergence is real (`ocheck.py:448` rejects `$`; bc strips `$`), but`ocheck.py:429-436` now *re-exports* `norm_id`/`parse_aa`/`parse_openrouter`/`parse_livebench`/`find**` from bc, and `display_len` output is identical. The comment misdescribes the current state (see Finding 3).

## 2. CLI Entrypoint Seam

- `pyproject.toml:8-14` maps all 6 entrypoints to `checkers.<module>:main`. Every module defines `main()` with `argparse` and an `if __name__ == "__main__": main()` guard (`llm_benchmark_aggregator.py:2550`, `opencode…:2187`, `commandcode…:1177`, `free_model_ranker.py:799`, `stealth…:511`, `benchmark_sync_daemon.py:416`).
- **Both invocation modes verified live:** package-relative import path (`import checkers.opencode_cost_benefit_analyzer` etc. — all 7 modules import cleanly from the repo root, the exact resolution the installed entrypoints use) AND direct script (`python3 checkers/free_model_ranker.py --check` rc=0, `python3 checkers/stealth_model_detector.py --check` rc=0, both offline, no writes).
- The `sys.path.insert(0, str(HERE))` hack at the top of every script (`llm_benchmark_aggregator.py:33-35`, etc.) is **redundant** when run as an installed entrypoint (the package dir is already on `sys.path`) and **harmless** — it only enables bare `import benchmark_common`. It does not break either mode today. Consolidating to package-relative imports is P3 polish that changes the direct-script contract, so it needs a test first.
- **Stale docstrings:** `free_model_ranker.py:13` and `stealth_model_detector.py:13` say "Reuses parsers + cross-source matchers from **ocgo_check.py**" — that module was deleted (memory.md: `cli.py/pricing.py/judge.py` decommission). The imports are actually `from benchmark_common import …`, so only the comment is wrong.

## 3. Data-File Schema Seam

Writers and readers per file (all use `bc.atomic_write_text`; all `models` arrays are the checker's full row shape):

| File | Writer | Reader | Diff baseline read | HTML/MD consumers |
| --- | --- | --- | --- | --- |
| `docs/data/benchmarks.json` | `save_baseline` (`llm_benchmark_aggregator.py:2410-2424`) `{generated_at, catalog_diff{added,removed,total_current}, models}` | `load_previous_snapshot` + `diff_model_catalog` (`:2482-2483`) | same file | `render_html_report`/`render_markdown_report` (`:2216`/`:2087`) — consume only `models` |
| `docs/data/cc_live.json` | `main` (`commandcode…:983-998`) `{generated_at, sources, catalog_diff, role_recommendations, models}` | `load_previous_snapshot(DATA/"cc_live.json")` (`:968`) | same file | `render_html` (`:1007-1008`) |
| `docs/data/ocgo_live.json` | `main` (`opencode…:1940-1966`) — same shape + `sources.usage_source` | `load_previous_snapshot(DATA/"ocgo_live.json")` (`:1890`) | same file | `render_html` (`:1980`) |
| `docs/data/free_models.json` | `main` (`free_model_ranker.py:763-791`) `{generated_at, sources, catalog_diff, n_free, n_with_aa, n_with_lm, models}` | `load_previous_snapshot` (`:749`) + `diff_model_catalog(require_docs_tag=False)` | same file | `render_html` (`:795`) |
| `docs/data/stealth_models.json` | `main` (`stealth…:487-503`) `{generated_at, sources, n_stealth, n_with_aa, n_with_lm, models}` | — (no baseline diff; `n_*` self-describing) | none | `render_html` (`:507`) |

**Schema round-trip findings:**

- **Write-then-read consistency holds** for all five files: the payload shape written is exactly the shape `diff_model_catalog`/`render_html*` read (verified against `benchmarks.json:1-52`, `free_models.json:1-76`, `ocgo_live.json:1-90`, `cc_live.json:1-90`, `stealth_models.json:1-13`).
- **Field written but never read back by the suite:** `ocgo_live.json`/`cc_live.json` persist `role_recommendations` and per-row `value`/`tokens`/`caps`/`remaining` blocks; the baseline diff reads only `models[i][model_id|first_seen|is_docs_model|is_new]` via `_extract_id`/`diff_model_catalog` (`benchmark_common.py:1718-1825`). This is intentional export surface (HTML/JSON consumers), not drift — noted for completeness.
- **Field read but never written by any checker:** none — `is_docs_model` is *written* by ocheck/ccheck before the docs-filtered diff (`opencode…:1899`, `commandcode…:972`) and *read* by `diff_model_catalog`'s `require_docs_tag` path (`benchmark_common.py:1747`). Consistent. fcheck/bcheck correctly pass `require_docs_tag=False`.
- **Snapshot filename convention vs `snapshot_date_str`:** all raw snapshots use `_YYYYMMDD` (`dt.date.today().isoformat().replace('-','')`), which is exactly what `_SNAP_DATE_RE = r"_(\d{8})(?:\.[A-Za-z0-9]+)?$"` (`benchmark_common.py:215`) parses, and `pick_latest_raw`/`newest_snapshot_age_h` rank by that filename date. **One name-part collision (Finding 4):** ocheck/ccheck write LiveBench snapshots as `livebench_YYYYMMDD.csv` (`opencode…:1521-1526`, `commandcode…:756-761`) while bcheck writes `livebench_<epoch>.csv` (`llm_benchmark_aggregator.py:1281-1282`) and the daemon writes `livebench_YYYYMMDD.csv` (`benchmark_sync_daemon.py:97`). bcheck's loader glob `*livebench*20*.csv` (`:1262`) sees *both* naming schemes; `date_part = "".join(filter(str.isdigit, p.stem))` (`:1268`) on `livebench_1785619200` yields `1785619200`, and the categories pair `livebench_categories_1785619200.json` misses. Both are parsed today (epoch files win only if newer mtime), but a fresh ocheck `--fetch` can make bcheck silently prefer a *stale* dated CSV over its own newer one. Structural drift between the two subsystems' cache-writer contracts.
- **Raw snapshot write gates:** every snapshot write is inside `if do_write:` (`opencode…:1356,1378,1456,1479,1502,1556`; `commandcode…:666,682`; `free_model_ranker.py:620,645`; `stealth…:338,382,408`) → `--check` never mutates `docs/data/raw/`. The prior audit's "fcheck/scheck default to network fetch and mutate raw on dry runs" is **no longer true** (`free_model_ranker.py:466-479`, `stealth…:292-305`).

## 4. Invariant Contract Seam (memory.md / AGENTS.md vs live code)

| Invariant | Status | Evidence |
| --- | --- | --- |
| Offline by default | ✅ **Enforced** | Every `fetch`/`fetch_url`/`urlopen` call site is inside `if do_fetch:`/`if fetch:` (grep-verified for all 7 files: `opencode…:1353,1373,1451,1475,1498,1546`; `commandcode…:662,680`; `free_model_ranker.py:616,641` + `fetch_or_load_cached_json`; `stealth…:333,378,404`; `llm_benchmark_aggregator.py:1277,1311,1339`; `benchmark_sync_daemon.py:103-181` reachable only via `sync-now`/daemon). Offline fallbacks are cache reads only. |
| `--check` never writes | ✅ **Enforced** | `do_write = not args.check` in all 5 checkers; file/snapshot writes gated. Live-verified: `fcheck --check` / `scheck --check` print "(check-only, no files written)" and rc=0. |
| Keys env-only | ✅ **Enforced** | No hardcoded key patterns (grep for sk-/AKIA/ghp_/xox/AIza/Bearer: zero hits). `get_api_key` (`opencode…:497-527`) reads env vars first, then *opt-in* `~/.pi/agent/auth.json` / opencode auth stores via a targeted per-provider lookup (`_lookup_provider_key`, `:480-494`) — the credential store is never harvested wholesale, and only the provider whose endpoint is called is read (S1-C4). Key is used only in the authenticated usage fetch (`:533`). |
| Pure stdlib | ✅ **Enforced** | `pyproject.toml:6` `dependencies = []`; grep for requests/numpy/pandas/httpx/bs4/yaml/dotenv/openai/anthropic: zero hits. |
| fcheck lists OC/CLN free tiers ONLY, never OR free | ✅ **Enforced** | `free_model_ranker.py:492-503`: OR is loaded to `or_free_by_key` for validation/enrichment only ("not listed"); rows come from OC (`:505-552`) and Cline (`:554-598`); a Cline free claim is validated with `is_free_model` before append (`:582-585`). |
| ocheck usage provenance in every limits view | ✅ **Enforced** | `usage_note` set to `"live (fetched now)"` or `f"cached {name}{staleness_tag}"` (`opencode…:1553,1581`); threaded into `render_cli_table` (`:715,737`), `render_limits_table` (`:990,996`), JSON `sources.usage_source` (`:1950`), HTML footer (`:2130`). Bare percentages without provenance are impossible — `usage_note` defaults to `""` and every view renders "unavailable" when empty. |
| Daemon systemd/cron invoke bsync entrypoint? | ✅ **Direct script is the CORRECT current contract** (prior "bypass" finding is resolved by design) | `install_systemd` → `ExecStart="{py_bin}" "{daemon_script}" --sync-now` (`benchmark_sync_daemon.py:338`), `install_cron` → `"{py_bin}" "{daemon_script}" --sync-now` (`:372`). The daemon script IS `bsync`'s module; invoking it by absolute path is equivalent to the entrypoint and survives environments where the project isn't pip-installed (venv-less cron). `main()` (`:381-413`) parses the same flags either way. Not a bypass — a deliberate deployment choice. |
| Staleness by filename not mtime | ✅ **Enforced** | `snapshot_date_str`/`snapshot_age_hours` (`benchmark_common.py:215-241`) parse `_YYYYMMDD` from the filename; mtime only for date-less files; `newest_snapshot_age_h` (`llm_benchmark_aggregator.py:1354-1364`) keys on the filename date — "a fresh clone/checkout rewrites mtimes" (S2-M2). |

**One prose-vs-code drift (Finding 3):** memory.md:57-71 ("norm_id… ocheck's converts them to hyphens + no None-guard;_safe_float/_safe_int (ocheck rejects $-prefixed…); display_len (disagree on 🥇-class emoji width by 1)") and the comment block at `ocheck.py:54-61` describe divergences that **no longer exist** — `norm_id` is a bc re-export in both ocheck and ccheck, `display_len` output is identical, and only `_safe_float`'s `$`-rejection remains (which IS real and deliberate). The fix is to update the docs, not the code.

## 5. Cross-Checker Formula Seam

Spot-checked by reading both implementations and by **identity check** (all computed from `benchmark_common`):

- `compute_qvi` — single definition `benchmark_common.py:356`; ocheck/ccheck both import it and assign `b["qvi_score"] = v["value_score"] = compute_qvi(q_score, eff_req_5h)` (`opencode…:1835-1838`, `commandcode…:931-934`). Numeric re-derivation matches (`log10(N+1)·(Q/70)^2.4·100` → 585.9 for Q=87, N=3000).
- `compute_avi` — single def `:325`; `opencode…:1840`, `commandcode…:931-934`; matches manual `Q^2.2/(100·log10(c+1.5))` (108.0 for Q=87, c=50).
- `compute_fgi` — single def `:335`; matches `Q·P^1.5` (67.1 for Q=87, P=84.1%).
- `compute_p_success` / `compute_token_multiplier` / `compute_effective_cost` / `compute_bfi` — single defs; identity check confirmed **`ocheck.compute_* is bc.compute_*` and `ccheck.compute_* is bc.compute_*` for all 9 shared functions** (get_z_scores included). fcheck/scheck import the same objects.
- **Where checkers genuinely differ (by design, both documented):** the *inputs* to the shared formulas. bcheck's `calculate_composite_scores` (`llm_benchmark_aggregator.py:1402-1484`) uses a fixed 6-signal weighted z (weights 0.125/0.125/0.150/0.125/0.125/0.175) with an AA-live/static cohort split; ocheck/ccheck use a renormalized presence-based weighted z (0.30/0.20/0.15/0.15/0.20) (`opencode…:1788-1800`, `commandcode…:875-884`). Same `compute_capability_q`, different z-composition. This is the seam the formulas cross — flagged as a *documented* boundary (memory.md Q-scoring invariant), not drift.
- **Cross-checker inconsistency found (Finding 1):** ocheck's no-coverage branch — there is **no `if not weights:` guard in ocheck** (unlike ccheck `commandcode…:885-905`): ocheck unconditionally computes `cz=0.0` → `compute_capability_q(0.0)=78.0` and `effective_cost=compute_effective_cost(0.0, t_mult)=0.0` for benchmark-uncovered models (`opencode…:1799-1820`). With `aa_intelligence=None`, `compute_avi(78.0, 0.0)` = `78^2.2/(100·log10(1.5))` ≈ 259 → a fake AVI/FGI/QVI for unscored models, and `_eff_cost` returns 0.0 for them (`:1860-1861`) making them *cheapest* in cost sort and Pareto candidates. ccheck deliberately nulls all of these (`:885-905`) with an explanatory comment citing the exact failure mode ("fake Q=78 made unscored cheap models dominate AVI/FGI/quality rankings"). **Two cost/benefit subsystems diverge on identical inputs.**

---

## Findings (with line refs)

### P1 — Silent wrong output across the cost/benefit seam

1. **ocheck fabricates capability/AVI for benchmark-uncovered models; ccheck nulls them — same boundary, opposite contracts.**
   `file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/opencode_cost_benefit_analyzer.py#L1785-L1820` (no `if not weights:` guard → `cz=0.0` → `compute_capability_q(0.0)=78.0`, `effective_cost=0.0`, AVI≈259)
   vs `file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/commandcode_cost_benefit_analyzer.py#L885-L905` (nulls `composite_score/capability_q/p_success/qvi/avi/fgi/effective_cost_per_request` for uncovered rows).
   Impact: `ocgo_live.json` rows with `monthly_usage_limit_usd=None` get `effective_cost=0.0` + `capability_q=78.0` → false cost-sort dominance, false Pareto candidates, false AVI/FGI/QVI in ocheck output (and in the HTML/JSON it writes). ccheck, fed the same kind of row, reports "—".
   Fix: port ccheck's guard (`if not weights: → set None ×9; continue`) into ocheck; add a regression test asserting `capability_q is None` for a zero-coverage row in BOTH checkers.

### P2 — Divergence-risk duplication + stale contract docs

2. **Six helpers still duplicated in ocheck/ccheck; behaviorally identical today, unfrozen tomorrow.**
   `_safe_float` (`opencode…:448`, `commandcode…:338`), `_safe_int` (`:465`/`:355`), `_safe_int_round` (**signature drift**: lacks `default=` vs `benchmark_common.py:190`), `display_len` (`:599`/`:371`; `\033` vs `\x1b`), `color_cell` (`:611`/`:382`). AST + live-output verified identical today. Fix: either (a) unify by importing from `benchmark_common` after confirming the `$`-reject behavior is wanted everywhere, or (b) — minimal, zero-risk — delete the `display_len`/`color_cell`/`_safe_int_round` copies and import them (provably identical), keep `_safe_float`/`_safe_int` local with an explicit `# DIVERGES: rejects $-prefixed` comment.
2. **memory.md and `ocheck.py:54-61` document divergences that no longer exist.**
   `file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/.mimori/memory.md#L57-L71` (norm_id-hyphens claim, display_len emoji-width claim, "$-reject vs strip" framing) and the code comment `file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/opencode_cost_benefit_analyzer.py#L54-L61`. `norm_id = bc.norm_id` at `opencode…:429` / `commandcode…:319`; `display_len` output verified identical. A maintainer following the doc could "restore" an import into a function that no longer diverges, or add shadowed-import fixes. Fix: update memory.md (keep only the still-true `$`-rejection divergence), trim the comment block to the actual remaining divergence.
3. **LiveBench cache-writer name-part collision between bcheck and ocheck/ccheck.**
   ocheck/ccheck write `livebench_YYYYMMDD.csv` (`opencode…:1521-1526`, `commandcode…:756-761`); bcheck writes `livebench_<epoch>.csv` (`llm_benchmark_aggregator.py:1281-1282`); the daemon writes `livebench_YYYYMMDD.csv` (`benchmark_sync_daemon.py:97`). bcheck's loader glob `*livebench*20*.csv` (`:1262`) ingests BOTH, and `date_part = "".join(filter(str.isdigit, p.stem))` (`:1268`) turns an epoch stem into a bogus date that fails to pair `livebench_categories_<part>.json`. Fix: standardize all writers on `livebench_YYYYMMDD.csv` (daemon already does) and have bcheck's loader match only the dated form (or pair by the same name-part both writers produce).

### P3 — Polish

5. **Redundant `sys.path.insert` HERE-hacks + stale module-name docstrings.**
   `llm_benchmark_aggregator.py:33-35`, `opencode…:28-30`, `commandcode…:36-38`, `free_model_ranker.py:28-30`, `stealth…:25-27`, `benchmark_sync_daemon.py:30-32`. Harmless (both invocation modes verified working), but consolidate to package-relative imports once the direct-script contract is covered by tests. `free_model_ranker.py:13` and `stealth_model_detector.py:13` still say "reuses parsers … from ocgo_check.py" — that module is gone; update to `benchmark_common`.
2. **No test asserts the --check-never-writes or offline-default invariants.** Tests pass today (102 passed) but none would catch a regression where a snapshot write escapes the `do_write` gate. Add one fixture-based test per checker that snapshots `docs/data/raw/` and `docs/reports/` mtimes under `--check`.

---

## Scoring

Rubric: <7.0 Critical (silent wrong output / contract drift); 7.0-8.4 Moderate (duplication divergence risk, entrypoint bypass); 8.5-9.4 Minor (polish); 9.5-10 Exemplary (zero drift).

- Prior round: **6.5 (Critical)** — offline violations, `--check` writes, daemon bypass, fcheck scope, divergence claims.
- Current round: the Critical-class drifts are **gone** (verified structurally + live). Remaining:
  - P1 ocheck-vs-ccheck uncovered-model divergence → real but *bounded* (only affects benchmark-uncovered rows; the other 5 seam classes are clean) — the one drift that can silently corrupt numbers on real data, so the ceiling sits at 8.4.
  - P2 duplication-without-freeze + stale docs + LiveBench name-part collision → classic 8.x duplication-divergence risk class.
  - P3 polish → 8.5+.

**Health score: 8.6 / 10 (Moderate).** One P1 (ocheck uncovered-model Q/AVI fabrication vs ccheck's null-out — same boundary, conflicting contracts), four P2 (helper duplication unfrozen, `_safe_int_round` signature drift, stale divergence docs, LiveBench cache-name collision), two P3. Every other documented invariant is structurally enforced and verified.

*Line refs use `#L<n>` against head `778a72f`; the working tree differs only in uncommitted data/HTML/pyproject dev-group — no seam .py files are modified.*
