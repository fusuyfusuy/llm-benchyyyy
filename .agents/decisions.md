# Architecture Decisions (ADRs)

<!--
Record format - one `## ` heading per decision, newest appended last:

## [YYYY-MM-DD] ADR-Title
- **Context**: Why was this decision necessary?
- **Decision**: What was chosen?
- **Consequences**: What trade-offs or constraints follow?
- **Superseded by**: optional. Name the ADR that replaced this one. Superseded
  entries stay in the file for history but are never expanded in `agent-ctx
  dump` - they are listed by title only, so the file can grow without the
  snapshot growing with it.

This block is an HTML comment on purpose: a `## ` heading here would be parsed
as an ADR and render as a phantom entry in every dump.
-->

## [2026-08-19] Python + Docker sandbox + generic CLI harness adapter
- **Context**: needed to benchmark models, coding harnesses (Claude Code,
  Codex CLI, Antigravity, Pi, OpenCode), tool-use/agentic behavior, cost/
  latency. Harnesses run shell commands (some tasks test destructive-command
  recovery) so need real isolation, not just a temp dir.
- **Decision**: Python (stdlib-heavy, `anthropic` SDK only new dep). Docker
  per task run via bind-mounted tempdir, not per-task image builds — `docker`
  CLI via subprocess, no docker SDK dep. One `harness-base.Dockerfile` with
  all 5 CLIs installed, reused across runs. One generic `cli_adapter.py`
  driven by a `HarnessConfig` (argv template + JSON field-map) instead of 5
  bespoke adapter classes. raw-api harness = baseline, 3-tool (bash/read/
  write) Anthropic tool loop, execs inside same sandbox container.
