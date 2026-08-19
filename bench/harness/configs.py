"""HarnessConfig entries for the 5 CLI-scriptable harnesses.

One generic adapter (cli_adapter.py) drives all five; this file is just the
per-harness argv template and the JSON-field map for pulling response text /
tokens / cost / tool-call-count out of each CLI's own output.

ponytail: the field paths for codex-cli, antigravity, pi-agent, and opencode
are written from vendor docs (see the research summarized in the design
conversation), not from a live run against real output -- codex isn't
installed on the dev machine at all, and the other three weren't hand-verified
against a real --json/--output-format run before this file was written.
claude-code's mapping is the one verified against a live run (see the
end-to-end smoke test in cli.py's verification). Upgrade path: run each
harness once for real, diff its actual JSON against the paths below, fix the
first mismatch found -- don't trust these paths for a real comparison until
that's done.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class HarnessConfig:
    name: str
    command: list[str]  # argv template; "{prompt}" is replaced with the instruction
    model_flag: list[str] | None  # argv tokens appended when a model override is given ("{model}" placeholder); None if this harness isn't cross-wired to other models in v1
    parse: str  # "single-json" | "jsonl"
    response_path: list[str]
    input_tokens_path: list[str] | None = None
    output_tokens_path: list[str] | None = None
    cost_path: list[str] | None = None
    tool_call_count_path: list[str] | None = None
    tool_call_event_types: tuple[str, ...] = ()
    timeout_seconds: int = 600


CLAUDE_CODE = HarnessConfig(
    name="claude-code",
    command=["claude", "-p", "{prompt}", "--output-format", "json", "--dangerously-skip-permissions"],
    model_flag=["--model", "{model}"],
    parse="single-json",
    response_path=["result"],
    input_tokens_path=["usage", "input_tokens"],
    output_tokens_path=["usage", "output_tokens"],
    cost_path=["total_cost_usd"],
    tool_call_count_path=["num_turns"],
)

CODEX_CLI = HarnessConfig(
    name="codex-cli",
    command=["codex", "exec", "--json", "--full-auto", "{prompt}"],
    model_flag=None,
    parse="jsonl",
    response_path=["msg", "text"],
    input_tokens_path=["usage", "input_tokens"],
    output_tokens_path=["usage", "output_tokens"],
    cost_path=None,
    tool_call_event_types=("command", "exec_command", "function_call"),
)

ANTIGRAVITY = HarnessConfig(
    name="antigravity",
    command=["agy", "-p", "{prompt}", "--output-format", "json", "--dangerously-skip-permissions"],
    model_flag=None,
    parse="single-json",
    response_path=["result"],
    input_tokens_path=["usage", "input_tokens"],
    output_tokens_path=["usage", "output_tokens"],
    cost_path=["total_cost_usd"],
)

PI_AGENT = HarnessConfig(
    name="pi-agent",
    command=["pi", "-p", "{prompt}", "--mode", "json"],
    model_flag=None,
    parse="jsonl",
    response_path=["text"],
    input_tokens_path=["usage", "input_tokens"],
    output_tokens_path=["usage", "output_tokens"],
    cost_path=["cost_usd"],
    tool_call_event_types=("tool_call", "tool_use"),
)

OPENCODE = HarnessConfig(
    name="opencode",
    command=["opencode", "run", "--format", "json", "{prompt}"],
    model_flag=None,
    parse="jsonl",
    response_path=["text"],
    input_tokens_path=["usage", "input_tokens"],
    output_tokens_path=["usage", "output_tokens"],
    cost_path=["cost_usd"],
    tool_call_event_types=("tool_call", "tool"),
)

REGISTRY: dict[str, HarnessConfig] = {
    "claude-code": CLAUDE_CODE,
    "codex-cli": CODEX_CLI,
    "antigravity": ANTIGRAVITY,
    "pi-agent": PI_AGENT,
    "opencode": OPENCODE,
}
