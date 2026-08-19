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
