# Scope 2 — Universal Aggregator + TUI Architectural Review

**Commit:** `b27355d` · **Files:** `checkers/llm_benchmark_aggregator.py` (2931 lines),
`checkers/benchmark_tui.py` (1141 lines), `checkers/test_llm_benchmark_aggregator.py` (836 lines),
`checkers/test_benchmark_tui.py` (358 lines) · **Date:** 2026-09-09 · **Mode:** diagnose-only, no code edits

**Health score: 7.8 / 10 (Moderate — ship with fixes)**

The aggregator core is sound where it matters most: offline-by-default loading, honest `None`
prices (no fabricated $1/$3), `None`-passthrough z-scores with renormalized weights, priced-only
Pareto, and a clean tri-verified/partial/unmatched partition. The findings below are real but
bounded: one dead-medal key, one render (Markdown) silently dropping diff/staleness context,
duplicated upstream signals on aliased provider variants, display-name diff-key churn, and small
TUI gaps. Performance is a non-issue at current scale (513-row full render ~50 ms). No security
blockers (HTML escaping covers all upstream-controlled strings; pool badges are curated-vocab).

---

## 1. Correctness

### 1.1 `key_index` collisions + duplicated signals on provider variants (P1)

`build_universal_catalog` builds `key_index` by writing every cid, stripped cid, display name, and
all aliases through `bc.norm_id` with last-writer-wins
(`checkers/llm_benchmark_aggregator.py:881-894`). A scan of the shipped 39-row catalog finds
**11 colliding keys**. Two cases are structural, not accidental:

- `qwen3.8-27b` base (`:435-445`, aliases `qwen3.8-27b`, `qwen3-8-27b`, `qwen-3-8-27b`) vs
  `qwen3.8-27b-hetzner` (`:630-640`, aliases superset the same three slugs).
- `kimi-k3` base (`:480-490`, alias `kimi-k3`) vs `kimi-k3-nvidia` (`:645-655`, aliases
  `kimi-k3`, `kimi-k-3`, `kimi-k3-max`).

The `key_index` value itself only feeds a membership test during upstream ingest
(`:900`, `:934`, `:957`), so the collision does not misroute there. The real consequence is in
signal attachment (`:978-1052`): each catalog row independently scans its own alias list, so **the
same LiveBench/LMArena/AA record attaches to both the base row and the provider variant row**.
The leaderboard then shows two rows with identical benchmark scores but different prices
(e.g. Kimi K3 Max vs NVIDIA NIM), and both rows independently enter composite scoring, Pareto,
and medal contention — one upstream evaluation counted twice. Fix: after attachment, detect
rows sharing an identical (livebench-id, elo, aa-quality) triple and either collapse them or mark
the variant as a price-only mirror excluded from medals/Pareto/role scoring.

### 1.2 Display-name-as-diff-key drift (P1)

`main()` diffs with `id_key="display"`
(`checkers/llm_benchmark_aggregator.py:2843`, helper
`checkers/benchmark_common.py:1793-1914`). Verified by probe: previous
`Gemini 2.5 Flash` vs current `Gemini 3.7 Flash` yields `added={new}, removed={old}`. Upstream
AA `name` fields feed `display` for every ingested row (`:902-905`, `:936`, `:959`), so any AA
rename churns `catalog_diff`/`first_seen`: a renamed model simultaneously fakes a REMOVAL and a
brand-new 7-day green highlight. The `_extract_id` fallback chain
(`benchmark_common.py:1821-1824`) already prefers stable ids when present. Fix: pass a stable key
(`model_id`/`or_slug`/`aa_slug` with display fallback) or normalize display through the alias map
before diffing.

### 1.3 Eff-column medals are dead — `eff_cost` vs `cost` key mismatch (P2)

`BCHECK_COL_MEDAL_KEYS` registers the key `"eff_cost"` (`:1373`), but `render_cli_table` reads
`meds.get("cost")` (`:1742`). The lookup always misses, so the **Eff $/M column never awards
🥇/🥈/🥉** in the main table. Same class of bug in `render_one_shot_cli_table`: `medal_metrics`
defines only `q/reason/coding/speed` (`:1982-1987`) while the wide row reads
`meds.get("psucc")` / `meds.get("cost")` (`:2131-2133`) — always `None`, harmless but dead.
Fix: rename dict key to `"cost"` (or the lookups to `"eff_cost"`) and add `psucc`/`cost` legs to
the one-shot medal map.

