# Scope 3 — Cost/Benefit Analyzers Audit (ocheck / ccheck)

**Commit:** b27355d · **Date:** 2026-09-09 · **Auditor:** ScopeCostAnalyzers
**Targets:** `checkers/opencode_cost_benefit_analyzer.py` (2239 lines),
`checkers/commandcode_cost_benefit_analyzer.py` (1323 lines),
`checkers/test_opencode_cost_benefit_analyzer.py`,
`checkers/test_commandcode_cost_benefit_analyzer.py`
**Non-goals:** aggregator, rankers, daemon, shared-math internals (cited only as contract surface).

**Health score: 8.3 / 10 (Moderate — one functional fetch-path bug in ccheck, rest minor/polish)**

## 1. Verdict

Both checkers are structurally sound: offline-first with `--fetch` as the sole network
path, `--check` correctly gates every write, corrupt snapshots degrade to WARN + fallback,
HTML output escapes interpolated ids, and the AVI cost-basis change is internally
consistent with the Eff c/r column. The single biggest defect is that
**ccheck's `--fetch` fetches OpenRouter/AA/LMArena bodies and then throws them away**
(`commandcode_cost_benefit_analyzer.py:799-804`), so `--fetch` (and `--fetch --check`)
silently uses stale cache for all three benchmark sources. Everything else is
minor: a stale "deliberate divergence" comment that overstates reality, a dead
`ox-alpha-free` pareto id, inconsistent canonical ids across the two checkers
(`qwen3.8-max` vs `qwen-3.8-max`, `hy4-preview` vs `tencent-hy4-preview`), an
always-true `log()` helper, and duplicate `diff_model_catalog` passes.

## 2. Correctness audit

### 2.1 Claimed "deliberate divergences" from benchmark_common — mostly not divergent

The ocheck header comment (`opencode_cost_benefit_analyzer.py:55-62`) claims
`norm_id / parse_aa / parse_openrouter / parse_livebench / _safe_float / _safe_int /
_safe_int_round / display_len / color_cell / C_RESET` are "redefined below with proven,
intentional divergences" and warns never to "restore" the imports. The code contradicts
the comment:

```python
# opencode_cost_benefit_analyzer.py:429-436
norm_id = bc.norm_id
parse_aa = bc.parse_aa
parse_openrouter = bc.parse_openrouter
...
```

`norm_id`, `parse_aa`, `parse_openrouter`, `parse_livebench`, and all four
`find_*_for_ocgo` helpers are **plain aliases to `bc`**, not redefinitions — there is
zero divergence and editing `bc` *does* change this file's behavior for those paths.
ccheck is identical (`commandcode_cost_benefit_analyzer.py:395-402`). Only `_safe_float`
(and trivially `display_len`) are actually local. The comment is stale documentation
drift that will mislead the next fixer into editing the wrong file or skipping a `bc`
fix. **Remediation:** shrink the NOTE to name only `_safe_float` (+ the cosmetic
`display_len` regex), or delete it.

`_safe_float` divergence itself (`opencode…:439-453`, `commandcode…:405-419` vs
`benchmark_common.py:171-190`):

| behavior | `bc._safe_float` | local `_safe_float` |
|---|---|---|
| `"$3.00"` | strips `$`/`%`/`,` → `3.0` | `s.startswith("$")` → `default` (REJECT) |
| `"50%"` | strips `%` → `50.0` | `float("50%")` raises → `default` |
| `"1,000"` | strips `,` → `1000.0` | strips `,` → `1000.0` (same) |
| `display_len` regex | `\x1b\[[0-9;]*m` | `(?:\033\|\x1b)\[[0-9;]*m` — `\033 == \x1b`, cosmetic only |

