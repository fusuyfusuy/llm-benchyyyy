# Project Memory

## Active Epics & Tasks

- v1 runner built + pushed to github.com/fusuyfusuy/llm-benchyyyy (public). Open:
  codex-cli JSON field-mapping in engine/harness/configs.py unverified live
  (docs-derived only, codex not installed locally). raw-api untested
  live, ANTHROPIC_API_KEY not set in this env.

## Core Invariants & Architecture Rules

- tasks/ and expected/ MUST stay separate dirs. Never put pass criteria/rubric
  in tasks/. Reason: contamination control + Dataset/Solver/Scorer split, see
  scope.md.
- Never commit results/. .gitignore blanket-excludes it (except .gitkeep).
  Holds real cost/token data + API-driven run transcripts.
- Never commit API keys/credential files. Keys live in env only. .gitignore
  backstops .env, *.pem, *.key, credentials* but rule is: keys never touch a
  tracked file.
- Task/expected markdown convention engine/markdown.py parses: fenced block
  first line `# path/to/file` = seed file written verbatim (minus that line)
  before run. `## Setup` bash block = setup script, runs before harness.
  `## Check` bash block in expected/ = grader command, exit 0 = pass.
- NO LLM JUDGES ALLOWED: All grading must be 100% deterministic (unit tests,
  exact match, state checks). The previously planned LLM judge ensemble has
  been decommissioned to eliminate bias. Enforced in code 2026-08-30:
  grading/judge.py deleted, GRADERS entry + --judge-* flags removed; spec.py
  raises on any 'judge' method. See ADR 2026-08-30.
- Every run must repeat N>=3 trials, report pass_rate not single pass/fail
  (non-determinism). Every result tagged model+harness+harness_version+
  tool_access (layer attribution) — untagged score is not valid, see
  metrics.md. Enforced 2026-08-30: --trials defaults 3, <3 rejected
  (engine/cli.py); report.py GROUP_KEYS is the single 5-key grouping
  contract, score.py imports it; <3-trial groups print U-flagged.
- CLI harness containers authenticate by bind-mounting host's own CLI config
  dirs read-only, not reimplementing auth. Container runs as non-root `ubuntu`
  (uid 1000) — Claude Code CLI refuses --dangerously-skip-permissions as root.
  NO host dir is rw anymore (P1 2026-08-30): pi gets a per-run throwaway
  overlay; task setup + grading phases run --network none (harness phase
  keeps egress — CLIs must reach providers).

## Domain Vocabulary & Gotchas

- Model ID is `claude-sonnet-5`, no date suffix — `claude-sonnet-5-20260115`
  is invalid (caught live during smoke test, was in cli.py/pricing.py/judge.py
  before fix).
- pi-coding-agent needs Node >=20 (image uses 22.x via NodeSource, not Ubuntu
  apt package).
- The pi package is @earendil-works/pi-coding-agent (host runs 0.84.x), NOT
  the original @mariozechner one — different behavior; image must match host.
- Container pi needs ~/.pi/agent WRITABLE as a directory (settings.json.lock,
  models-store.json, else EACCES). Since P1 the sandbox provides a throwaway
  per-run overlay (state files copied in, host npm/ ro) — never rw-mount the
  host dir: model-authored bash editing settings.json `packages` = host code
  exec at next pi launch.
- Bench pi argv includes --no-session (ephemeral runs). settings.json's
  `packages` list makes pi auto-install extensions at startup — overlay
  bind-mounts host npm/ READ-ONLY; auto-install now lands in the throwaway
  copy, not the host tree.
- pi JSONL (verified live): response text = message.content[].text (content is
  a LIST of typed blocks); usage/cost are PER-TURN on message_end events and
  must be SUMMED for multi-turn runs; tool calls = tool_execution_start.
- Antigravity CLI install URL: antigravity.google/cli/install.sh (an earlier
  guessed URL 404'd).
- artificialanalysis.ai leaderboard has no static __NEXT_DATA__ blob anymore
  (App Router, RSC-streamed). Data ships as an escaped `"models":[...]` array
  inside a `self.__next_f.push(...)` chunk. checkers/benchmark_common.py
  parse_aa() was silently broken against this (0/249 records had real scores)
  until fixed 2026-08-27 — extract via bracket-depth scan on the unescaped
  HTML, not JSON.loads on a script tag. Same site also dropped its unified
  reasoningIndex/mathReasoningIndex field in favor of raw sub-benchmarks
  (gpqa/hle/critpt/...) — no direct live replacement for aa_reasoning.
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

---

## KNOWN DEBT

- checkers/free_model_ranker.py:521: naming convention only — Zen /v1/models entries carry no `pricing` field (0/64 in the 20260828+20260830 snapshots) -> so the former price==0 clause could never fire and is deleted (S3-F3-4). If upstream ever ships pricing, reinstate a real price check instead of trusting names.
- docker/harness-base.Dockerfile:4: 5 CLI harness install layers verified <- container build passes -> live run verification of JSON schemas for all 5 CLIs inside container
- docker/harness-base.Dockerfile:29: unpinned CLI versions <- docker build w/ --version capture -> first container rebuild