### 1.4 `--sort reasoning` fallback chain is wider than the pipeline populates (P2)

The reasoning sort key tries `livebench.reasoning → base_metrics.aa_reasoning →
aa_live_reasoning` (`:2870`); `extract_capability_pillars` similarly reads `bm.aa_reasoning`
(`benchmark_common.py:2006`). Probes confirm **nothing in the pipeline ever writes**
`aa_reasoning` or `aa_live_reasoning` (the AA parser emits only
`intelligenceIndex/codingIndex/agenticIndex/medianTps/prices`,
`benchmark_common.py:693-763`; zero catalog rows carry `aa_reasoning`). The chain silently
degrades to LiveBench-reasoning-only. The sort is not wrong, but the two AA legs are
documentation, not behavior. Fix: either populate AA reasoning from a real field or drop the dead
legs so the next reader does not assume AA reasoning coverage exists.

### 1.5 AA live/static cohort split drops static signals silently (P2, by design — document it)

When *any* row has `aa_live_quality`, the whole cohort z-scores live values and static-only rows
score with AA weight renormalized away (`:1261-1270`, renormalization `:1293-1318`). Probe:
mixed cohort → live row Q83.0, static row (AA 95 seed, no live) Q69.5 with its static AA seed
entirely unused. Quarantining old-scale seeds (~93-96) from the new live scale (~4-53) is correct
(the mixed distribution would be garbage), and renormalization keeps it honest rather than
mean-filled. But a static row loses 40% of its signal weight with no marker — it renders
indistinguishable from a fully-evaluated row. Fix: flag rows scored without AA
(e.g. reuse the `[2/3]` confidence language) or log the count of AA-dropped rows per run.

### 1.6 Tri-verified vs single-source ranking is inconsistent across renders (P2)

- `render_cli_table` medals + roles use `primary_models` (tri-only, `:1620`, `:1883`).
- `render_one_shot_cli_table` roles use **all** models (`:2230`).
- Markdown §3 podium uses tri-only (`:2518`); standalone `render_podium_table` (`--podium`)
  uses **all** models (`:2286-2287`).
- Markdown §1 shows tri-only while one-shot shows the full merged list — intended per-table, but
  the podium/role split across the two is not.

A single-source row can therefore win a podium slot via `--podium` that the Markdown report
denies it. Fix: pick one rule (recommend: tri-only for podiums/medals everywhere, full-list only
for the one-shot body) and thread it through all four renders.

### 1.7 Priced-Pareto wiring: 3.5 of 4 renders (P2 for the half)

CLI (`:1600`), one-shot (`:1908`), and HTML (`:2558`) all default to
`compute_priced_pareto_frontier` — correct. The Markdown report computes pareto (`:2417`) but its
signature (`:2414`) has **no `added_ids` / `removed_models` / `stale_note` params**, and `main()`
(`:2886`) cannot pass them: `--md` output silently drops NEW/REMOVED banners and the staleness
warning that CLI/one-shot/HTML all carry. The standalone podium table has no pareto overlay at
all (`:2238-2254`, no `pareto` reference) — acceptable if deliberate, but it is the only render
where a "winner" can be a Pareto-dominated row with no visual cue. Fix: extend the Markdown
signature to parity with HTML and pass the three args at the call site.

### 1.8 `save_baseline` collapse semantics (P3)

`save_baseline` (`:2767-2781`) persists `added`/`removed` id lists + `total_current` + full rows,
and it is only called on `--fetch` (`:2847-2849`, correct — a `--pool all` subset baseline would
fake-REMOVE the filtered rows; diffing runs catalog-wide pre-filter at `:2840-2844`, also
correct). Two gaps: (a) `first_seen` for *removed* models is discarded (only live rows persist),
so a model that leaves and returns looks brand-new instead of returning; (b) `total_current`
counts post-dedup rows but the payload drops the `window_days` that gave `added` its meaning —
a future window change silently reinterprets old baselines. Fix: persist removed rows'
`{id: first_seen}` map and the window used.