Is the `$`-rejection load-bearing? Today, no: every docs-price cell flows through
`parse_price` (imported from `bc` in both files), never through local `_safe_float`.
Local `_safe_float` is applied to already-numeric benchmark fields
(`intelligenceIndex`, `elo`, `resetsAt` percents via `float()` directly, caps via
`bc._safe_float`). So the divergence is currently inert — but it is a trap: any future
caller (the comment explicitly blesses `fcheck`/`scheck` reuse of `ogc.*`) passing a
`"$12.00"` string gets `None` where `bc` gives `12.0`, silently zeroing caps/requests.
**Remediation:** either document the rejection contract with a test
(`assertIsNone(_safe_float("$3.00"))` + why), or drop the local and use `bc._safe_float`.

`display_len` divergence is nil: the two regexes match the same language; wide/emoji
handling is line-identical to `bc.display_len` (`benchmark_common.py:943-959`). Keep or
dedup freely — no behavioral risk.

`parse_aa` / `parse_openrouter`: no divergence (aliases). The one genuine parser
difference is that ccheck adds its own `parse_cc_docs` RSC intel extractor
(`commandcode…:212-271`) — new code, not a divergence — reviewed in §2.5.

### 2.2 AVI cost-basis change — consistent with Eff c/r (correct)

Both files compute (ocheck `1883-1892`, ccheck `1063-1072`):

```python
toks_tot = est_input + est_cached + est_output
avi_cost = eff_c_req * 1_000_000 / toks_tot   # eff_c_req = cost_req * t_mult
avi = compute_avi(q_score, avi_cost)
```

