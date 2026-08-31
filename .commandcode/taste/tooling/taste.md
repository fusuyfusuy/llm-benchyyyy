# Tooling & Environment

- The harnesses/agents under test in their benchmark system are: antigravity CLI, codex CLI, pi agent, and opencode. Confidence: 0.9
- Runs large refactors and audits via subagents with task notifications (parallel audit agents, verify-and-audit agents, implementation agents in worktrees). Confidence: 0.8
- Uses the `mimori` code-intelligence tool as a standard part of the workflow: warm it up early in a session (`mimori dump --file`), orient on large files with `mimori map --stdout --focus` / `mimori slice` before reading them in full, and gate finished work on `mimori debt check` being green for touched files. Confidence: 0.7
- Exposes checker CLIs (bcheck/ocheck/fcheck/scheck/ccheck) on PATH via manual symlinks from `~/.local/bin/` to the `checkers/*.py` scripts — there is no pip on this Python, so no `pip install -e .` console scripts; new checkers are wired the same way. Confidence: 0.9