### 1.9 TUI Pareto membership is display-only (P3)

`benchmark_tui.py:138` and `:763` test `display in pareto_ids`, while every aggregator render
tests five stable ids (`display/aa_slug/lm_slug/model_id/or_slug`, e.g. `:1731`). It works today
because the pareto set always contains displays, but a row whose display differs from all its
stable ids (exactly the upstream-ingested rows of §1.2) can lose its ⭐ in the TUI while keeping
it in CLI/HTML. Fix: share one `is_pareto_row(m, pareto_ids)` helper.

### 1.10 Main-filter vs partition `unmatched` predicate disagree (P3)

`main()` keeps a row when its `livebench` dict is truthy (`:2837-2838`), while
`partition_models_by_benchmark_coverage` requires `livebench.overall is not None` (`:1393`).
A row with `livebench={"overall": None}` (possible straight from `parse_livebench` when a CSV
row has no numeric cells) lands in `models` *and* in `partitions["unmatched"]` — rendered as a
`—`-filled main-table row plus an unmatched alert. Fix: use the partition predicate in `main()`.

---

## 2. Robustness

### 2.1 Offline-by-default: sound (no finding)

`load_livebench_data` / `load_lmarena_data` / `load_aa_data` (`:1083-1181`) read the newest dated
cache snapshot with zero network unless `--fetch`; `fetch_url` (`:1073-1080`) returns `None` on
any exception; `--fetch` failures print a `WARN` to stderr and continue on cache (`:1123-1124`,
`:1151-1152`, `:1179-1180`); no-cache + fetch-failure degrades to base-catalog-only with every
row honestly `unmatched` (scorer emits `None`s, `:1304-1316`). TUI standalone `main()`
(`benchmark_tui.py:1107-1137`) follows the same offline pattern.

### 2.2 Staleness banners: CLI/one-shot/HTML yes; Markdown/TUI no (P2)

`cache_staleness_note` (`:1197-1212`, filename-date age via
`benchmark_common.py:251-...`, immune to checkout-mtime skew) threads through CLI, one-shot, and
HTML. It never reaches Markdown (§1.7) and the TUI has no staleness surface at all — the info
line (`benchmark_tui.py:647`) names the upstreams without cache age, so the most
offline-likely surface (interactive browsing) is the one that hides staleness. Fix: add a stale
segment to the TUI info line (or status bar) and the Markdown header.

### 2.3 Silent cache-parse swallows (P2)

The three cache-read loops catch `Exception: pass` with no log (`:1103-1104`, `:1136-1138`,
`:1164-1166`) — only the *fetch* branch earned the "never swallow silently" annotation. A corrupt
snapshot is indistinguishable from a missing one (both → base-catalog-only run). Fix: mirror the
`load_previous_snapshot` loud-WARN pattern (`benchmark_common.py:1742-1755`) on corrupt caches.

### 2.4 Empty-catalog renders never crash but say nothing (P3)

Probed all five renders with `[]`: headers + zero-row tables, no exceptions. `render_tui` has an
explicit empty-filter message (`benchmark_tui.py:747-750`). The CLI/markdown/HTML/podium paths
print `Tri-Verified: 0 models` with no "no data — run with --fetch?" hint. Fix: one shared
empty-catalog notice line.

### 2.5 `render_sub_table_*` KeyErrors on key-missing rows (P3)

`render_sub_table_md` (`:2343-2344`: `m["display"]`, `m["pool"]`, `m["tier"]`) and
`render_sub_table_html` (`:2367`: `m["pool"]`) index required keys directly — probe crashes with
`KeyError: 'pool'` on a sparse row. All current callers pass full catalog rows, so this is
latent; fix with `.get()` defaults when touching these functions.

---

## 3. Performance (no findings; numbers for the record)