The inline comment ("NOT the 80/20 fresh blended rate … flips AVI rank order against
the Eff c/r column for cache-heavy models") is accurate: Eff c/r is
`c_req * t_mult` where `c_req = compute_cost(...)` already prices cached reads at the
discounted rate, so normalizing it back to $/1M of the model's *own* token mix keeps
AVI rank-monotone with Eff c/r. The alternative 80/20 `blended_price`
(`0.80*pin + 0.20*pout`, ocheck `1858-1864`, ccheck `1044-1049`) ignores the
~50-89k cached-token leg that dominates every `FALLBACK_TOKENS` row and would indeed
invert cache-heavy ordering. Unknown price → `eff_c_req None` → no AVI (no ~900
noise): correct. One asymmetry to be aware of (not a bug): `BFI` still uses the 80/20
`blended_price` via `compute_bfi(q_score, speed, blended_price)` per the shared
formula, so BFI rank *can* diverge from Eff c/r on cache-heavy models — that is the
`bc` contract, and both checkers apply it identically.

### 2.3 Pooled-cap math — correct within each file, one out-of-pool fallback value

- ocheck (`1647-1653`): `cap_mo = usage; cap_wk = cap_mo*0.50; cap_5h = cap_mo*0.20`.
  With pools `ACC_5H/WK/MO = 12/30/60` (`:205`), `0.50 == 30/60` and `0.20 == 12/60`,
  so `cap_5h == 12 × (usage/60)` exactly as the `:108` comment states. ✔
- ccheck (`907-913`): `cap_wk = credits*(35/70)`, `cap_5h = credits*(14/70)` from
  `ACC_* = 14/35/70` (`:126`) — same shape, but expressed via the constants so a pool
  change propagates (ocheck's literals would not). Recommend ocheck adopt the
  `ACC_WK/ACC_MO` form for parity. Minor.
- Out-of-pool value: ocheck `FALLBACK_PRICING["omen-alpha"]["usage"] = 100` (`:137`)
  yields `cap_5h = $20 > $12` pool. The formula is applied faithfully
  (`12 × 100/60 = 20`), so this is a *data* question (does the docs table really grant
  Omen Alpha $100/mo headroom against a $60 pool?), not a code bug — but it should be
  confirmed on next docs re-fetch; if `usage` means something other than pool share,
  the cap model overstates Omen throughput by 67%.

### 2.4 FALLBACK_PRICING freshness vs live docs

Both catalogs are stamped 2026-09-08 (ocheck `:106`, ccheck `:72`). Staleness handling
is asymmetric: *snapshots* older than 24h get WARN banners (`offline_data_note`,
ocheck `:70-93`, ccheck `:156-175`), but the *fallback itself* never warns — a fully
offline run on month-old fallback prints no fallback-age notice. Acceptable (fallback
is last resort after snapshot), but recommend embedding the fallback date in the banner
when the fallback path is taken (`using fallback catalog`, ocheck `:1448`, ccheck
`:827`). Specific freshness risks to re-verify on next `--fetch`:

- ocheck carries 7 API-served-but-undocumented ids (`:138-150`, e.g. `grok-4.5`,
  `glm-5`, `qwen3.5-plus`, `hy3-preview`) with a "drop once the API stops serving it"
  note — good hygiene, but nothing enforces the drop; a removed API id lingers
  forever via the `for k in FALLBACK_PRICING: append` merge (`:1450-1452`).
- ccheck `FALLBACK_PRICING` has 48 entries with per-model `credits` up to 70 and two
  `None`-priced free tiers; the `"Older models also available → $20"` paragraph patch
  (`:362-369`) hardcodes 8 model names — a docs rewording silently disables it
  (falls back to per-model fallback credits via `:842-847`, so impact is bounded).
- Cross-file price drift (same model, different file): `mimo-v2.5-pro` cached_read is
  `0.003625` in ocheck (`:120`) vs `0.0036` in ccheck (`:111`); `qwen-3.8-flash`
  input `0.15` (ocheck `:127`) vs `0.16` (ccheck `:81`); `grok-4.5` cached_read `0.30`
  vs `0.5`. These are different-vendor docs so exact parity isn't expected, but the
  `mimo-v2.5-pro` 4th-decimal truncation looks like a copy slip — verify on re-fetch.

### 2.5 Docs-vs-API id aliasing

- ocheck `model_to_id` (`:357-426`): explicit display-name map + generic
  space→dash fallback + dot/dash-insensitive fallback-key match + permissive
  `^[a-z0-9][a-z0-9\.\-]*$` accept. Reasonable; the `if "/" in part: continue` guard
  after splitting on `/` (`:335`) is dead code (split output never contains `/`) but
  harmless. Duplicate-tier dedup keeps the *first* table row (`:277-278`) on the
  assumption docs list the cheaper tier first — undocumented order dependence; a docs
  reorder silently picks the peak price. Prefer `min` by computed cost or assert.
- ccheck `_norm_cc_id` (`:191-201`) + `_ID_ALIASES` (`:129-149`): strips parens,
  `Off-peak`, trailing `-N%`, normalizes separators, then alias-resolves. Sound.
  The catalog parser's tag-stripping uses `" "` replacement (`:320`) specifically so
  `"LongCat 2.0"+"Free"` don't fuse — a real bug class, correctly handled.
- **Cross-checker canonicalization split (the actual aliasing breach):** ocheck ids
  use `qwen3.8-max / qwen3.8-flash / qwen3.7-max / qwen3.7-plus / qwen3.6-plus /
  hy4-preview / hy3 / longcat-2.0` while ccheck uses `qwen-3.8-max(-0902) /
  qwen-3.8-flash / qwen-3.7-max / qwen-3.7-plus / qwen-3.6-plus /
  tencent-hy4-preview / tencent-hy3 / longcat-2.0-free`. `norm_id` does not unify
  `qwen3.8-max` with `qwen-3.8-max`, so any downstream join on `model_id` across
  ocheck/ccheck treats the same vendor model as two models. Within each checker the
  ids are self-consistent (fallback keys match `model_to_id`/`_norm_cc_id` output),
  so tables render correctly — the blast radius is cross-checker comparison only.
  **Remediation:** adopt one canonical form (recommend hyphenated `qwen-3.8-max`,
  vendor-prefixed `tencent-hy*` to match ccheck/docs slugs) and add an alias test.
- Dead pareto id: ocheck `:1922` unions `{"ox-alpha-free"} if "ox-alpha-free" in
  ocgo_api_ids`, but the canonical id everywhere else (fallback `:137`, DOCS_IDS
  `:162`, mapping `:410`) is `omen-alpha` — the condition is never true. `omen-alpha`
  is still covered via `DOCS_IDS`, so no ranking harm, but the branch is misleading;
  replace with `omen-alpha` or delete.

### 2.6 P0/P1 correctness bug: ccheck `--fetch` discards live benchmark payloads

`commandcode_cost_benefit_analyzer.py:799-804`:

```python
for url, tag in [(OPENROUTER_API, ...), (AA_URL, ...), (LMARENA_URL, ...)]:
    body = fetch(url, verbose=verbose)
    if body and do_write:          # save only; never parsed into or_map/aa_map/lm_map
        snap = RAW / f"{tag}_..."
        bc.atomic_write_text(...)
```

Compare ocheck `:1476-1531`, which parses each fetched body into `or_map`/`aa_map`/
`lm_map` immediately (`or_map = parse_openrouter(j, …)`) and only *additionally*
saves the snapshot. In ccheck the fetched bytes are used for nothing except the
snapshot write; the maps are populated later exclusively from
`pick_latest_raw(...)` (`:849-875`). Consequences:

1. `--fetch --check` (do_write=False): network is hit three times and every byte is
   discarded — the run reports "fetch (network)" but scores entirely from stale
   cache. The docs payload *is* parsed live (`:779-795`), so the run is half-live,
   half-stale with no banner distinguishing them.
2. `--fetch` with `do_write=True` still works (the just-written snapshot is
   re-read as newest), but pays a redundant serialize→write→read→parse round trip
   and breaks if the write fails while the fetch succeeded.
3. The docstring itself flags drift: "Like ocheck, --json/--html are accepted but all
   outputs are always written unless --check (documented contract drift vs
   bcheck/fcheck)" (`:18-19`) — the fetch-parse gap is presumably part of that drift.

**Remediation:** mirror ocheck — parse each fetched body into its map inline (guard
JSON decode for OpenRouter as ocheck `:1479-1487` does; note ccheck's saver at `:803`
calls `json.loads(body)` without try/except, so a truncated OpenRouter payload
currently raises out of `main` instead of WARN-and-cache).

## 3. Robustness

- **Offline cache:** both checkers default offline, order by filename-embedded date
  via `bc.pick_latest_raw` (mtime fallback), WARN past-24h sources and reuse them.
  ocheck additionally falls back through snapshot → `FALLBACK_PRICING`/`FALLBACK_TOKENS`
  → `(500, 60000, 200)` median tokens (`:1454-1472`); ccheck snapshot → fallback →
  `credits: 20.0` default (`:833-840`) + fallback-credit patch (`:842-847`). New
  unknown API ids get `None` pricing (ocheck `:1463`, ccheck `:840`) and render
  `—`/Unlimited paths instead of crashing. Good.
- **`--check` never writes:** verified by reading every write site. ocheck gates docs
  (`:1382`), API (`:1403`), OpenRouter (`:1481`), AA (`:1504`), LMArena (`:1527`),
  usage (`:1581`) snapshots and all three outputs (`:1988-2033`) on `do_write`;
  the tail prints `(check-only, no files written)` (`:2035`). ccheck gates docs
  (`:782`), OR/AA/LM (`:801`), outputs (`:1117-1146`) identically. `load_previous_snapshot`
  / `diff_model_catalog` are read/pure (shared). One wrinkle: ccheck's
  `if body and do_write` (`:801`) skips even the *save*, which is correct for `--check`
  but is also the line that causes the §2.6 discard — fix by parsing regardless of
  `do_write`, saving only when set.
- **Corrupt snapshot handling:** ocheck wraps docs (`:1421-1432`), API JSON
  (`:1437-1444`), OR (`:1491-1496`), AA (`:1514-1519`), LM (`:1537-1542`), usage
  (`:1599-1604`) parses in try/except → WARN on stderr, continue on fallback; the
  LiveBench loop (`:1544-1563`) skips per-file with a never-silent WARN (S1-C3).
  ccheck mirrors this for docs (`:810-821`), OR/AA/LM (`:852-875`), LiveBench
  (`:879-892`). The two gaps: (a) ccheck's `json.loads(body)` inside the *fetch-save*
  path (`:803`) is unguarded — a 200-with-garbage OpenRouter response crashes `--fetch`
  instead of WARN-and-cache (ocheck guards it, `:1479-1487`); (b) neither checker
  validates that a parsed snapshot is non-empty before accepting it over fallback
  (ocheck checks `if pl:` for docs but accepts empty `ids` silently at `:1440`).

## 4. Performance

No blocking issues at these catalog sizes (28–48 models). Three polish items:

1. **Double `diff_model_catalog` pass** — ocheck `:1943` diffs full `rows_sorted`
   (result's added/removed discarded; only `["rows"]` kept), then `:1951` diffs
   `docs_rows` again. ccheck `:1104` + `:1108` identical. Each pass is O(n·m) against
   the baseline; halve it by diffing once and deriving `docs_rows` by filter.
2. **Redundant fetch→save→reload in ccheck** (§2.6): after fixing to parse inline,
   the snapshot re-read becomes unnecessary on fetch runs.
3. **Render cost** — `render_cli_table` recomputes `display_len` per character per
   cell plus `compute_column_medals` sorts per scored column; fine for <100 rows but
   the per-char `display_len(ch)` inner loop in `pad_display` truncation is O(w²)
   worst-case on adversarially long model ids — bounded in practice by docs ids.
   The `for k in FALLBACK: if k not in ocgo_api_ids: append` merges are O(n²) list
   scans on ≤48 ids — negligible, but a set would express intent.

## 5. Security

- **Docs HTML scraping:** pure `re` extraction + `html_lib.escape` on every
  interpolated id/slug in `render_html` (ocheck `:2060-2061`, ccheck `:1171`);
  no `eval`/shell/template injection surface. The `<table.*?</table>` and
  bracket-depth RSC scans operate on untrusted page bytes but only build strings/
  dicts; worst case is CPU on a pathological page (see §4), not code execution.
  `fetch()` uses `urllib` with a static UA, no redirect/auth handling, no shell.
- **Price parsing injection:** `parse_price` (`bc`) strips `$`/`,` and `float()`s;
  ccheck `_eff_price` (`:303-310`) allowlists `\$([\d\.]+)` and takes the *last*
  match (handles `$20 → $14` discount cells by design). A hostile cell can at most
  yield `None` or a float — no format-string or SQL sink exists downstream
  (JSON/HTML outputs are escaped/serialized).
- **Secrets:** ocheck `get_api_key` (`:488-518`) reads three env names + targeted
  `auth.json` provider lookup, sends the key only as `Bearer` to `OCGO_USAGE_API`
  (`:524`), and explicitly warns when no opencode entry exists rather than shipping
  another provider's key (`:517`). No key is logged or persisted except the *usage
  response* snapshot (contains quota percentages, not the key — verify the usage
  payload has no token echo on next API change).
- Minor: `fetch()` prints `WARN fetch {url}: {e}` to stderr including the full URL —
  no secret is in these URLs today, but keep keys out of future query strings.

## 6. Test files

`test_opencode_cost_benefit_analyzer.py` (335 lines) and
`test_commandcode_cost_benefit_analyzer.py` (~247 lines) cover: fallback catalog size,
`compute_cost` spot values, quality-vs-cap sort distinction + bogus-mode `ValueError`,
snapshot discovery, offline AA/LMArena parsing, LiveBench CSV (ocheck `:74-83`),
header-matched (non-positional) docs tables, usage-window shapes, limits-table notes,
CLI/HTML diff rendering incl. `[-]/❌` removals, unscored-models-sort-last (no fake
Q=78), and color/plain alignment uniformity. Gaps (recommend, do not require):

- No test pins `--check` writes nothing (temp `OUT`/`DATA` + assert no new files).
- No corrupt-snapshot test (write garbage `*_docs_*.html`/bad JSON, assert WARN +
  fallback path) despite the S1-C3 comments claiming the behavior.
- No test pins the `$`-rejection `_safe_float` contract or the AVI own-mix basis
  (cache-heavy model ranks above its 80/20 position).
- No test covers ccheck §2.6 (mock `fetch`, assert maps populated without `do_write`).
- Snapshot-dependent tests (`test_snapshot_discovery`, `test_offline_parsing`)
  require a populated `docs/data/raw/` — they fail on a fresh clone; consider
  `skipUnless` guards.

## 7. Findings (patch-anchored)

**P1 — ccheck `--fetch` discards live OpenRouter/AA/LMArena payloads.**
`commandcode_cost_benefit_analyzer.py:799-804` saves but never parses the three
fetched bodies; maps come only from `pick_latest_raw` (`:849-875`). `--fetch --check`
does network I/O for zero effect; `--fetch` re-reads its own write. Mirror ocheck
`:1476-1531`: parse inline, save iff `do_write`.

**P2 — Unguarded `json.loads(body)` in ccheck fetch-save.**
`commandcode_cost_benefit_analyzer.py:803` raises out of `main` on a truncated
OpenRouter 200. Wrap like ocheck `:1479-1487` (try/except → WARN → snapshot path).

**P2 — Cross-checker canonical id split.**
ocheck `:126-137` (`qwen3.8-max`, `hy4-preview`, `hy3`) vs ccheck `:77-101`
(`qwen-3.8-max-0902`, `tencent-hy4-preview`, `tencent-hy3`) never unify under
`norm_id`. Self-consistent per checker; breaks cross-checker joins. Canonicalize
once + alias test.

**P3 — Stale "deliberate divergence" NOTE.**
`opencode_cost_benefit_analyzer.py:55-62` claims local redefinitions that are actually
`bc` aliases (`:429-436`). Shrinks trust in the one real divergence (`_safe_float`
`$`-rejection, `:439-453`). Trim to `_safe_float` only.

**P3 — Dead pareto id `ox-alpha-free`.**
`opencode_cost_benefit_analyzer.py:1922`; canonical id is `omen-alpha`
(`:137,162,410`). Harmless (covered via `DOCS_IDS`) but misleading — fix or delete.

**P3 — `log()` ignores `verbose`.**
`opencode_cost_benefit_analyzer.py:208-210`: `if verbose or True` always prints.
Gate on `verbose` or delete the helper (only used sparingly).

**P3 — First-row-wins duplicate-tier assumption.**
`opencode_cost_benefit_analyzer.py:277-280` keeps the first docs row as "cheaper".
Order-dependent; prefer min-cost or an assertion. ccheck `:326-327` same pattern.

**P3 — ocheck header-phrase brittleness.**
`opencode_cost_benefit_analyzer.py:249` matches only `"requests per 5 hour"`;
ccheck `:283` also tries `"requests / 5 hour"`. Adopt the fallback in ocheck.

**P3 — `omen-alpha` usage 100 exceeds $60 pool.**
`opencode_cost_benefit_analyzer.py:137` → `cap_5h = $20` (`:1657`). Confirm against
live docs; if `usage` is not pool share, cap model overstates throughput.

**P3 — Double diff + unused imports.**
Double `diff_model_catalog` (ocheck `:1943,1951`; ccheck `:1104,1108`); ocheck
imports `statistics` (`:22`) with no use; ocheck mixes `bc._safe_float` (`:1648`)
with local `_safe_float` (`:1898`) for the same semantic. Cleanup only.

## 8. Remediation list

1. ccheck: parse fetched OR/AA/LM bodies inline (P1); guard OpenRouter decode (P2).
2. Canonicalize `qwen3.*`/`hy*` ids across both checkers + alias test (P2).
3. Trim the divergence NOTE to `_safe_float`-only; add `$`-rejection test or unify (P3).
4. Fix `ox-alpha-free` → `omen-alpha`, `log()` gating, header-phrase fallback,
   first-row-wins → min-cost, single diff pass (P3).
5. Confirm `omen-alpha` usage-100 and `mimo-v2.5-pro` 0.003625-vs-0.0036 drift on next
   `--fetch`; surface fallback age in the banner when fallback path is taken.
6. Add tests: `--check` writes nothing, corrupt snapshot → WARN+fallback, AVI own-mix
   ordering, ccheck fetch-parse without write.
