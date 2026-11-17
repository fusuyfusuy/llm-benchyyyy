# Project Memory

## Active Epics & Tasks

- 7-authority single-scoring-authority architecture (`Option A`, 2026-11-15): `checkers/benchmark_common.py:score_five_axes_and_roles` is the sole scoring engine across Python (`bcheck`) and Rust (`checkerz`), integrating Artificial Analysis v5.0.1, Vals Index, LMArena (HF), LiveBench, Cognition FrontierCode 2.0 (`cognition.com/data/frontier-code-2.0/data.json`), FrontierSWE (`frontierswe.com`), and CursorBench 4.0 (`cursor.com/evals` immutable JS chunk) with `Conf [k/7]` badges, 5 James-Stein shrunk z-score axes (`reasoning`, `coding`, `design`, `research`, `economics`, `SHRINKAGE_LAMBDA=0.20`), and 4 task-role scores (`architecture`, `software_dev`, `design`, `research`).
- Distinct thinking/effort rows: catalog and upstream ingest preserve `minimal`, `low`, `medium`, `high`, `xhigh`, `max`, and `non-reasoning` as separate rows (including `Gemini 4 Carbon (High|Medium|Low)`, `Gemini 4 Hydrogen (Xhigh|High|Medium|Low)`, `Claude Opus 5.5 (Max|Xhigh|High|Medium|Low)`, `Claude Sonnet 5.5`, `Claude Fable 5.2`) with effort-strict signal & empirical `$/task` binding.
- 08:00 Benchmark Sync Daemon (`bsync`): syncs all 14 raw feeds (including FrontierCode 2.0, FrontierSWE, and CursorBench 4.0 with fail-closed byte & parsed-row minimums), refreshes `benchmarks.json` + downstream JSON/HTML outputs, and updates Akatsuki (`30-Agents/Model-Benchmarks-Live.md`).

## Core Invariants & Architecture Rules

- Never commit API keys/credential files. Keys live in env only (`.gitignore` backstops `.env`, `*.pem`, `*.key`, `credentials*`).
- All checkers (`bcheck`, `ocheck`, `ccheck`, `fcheck`, `scheck`, `fntcheck`, `checkerz`) operate 100% offline by default against `docs/data/raw/` and `docs/data/benchmarks.json`, requiring explicit `--fetch` or `bsync --sync-now` to touch the network.
- Single scoring authority: never duplicate z-score or synthetic sigmoid math in `checkerz` (`checkerz/src/scoring.rs` reads precomputed `roles`, `axes`, and `empirical_cost` from `benchmarks.json`).

## Domain Vocabulary & Gotchas

- `artificialanalysis.ai` v5.0.1 (migrated 2026-11-14): RSC-streamed JSON array inside `self.__next_f.push(...)` now nests `slug` under `release.slug`, renames throughput to `outputSpeed`, and stores benchmark scores as `0..1` ratios inside `scores.*` (`intelligenceIndex`, `hle`, `critpt`, `terminalbenchHard`, `frontiercode`, `lcr`, `omniscienceNonHallucinationRate`, `omniscienceAccuracy`, `ifbench`, `gpqa`, `scicode`). `parse_aa()` scales ratios `<=1.0` to `0..100` and preserves both schema generations.
- Effort vs model-size suffixes: `qwen...-max` and `mistral/devstral...-medium` denote model-size tiers, NOT thinking effort. Always guard suffix extraction with `_is_model_size_suffix` (`benchmark_common.py`) and `strip_effort_suffix` (`llm_benchmark_aggregator.py`).
- Cross-source Anthropic & Meta slugs: `FrontierCode 2.0` and `FrontierSWE` omit `claude-` on Anthropic slugs (`fable-5-2`, `opus-5-5`, `sonnet-5-5`, `haiku-5-5`); `_canon_family_slug` canonicalizes bare prefixes to `claude-*`. Single-config family boards (`FrontierSWE`, `Vals Index`) attach ONLY to unsplit rows or a family's highest effort tier (`is_flagship=True`).
- `cursor.com/evals` data path: embeds the full 111-row `CursorBench 4.0` dataset (`models[]` with `effort`, `cost`, `tokens`, `steps`, `cursorbench`) inside an immutable `/marketing-static/_next/static/immutable/chunks/*.js` bundle; `fetch_cursor_evals_json` locates the chunk with `"CursorBench"` and extracts balanced JSON via `extract_json_array_after_key`.
- LMArena data path: `arena.ai` returns Cloudflare 403 to non-browser clients; `fetch_lmarena_hf_snapshot` pulls from HuggingFace `lmarena-ai/arena-leaderboard-snapshot` into `docs/data/raw/lmarena_hf_YYYYMMDD.json`.
- `vals.ai/benchmarks/vals_index` embeds Astro v4 devalue serialization inside `<astro-island ... props="...">`; `unwrap_astro_devalue` decodes overall + sub-task metrics (`vibe_code_bench`, `terminal_bench_4`).
- OpenCode Go (`/v2/docs/console/go/`) uses shared percentage quota windows (`5h=20%`, `weekly=50%`, `monthly=100%`); Command Code GOAT (`commandcode.ai/docs/plans/goat`) uses strikethrough HTML `<s>$old</s><span>$new</span>`; Cline catalog lives at `api.cline.bot/api/v1/ai/cline/recommended-models`.

## KNOWN DEBT
# Deliberate gaps get ledger lines: - accepted <what> <- <why> -> <trigger>

- naming convention only <- Zen /v1/models entries carry no pricing field -> reinstate real price check if upstream ships pricing
