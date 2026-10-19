# Project Memory

## Active Epics & Tasks

- 08:00 Benchmark Sync Daemon (bsync) extended: syncs all upstream sources
  (including OpenCode Go/Zen models & docs), refreshes downstream checkers
  (ocgo_live.json, cc_live.json, free_models.json, stealth_models.json),
  and writes live benchmark/pricing radar to Akatsuki (30-Agents/Model-Benchmarks-Live.md)
  with telemetry logging.
- Tri-source consensus scoring transition: Vals Index (vals.ai/benchmarks/vals_index)
  integrated alongside Arena.ai and Artificial Analysis as a balanced tri-pillar consensus
  scoring system (Arena 35%, AA 35%, Vals 30%). LiveBench remains decontaminated reference.
  Confidence badges standard updated to [3/3].
- Gemini / AGY subscription models update: Claude Opus 5.5 and Claude Sonnet 5.5
  integrated into the AGY pool (`pool: 'agy'`) with built-in Antigravity effort tiers
  (claude-opus-5-5-low|medium|high, claude-sonnet-5-5-low|medium|high), unlocking frontier
  architecture and pair coding roles under Gemini / AGY plans.

## Core Invariants & Architecture Rules

- Never commit API keys/credential files. Keys live in env only. .gitignore
  backstops .env, *.pem, *.key, credentials* but rule is: keys never touch a
  tracked file.
- All checkers (bcheck, ocheck, ccheck, fcheck, scheck, fntcheck) operate fully
  offline by default against docs/data/raw/ snapshots, requiring explicit --fetch
  or daemon sync to access network.

## Domain Vocabulary & Gotchas