- **Consequences**: v1 scoped to Anthropic-only for raw-api + judge grading;
  CLI harnesses keep native provider (Codex->OpenAI, Antigravity->Gemini) —
  no cross-wiring in v1. Container creds = host CLI config dirs bind-mounted
  read-only (reuse existing host auth, don't reimplement). Only claude-code's
  JSON field-mapping verified live; others docs-derived, verify on first real
  use (see memory.md Active Epics).

## [2026-08-27] Shared output-engine primitives over one generic table renderer
- **Context**: bcheck/ocheck/fcheck/scheck each hand-rolled their own
  ~150-300 line CLI table + HTML report renderer with real, hard-to-spot
  drift: bcheck/ocheck locally shadowed shared color_cell/display_len/
  medal_badge instead of using benchmark_common's; every script hand-rolled
  its own Q/P/AVI/FGI color thresholds (disagreeing with each other) despite
  score_color_* already existing unused; only bcheck had per-cell rank medal
  badges; bcheck+ocheck each had a fully separate hand-rolled HTML CSS/JS
  system instead of the shared HTML_CSS_COMMON/HTML_SORT_SCRIPT fcheck/scheck
  already used correctly; ocheck additionally had a 3rd, ASCII-only box style
  just for `--limits`.
- **Decision**: extend benchmark_common.py with shared *building-block*
  functions (compute_column_medals, render_banner_box, render_metric_guide_
  cli, color_ladder) that each script calls with its own column spec / row
  data / bullet text, rather than one generic parameterized table-rendering
  engine that would retire each script's render_cli_table entirely. Migrated
  all 4 scripts' banners, footers, medal badges, and Q/P/AVI/FGI color
  thresholds onto the shared functions; migrated bcheck's and ocheck's HTML
  reports onto HTML_CSS_COMMON/HTML_SORT_SCRIPT (porting ocheck's pareto/
  flagship/value/free row classes and call/note/sub/mid classes into the
  shared stylesheet as additions, not replacements).
- **Consequences**: each script still owns its own render_cli_table/
  render_html and full column set — lower regression risk than one generic
  engine, but future box/footer/badge style changes require touching each
  script's call site (not zero-touch). Found + fixed real latent bugs along
  the way: benchmark_common.display_len didn't count wide/medal emoji as
  2 columns, silently misaligning any fcheck/scheck row with a 🥇 badge;
  score_color_avi's thresholds (≥85/60/40) were miscalibrated against AVI's
  real ~100-600 output range (would've painted the whole column green) —
  recalibrated to bcheck's ≥300/200/140 as the new canonical value; ocheck's
  HTML `+NEW` badge was missing its base `.badge` class (no padding/pill
  shape). A full generic table-rendering engine (one shared render_table_cli
  used by all 4) remains a possible future follow-up, explicitly deferred as
  higher-risk/separately-scoped.

## [2026-08-30] P1 boundary enforcement: sandbox containment, egress, judge removal
- **Context**: boundary-review audit (13 critical findings, master_architectural
  audit_report.md) proved: seed-file `# path` headers escaped the sandbox
  (arbitrary host write via `../`/absolute); `.gemini` + `~/.pi/agent`
  credential trees mounted read-WRITE into containers running model-authored
  bash (pi `packages` auto-install = host code-exec vector); judge-ensemble
  grading still dispatchable despite the decommission rule.
- **Decision**: `_contained_target` guards every seed write (rejects absolute +
  `..`, O_NOFOLLOW). Setup + grading phases run `--network none` (verified 0
  network commands in tasks/ + expected/; harness phase keeps egress — CLIs
  must reach providers). `~/.pi/agent` = per-run throwaway overlay (settings/
  models-store copied in, host npm mounted ro); `.gemini` ro. judge.py +
  GRADERS entry + --judge-* flags + selfsolve route deleted; spec.py raises on
  'judge'. Errored trials write no RunRecord; cmd_run exits non-zero. Checkers:
  one variant-guarded matcher (bc.variant_conflict) for all model-ID fallbacks;
  tracked JSON writes atomic (tmp+os.replace); fcheck validates Cline ids via
  is_free_model; scheck refuses --json write on empty catalog.
- **Consequences**: LLM grading impossible without code revert + ADR. Credential
  exfil requires escaping a networkless container or reading ro dirs (read-only
  leak surface remains). Deferred to P2: egress proxy allowlist for harness
  phase, per-harness credential fragments, raw_api timeout/retry, offline-
  default parity for fcheck/scheck/ocheck.

## [2026-08-30] P2 invariants moved from prose to code
- **Context**: seam + scope4/5 audits: N>=3 was convention-only (CLI defaulted
  to 1, live data had 1-2-trial groups); score.py and report.py disagreed on
  leaderboard grouping keys; pricing keyed by banned dated ids silently
  misbilled Haiku 3.75x; three checkers still defaulted to network;
  first_seen re-stamped non-docs rows every run.
- **Decision**: --trials default 3 + reject <3 (cli.py). Single grouping
  contract: report.py GROUP_KEYS (task,model,harness,harness_version,
  tool_access), score.py imports it, dedupes trial_number keep-last, U-flags
  under-trialed groups. pricing.py canonical undated keys + _ALIASES resolver
  + one-time WARN on unknown ids. All 4 checkers offline-by-default;
  staleness from filename _YYYYMMDD not mtime; --check never writes.
  bc: variant_conflict + catalog-wide first_seen carry-over (docs-filtered
  removed display); fcheck provider-prefix dedup with also_listed provenance.
  raw_api: SDK timeout=600/max_retries=2, APIError -> errored-trial bucket
  (still no error RunRecords, P1 contract); cli_adapter rc-124 raises before
  parsing truncated JSONL; harness_version captured IN-container via exec_in.
  Grading vocabulary: exact-match|unit-test|state-check|human (human = clear
  dispatch-time refusal); CRLF normalized at extract_fenced_blocks.
- **Consequences**: documented invariants now structurally unbreakable; old
  under-trialed rows stay in runs.jsonl but render U-flagged, historical
  1-trial scores remain attributable, not silently trusted. Egress allowlist
  proxy for the harness phase + per-harness credential fragments remain the
  open hardening items (need design, not batch fix).
