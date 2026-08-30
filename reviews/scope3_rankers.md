# Scope 3: Rankers & Detectors (fcheck + scheck) — Audit
Health Score: 5.5/10 (Critical) · Files audited: 4 primary (+2 generated outputs, 6 raw snapshots, 2 seam files lens-only) · LoC reviewed: ~1,620 + seam reads

## Evidence base (offline probes executed)

- `python3 -m unittest checkers.test_free_model_ranker -v` → 7 tests OK · `python3 -m unittest checkers.test_stealth_model_detector -v` → 6 tests OK (full output pasted in probe log; both suites green).
- Probe A (OR snapshot `openrouter_models_20260830.json`, real `ogc.parse_openrouter` + `fmr.is_free_model`): 396 records, 0 with missing/None pricing, 21 classified free (18 by `:free` suffix, 3 by $0 price), 0 suffix-bypassed paid records, **0 stealth/ models** (stealth existed only in ≤20260823 snapshots).
- Probe B (Zen/Go/Cline 20260830 snapshots, replicating fcheck:512-570 expressions): **0 of 64 zen entries contain a `pricing` key** → fcheck:516 `p.get("input") == 0 and p.get("output") == 0` can never fire; cline payload top-level keys `['recommended','free','clinePass','clineCloud']`; cline `free` ids = `cline-free/longcat-2.0`, `z-ai/glm-5.3-flash`, `deepseek/deepseek-v4-flash`, `poolside/laguna-s-2.1:free`.
- Probe C (committed `docs/data/free_models.json` × OR snapshot): 31 rows; **2 rows resolve to non-zero OpenRouter pricing** — `z-ai/glm-5.3-flash` ($0.075/$0.25 per M) and `deepseek/deepseek-v4-flash` ($0.0815/$0.163 per M), both added via the Cline path with fabricated zero pricing; `is_new=True` on **31/31** rows; `catalog_diff` = `{added: 31, removed: 0, total_current: 31, total_previous: 35}` (≥4 models silently vanished from the removal report); 3 duplicate-model pairs across sources (see F3-3).
- Probe D (deterministic re-execution of the real `bc.diff_model_catalog` against the actual `free_models.json` payload, fcheck's exact call shape `id_key="model_id"`): removing one previously-listed model yields `added_ids=30/30 (all)`, `removed_ids=0` — the truly-missing `poolside/laguna-xs-2.1:free` is **not** reported removed.
- Probe E (AA snapshot via `ogc.parse_aa`): record keys `intelligenceIndex/codingIndex/agenticIndex/medianOutputTokensPerSecond/contextWindowTokens/slug` all present → fcheck:638-643 field reads valid. Shared CSS check: `HTML_CSS_COMMON` contains `badge-or/ocg/cln/stl/new`, `removed-tag/section`; `.top-row` intentionally appended locally by both scripts (fcheck:224, scheck:122) — parity OK. No `eval/exec/subprocess/os.system` in either script; all scraped strings interpolated into HTML pass through `html.escape` (fcheck:139-141,194-195,209,220; scheck:82-94).
- `.gitignore` contains no `raw` entry; `git status` shows `docs/data/raw/*_2026082*.json` as **tracked and modified** → fcheck's unconditional snapshot writes (F3-5) dirty tracked files.

## Invariant compliance

| Rule | Relation to scope | Status |
|---|---|---|
| 1 tasks/expected separation | N/A | — |
| 2 no LLM judges | N/A | — |
| 3 run tagging | N/A (checkers don't run tasks) | — |
| 4 `claude-sonnet-5` id form | N/A | — |
| 5 container user/mounts | N/A | — |
| 6 keys in env / results not committed | fcheck/scheck claim "No API keys"; confirmed no key reads | PASS |
| 7 offline-by-default checkers (24h cache, fetch only on flag) | fcheck/scheck default to **live network**; no 24h-freshness logic; fcheck writes raw snapshots even under `--check` without `--fetch` | **BREACH** (F3-5; seam auditor cross-checks) |
| 8 task markdown convention | N/A | — |
| 9 intentional same-named helper divergence | `ogc.norm_id` vs `bc.norm_id`, `bc._safe_float` vs `ogc._safe_float`, bc vs ogc `parse_openrouter/parse_aa` shadowing: reviewed, divergence not reported per rule | PASS (F3-3 reports only the provably-wrong dedup *outcome*, not the divergence) |

## Findings

### [CRITICAL] F3-1 · Paid OpenRouter models admitted to the free headline list via the unvalidated Cline path
`checkers/free_model_ranker.py:541-570` (esp. 558-567) with `is_free_model` at 66-77.
**Mechanism:** every id under the Cline payload's `free` key is appended to `free_recs` with fabricated `pricing: {"prompt": "0", "completion": "0"}` (line 567) without ever consulting `is_free_model` — even though the full OpenRouter catalog (including the record for that same id, used two lines earlier for `context_length` at 563-566) is already in `or_map`. The dedup at 559-561 only skips ids already present as *free* OR variants; bare ids like `z-ai/glm-5.3-flash` have no `:free` counterpart, so they pass.
**Evidence (Probe B/C):** committed `docs/data/free_models.json` contains `z-ai/glm-5.3-flash` and `deepseek/deepseek-v4-flash` (source `cln`); both resolve in `openrouter_models_20260830.json` to non-zero pricing ($0.075/$0.25 and $0.0815/$0.163 per M), i.e. `fmr.is_free_model` would return False on the real record. 2/31 headline rows misclassified; any consumer routing by the listed model id incurs paid usage.
**Proposed fix:** when `cid in or_map`, require `is_free_model(or_map[cid])` (or an OR `:free` variant) before adding; for non-OR ids, record the free claim as platform-scoped rather than inventing $0 pricing.

### [CRITICAL] F3-2 · fcheck catalog diff permanently broken: every model forever "+NEW", removals silently dropped
`checkers/free_model_ranker.py:723-728, 753-758` × `checkers/benchmark_common.py:1361-1368, 1417-1423`.
**Mechanism:** fcheck's own output payload carries a `catalog_diff` key, so on the next run `has_catalog_diff=True`; with fcheck's call shape `id_key="model_id"`, the ocheck-specific docs-model filter at bc:1366 (`and not m.get("is_docs_model"): continue`) fires on fcheck payloads — where no model ever has `is_docs_model`. Result: `prev_models_map` is always empty → `is_brand_new` True for every current row (1396-1419) and `removed_ids = {} - current = ∅` (1423). Removals can never be reported; additions list is the entire catalog every run.
**Evidence (Probe C/D):** committed JSON shows `is_new=True` 31/31, `added=31, removed=0` while `total_previous=35` — ≥4 de-listed free models silently dropped from the removal report (the feature fcheck advertises in CLI/HTML/JSON). Deterministic re-execution of `bc.diff_model_catalog` with the real payload shape: 1 genuinely removed model → `removed_ids=0`, all 30 survivors marked added.
**Proposed fix:** only apply the `is_docs_model` filter when the previous payload actually uses that tag (e.g. `any("is_docs_model" in m for m in prev_models_list)`), or pass an explicit `docs_only` flag from ocheck instead of inferring from `catalog_diff` presence.

### [MODERATE] F3-3 · Provider-prefix dedup hole double-lists the same model (inflated n_free, double ranking)
`checkers/free_model_ranker.py:526-535, 559-569` (dedup sets built from `ogc.norm_id(base_id(...))`; `bc.base_id` never strips provider).
**Mechanism:** OpenCode ids are bare (`nemotron-3.5-lightning-free`) while OpenRouter ids carry a provider (`nvidia/nemotron-3.5-lightning:free`); after `base_id`+`norm_id` the strings differ by the `nvidia/` prefix, so the dedup's `if norm in or_norms: continue` misses and both survive as separate "free" rows. The dedup's stated intent (`{oc_added} added new (others already in OR)`, line 537) is defeated whenever the same free model is offered on both platforms.
**Evidence (Probe C):** committed `free_models.json` carries three duplicate-model pairs: `nemotron-3.5-lightning-free` (oc) + `nvidia/nemotron-3.5-lightning:free` (or); `laguna-s-2.1-free` (oc) + `poolside/laguna-s-2.1:free` (or); `deepseek-v4-flash-free` (oc) + `deepseek/deepseek-v4-flash` (cln). Headline count 31 overstates 28 distinct models; composites are z-scored over a multiset.
**Proposed fix:** also compare the OC/Cline norm against the OR norm *with the provider segment removed* (`norm.rsplit("/",1)[-1]`).

### [MODERATE] F3-4 · Zen pricing==0 clause is dead code against the real Zen catalog; free detection rests solely on name convention
`checkers/free_model_ranker.py:512-518` (line 516).
**Mechanism:** the clause `p.get("input") == 0 and p.get("output") == 0` requires a `pricing` object on Zen entries, but the Zen API payload entries are `{id, object, created, owned_by}` only — Probe B: **0 of 64 entries in both 20260828 and 20260830 snapshots carry `pricing`**. The intended price-based free detection can never fire; detection depends entirely on `-free` substring / hard-coded `big-pickle`, `ox-alpha-free`. Any free Zen model not following the naming convention is silently missing from the headline output (the hard-coded pair is the existing proof that the heuristic alone is insufficient).
**Evidence:** Probe B output (`zen has any 'pricing' key: False`) + code line 516.
**Proposed fix:** source Zen pricing from the catalog that actually exposes it (or document the naming-convention contract and drop the dead clause); note `"-free" in mid.lower()` is over-broad (matches anywhere), currently harmless.

### [MODERATE] F3-5 · fcheck ignores its own `--fetch` gate and `--check` no-write contract; defaults to live network + unconditional writes to tracked raw snapshots
`checkers/free_model_ranker.py:87-124` vs help text at 471-473.
**Mechanism:** (a) `fetch_or_load_cached_json` enters the network path whenever `offline` is False (line 99-100) — `--fetch` never enables fetching, network is the *default*; (b) the JSON catalog snapshot write at 104-105 is unconditional on any successful fetch, regardless of `do_fetch` (which only gates the print at 106) and regardless of `--check` ("dry-run: fetch + print, no file writes"); (c) `docs/data/raw/*_models_*.json` are git-tracked (no .gitignore entry; `git status` shows them modified), so a plain or `--check` run silently dirties tracked files. scheck (gated writes at 339/370/396) and bcheck (invariant 7: offline-by-default with 24h cache) behave differently from fcheck — inconsistent checker family defaults; repo convention per audit context is "checkers default to a 24h-file-cache offline mode," which neither fcheck nor scheck implements.
**Evidence:** deterministic code path (not executed — auditors barred from network); git tracking status from probe; scheck/fcheck write-gating asymmetry at cited lines.
**Proposed fix:** mirror bcheck's contract — default to the cached snapshot (fetch only with `--fetch`), gate all `RAW` writes on `do_fetch`, and honor `--check`.

### [MODERATE] F3-6 · scheck: a transient fetch failure writes an empty catalog over the last good stealth_models.json (no cached-snapshot fallback)
`checkers/stealth_model_detector.py:321-347, 469-488`.
**Mechanism:** in live mode, `ogc.fetch` returning None prints WARN (347) and leaves `or_map={}` → zero rows; the run then proceeds to `--json` (472-488) and overwrites `docs/data/stealth_models.json` with `n_stealth: 0, models: []` — destroying the previous real output with a zero exit code. fcheck avoids this exact hazard with its cached-snapshot fallback (`free_model_ranker.py:114-122`); scheck only falls back under `--offline`. When stealth models are actually live (e.g. `stealth/ox-alpha`, present through 2026-08-23 per snapshot probe), any network blip during a scheduled run silently erases the record.
**Proposed fix:** reuse fcheck's fallback (load latest raw snapshot on fetch failure), or refuse the `--json` write when the catalog source produced zero records after a fetch error.

### [MINOR] F3-7 · Missing/None pricing defaults to "free" in `is_free_model` and to "$0" in scheck price rendering (latent)
`checkers/free_model_ranker.py:71-77`; `checkers/stealth_model_detector.py:418-422`.
**Mechanism:** `float(p.get("prompt", 0) or 0)` treats an absent or null pricing field as exactly $0.00. If upstream shape drifts (pricing renamed/nulled), every paid model would be silently promoted to the free headline list. Probe A confirms 0/396 records currently lack pricing, so the defect is latent, not active.
**Proposed fix:** require both keys present and numeric; treat missing pricing as not-free (and not-$0).

### [MINOR] F3-8 · scheck `price_str` "($0)" annotation can assert free for non-zero sub-cent prices; persisted into JSON
`checkers/stealth_model_detector.py:420, 443`.
**Mechanism:** `f"{price*1e6:.2f}"` rounds anything below $0.005/M to `0.00`, and the string `0.00/0.00` is then annotated " ($0)" inside `price_str`, which is written verbatim to `stealth_models.json`. No current record triggers it (Probe: the one historical stealth model was genuinely 0/0) — display-precision nuance.
**Proposed fix:** append " ($0)" only when the raw float product is exactly 0.

## Remediation backlog

**P1 (silent data corruption / record loss)**
1. F3-1 — validate Cline ids against `or_map` pricing before adding; remove fabricated `{"prompt":"0","completion":"0"}` records (fcheck:541-570).
2. F3-2 — fix `diff_model_catalog` docs-filter so fcheck's prev payload populates `prev_models_map`; removals currently vanish every run (bc:1366 + fcheck:725).
3. F3-6 — scheck cached-snapshot fallback / empty-write guard (scheck:334-347, 472-488).

**P2 (correctness / robustness / contracts)**
4. F3-3 — provider-suffix-tolerant dedup between OR/OC/Cline namespaces (fcheck:526-535, 559).
5. F3-4 — dead Zen pricing clause: wire real pricing source or drop + document naming convention (fcheck:516).
6. F3-5 — align fcheck/scheck defaults with bcheck's offline-first convention; gate raw writes; honor `--check` (fcheck:87-124, 471-473).
7. F3-7 — explicit-missing-pricing handling in `is_free_model` (fcheck:71-77; scheck:420).

**P3 (polish)**
8. F3-8 — exact-zero check before the "($0)" price annotation (scheck:443).
9. Test coverage: exercise the real payload round-trip `free_models.json → diff_model_catalog` and Cline-vs-OR pricing validation; current tests inject synthetic `removed_models` into renderers only, which is why F3-2/F3-1 pass CI. Unused `import statistics` in both scripts; non-atomic `write_text` outputs (consistent repo-wide, informational).