- Antigravity CLI install URL: antigravity.google/cli/install.sh (an earlier
  guessed URL 404'd).
- artificialanalysis.ai leaderboard has no static __NEXT_DATA__ blob anymore
  (App Router, RSC-streamed). Data ships as an escaped JSON array inside a
  `self.__next_f.push(...)` chunk. checkers/benchmark_common.py parse_aa()
  must find that array via bracket-depth scan on the unescaped HTML, NOT
  JSON.loads on a script tag. The array KEY is NOT stable: it was `"models"`
  through 2026-10, then renamed to `"initialModels"` (2026-10-19), which
  silently zeroed parse_aa() to 0/273 records until re-fixed — always scan
  BOTH keys and take the largest array that carries `intelligenceIndex`.
  Same site also dropped its unified reasoningIndex/mathReasoningIndex field
  in favor of raw sub-benchmarks (gpqa/hle/critpt/...) — no direct live
  replacement for aa_reasoning.
- arcprize.org/leaderboard (ARC-AGI-2 source) is client-rendered, data NOT in
  HTML/RSC — but the runtime fetch IS plain static JSON (found via browser
  network inspection 2026-08-28): /media/data/models.json + /media/data/
  evaluations.json (+ leaderboard/v3.json = ARC-AGI-3, 27 evals, ignore for
  arc_agi col). bcheck wired live 2026-08-28: load_arc_data/parse_arc/find_arc,
  dataset v2_Semi_Private = leaderboard column, display!=False, Human excluded,
  best score per modelGroup, tier-stripped base-name keys; modelReleaseDate
  feeds created_date -> first_seen. Raw snapshot: docs/data/raw/arc_agi_YYYYMMDD.json.
- ALL FOUR checkers (bcheck/ocheck/fcheck/scheck) run fully offline by
  default since 2026-08-30 (P2 parity): cache-only docs/data/raw/ snapshots,
  staleness judged by FILENAME _YYYYMMDD (fresh mtime cannot mask old data),
  >24h = WARN banner, network only via --fetch/--refresh. --check NEVER
  writes (even with --fetch). bcheck baseline rewrite: dict payload w/
  first_seen + catalog_diff; NEW green 7d self-expiry; diff catalog-wide
  BEFORE --pool filtering. first_seen carry-over is catalog-wide (non-docs
  rows stop re-stamping); removed display stays docs-filtered.
- checkers/ dedup gotcha (2026-08-27 cleanup): same-named helpers across
  ocheck/bcheck/fcheck/scheck that LOOK like copy-paste duplicates often
  aren't — verify with actual diffs/programmatic equivalence checks before
  consolidating, don't trust visual similarity or docstring claims. Found
  divergent on close inspection: norm_id (bc keeps dots/underscores, ocheck's
  converts them to hyphens + no None-guard), _safe_float/_safe_int (ocheck
  rejects any "$"-prefixed value, bc strips "$" and parses it), parse_aa/
  parse_openrouter (ocheck returns full raw API dicts, bc returns a
  normalized subset — ocheck reads fields bc's wrapper drops, e.g.
  contextWindowTokens), display_len (disagree on 🥇-class emoji width by 1).
  Left all of these local to ocheck. Confirmed safe to consolidate only
  after byte-identical output on real data: parse_lmarena, the color
  constants (except C_YELLOW: bc=226, ocheck had 221 — real bug, fixed),
  and fcheck/scheck's composite-scoring block (verified via direct reads,
  not the explore-agent's claim alone).
- Command Code docs use strikethrough HTML `<s>$old</s><span>$new</span>` for
  updated credit allowances (e.g. DeepSeek V4.1 Flash $40 -> $60). Credit cell
  parsers must use regex extraction (`_eff_price` / `nums[-1]`) to extract the
  active price, and never conflate `credits is None` with the Free tier.
- vals.ai/benchmarks/vals_index uses Astro v4 with devalue serialization embedded inside
  `<astro-island component-url="/_astro/ValsIndexBarGraph..." props="...">`. `unwrap_astro_devalue`
  in `checkers/benchmark_common.py` recursively unpickles Astro devalue objects (`[0, {...}]`) and arrays
  (`[1, [...]]`) into native Python structures. Sub-task scores (vibe_code_bench, terminal_bench_4,
  finance_agent, legal, tax, code_migration) are present in ValsIndexBarGraph props, while ScatterGraph
  only carries overall scores. Model slugs use `provider/model-slug` format.
- parse_lmarena in checkers/benchmark_common.py extracts Next.js RSC "entries":[{...}]
  keyed by lowercase modelDisplayName and only runs the legacy <tr> HTML table parser
  when RSC entries are absent (if not out:), preventing dual-parser duplicate slugs.

---
- 2026-10-19 upstream scraper-drift batch (all verified against live pages):
  (1) LiveBench moved its data files under a `/v1/` path prefix — old
  `livebench.ai/table_*.csv` and `categories_*.json` root URLs now 404; both
  benchmark_sync_daemon.py and llm_benchmark_aggregator.py must use
  `livebench.ai/v1/table_2026_06_25.csv` + `/v1/categories_2026_06_25.json`.
  (2) Cline's `api.cline.bot/v1/models` is dead; the working catalog endpoint
  is `api.cline.bot/api/v1/ai/cline/recommended-models` (returns
  {recommended, free, clinePass, clineCloud}). (3) opencode.ai moved the Go
  docs to `/v2/docs/console/go/` (old /docs/go/ 301-redirects but canonical
  is v2). (4) OpenCode Go promo rows (`<del>$15</del> <strong>$60</strong>`
  + a trailing `<small>4x · Limited time</small>`) must be parsed off the RAW
  cell — stripping tags first fuses "$60" with the "4x" suffix into a bogus
  "604" and also fuses the model name ("Step 5 Preview4x"); read the
  `<strong>` active price/count, and strip the promo suffix with an
  OPTIONAL-space regex `\s*\d+x\s*$` after splitting on "·". (5) OpenCode Go
  is now per-model monthly caps ($15/$30/$60 tiers), NOT the old pooled
  "$12/5h · $30/wk · $60/mo"; 5h window = 20% and weekly = 50% of the
  monthly cap.
- arena.ai (LMArena / leaderboard/code/webdev) returns Cloudflare-403 to
  every non-browser path (all arena.ai URLs, verified 2026-10-19) — this is
  bot-protection, not a wrong URL, so there is no scraper fix; bcheck simply
  loses LMArena ELO coverage for any date with no cached lmarena_*.html
  snapshot. When the rolling retention window prunes the last good snapshot
  (was lmarena_20261013) the evaluated-model baseline drops (522 -> 289 on
  2026-10-19, ~233 ELO-only models). A browser-context fetch or an operator
  manual snapshot is required to restore LMArena rows.



## KNOWN DEBT

- checkers/free_model_ranker.py:521: naming convention only <- Zen /v1/models entries carry no pricing field (0/64 in snapshots) -> reinstate real price check if upstream ships pricing