Catalog build pre-indexes all four upstream maps to O(1) dicts (`:845-847`) plus base-slug maps
(`:850-879`); per-row attachment is bounded alias-list scans — no nested catalog×upstream loops.
Measured on a synthetic 513-row catalog: scoring 6 ms, CLI/HTML/Markdown/one-shot ~30 ms each at
`top_n=30`, full-catalog CLI 49 ms, `TUIState` init 5 ms, 8× search keystrokes over 513 rows
20 ms. `compute_pareto_frontier` is O(n²) pairwise
(`benchmark_common.py:440-448`) — 263k cheap tuple comparisons at n=513 (lost in the noise),
but flag it if the catalog ever grows 10-20×; a skyline sweep would drop it to O(n log n).
`TUIState.apply_filters` recomputes pillars + Pareto + roles per keystroke
(`benchmark_tui.py:83-165`) — fine at this scale; only revisit if `top_limit` grows past a few
thousand. TUI search itself is three-substring matching (`:102-108`, display/provider/model_id)
— aliases are not searched; adding them is a product call, not a perf concern.

---

## 4. Security

### 4.1 HTML escaping: upstream-controlled strings covered; pool badges not (P3)

Main table escapes display/tier (`:2590`, `:2618`), sub-tables escape display/tier
(`:2377`, `:2379`), podium escapes display (`:2654`), unmatched/removed escape ids (`:1494`,
`:2688`). The gaps — `{m['pool'].upper()}` in main (`:2617`) and sub (`:2378`) tables,
`pool_str` in removed tags (`:2689-2694`), raw `pool_badge()` in the Markdown podium (`:2525`) —
all interpolate from the curated pool vocabulary (`api` constant for every upstream-ingested
row), so there is no live injection path today. Escape them anyway for defense in depth; one
upstream-controlled `pool` value in future is all it takes. Markdown tables never escape `|`
in display names (same verdict: no live path, harden on touch).

### 4.2 Curses input handling: sound, two UX-behavior mismatches (P3)

`safe_addstr` bounds-checks every write (`benchmark_tui.py:258-277`); search accepts only
printable ASCII (`:926-928`); `getch` exceptions and `KEY_RESIZE` handled (`:902-914`); modal
dismissal correctly shadows `q`-quit while a modal owns the screen (`:932-992`); non-tty
`run_tui` degrades to a printed one-shot table (`:869-878`). Two mismatches: (a) Esc during
search is labeled "cancel" (`:921`) but keeps the already-applied filter — it commits, not
cancels; (b) main-loop Esc (`:1069-1074`) resets query/pool/pareto but leaves sort/pool-cycle
state, so "Filters reset." overpromises. Neither corrupts state.

---

## 5. Test coverage assessment

`test_llm_benchmark_aggregator.py` guards the important contracts hermetically (renormalized
weights, `None`-cost rows, priced Pareto, version-safe matching, diff rendering) and
`test_benchmark_tui.py` covers tri-default, toggles, pagination, pool/search/sort. Gaps that map
to findings above: no test asserts Eff-column medals (would have caught §1.3); no test renders
`--md` with added/removed/stale (would have caught §1.7); no duplicate-signal test for aliased
variants (§1.1); no rename-drift diff test (§1.2); no corrupt-cache test (§2.3). Recommended
additions are exactly those five regression tests — each fails pre-fix and passes post-fix.

---

## 6. Remediation list (priority order)

1. **P1** — Deduplicate shared upstream signals across aliased provider variants (§1.1).
2. **P1** — Diff on a stable id, not `display` (§1.2).
3. **P2** — Fix `eff_cost`/`cost` medal key + one-shot `psucc`/`cost` legs (§1.3).
4. **P2** — Markdown parity: `added_ids`/`removed_models`/`stale_note` params + call site (§1.7).
5. **P2** — TUI staleness indicator (§2.2); unify podium/role cohort rule (§1.6).
6. **P2** — Loud WARN on corrupt cache snapshots (§2.3); resolve or document the dead AA
   reasoning legs (§1.4) and the static-AA drop marker (§1.5).
7. **P3** — Persist removed-`first_seen` + window in baseline (§1.8); shared pareto-membership
   helper (§1.9); partition predicate in `main()` (§1.10); escape pool badges (§4.1); empty-catalog
   notice (§2.4); `.get()` in sub-tables (§2.5); search-Esc semantics (§4.2).
8. Tests: medal, md-diff/stale, duplicate-signal, rename-drift, corrupt-cache regression tests.
