"""HarnessConfig entries for the 5 CLI-scriptable harnesses.

One generic adapter (cli_adapter.py) drives all five; this file is just the
per-harness argv template and the JSON-field map for pulling response text /
tokens / cost / tool-call-count out of each CLI's own output.

ponytail: claude-code and pi-agent mappings are verified against live runs
(pi's JSONL shape confirmed 2026-08-21: response text at message.content[].text,
per-turn usage at message.usage.{input,output}, cost at message.usage.cost.total,
tool calls as tool_execution_start events). codex-cli, antigravity, and opencode
are still docs-derived and unverified. Upgrade path: run each harness once for
real, diff its actual JSON against the paths below, fix the first mismatch found.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class HarnessConfig:
    name: str
    command: list[str]  # argv template; "{prompt}" is replaced with the instruction
    model_flag: list[str] | None  # argv tokens appended when a model override is given ("{model}" placeholder); None if the CLI has no known model flag
    parse: str  # "single-json" | "jsonl"
    response_path: list[str]
    input_tokens_path: list[str] | None = None
    output_tokens_path: list[str] | None = None
    cost_path: list[str] | None = None
    tool_call_count_path: list[str] | None = None
    tool_call_event_types: tuple[str, ...] = ()
    timeout_seconds: int = 600
    # jsonl parse only: event types whose metric paths (tokens/cost) should be
    # SUMMED across events instead of last-value-wins. Empty -> last-wins.
    sum_usage_event_types: tuple[str, ...] = ()
    # argv run once (cached) to record the harness's real version in results;
    # None -> fall back to the harness name. Docs-derived for unverified CLIs.
    version_argv: tuple[str, ...] | None = None


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
    version_argv=("claude", "--version"),
)

CODEX_CLI = HarnessConfig(
    name="codex-cli",
    command=["codex", "exec", "--json", "--full-auto", "{prompt}"],
    model_flag=["--model", "{model}"],
    parse="jsonl",
    response_path=["msg", "text"],
    input_tokens_path=["usage", "input_tokens"],
    output_tokens_path=["usage", "output_tokens"],
    cost_path=None,
    tool_call_event_types=("command", "exec_command", "function_call"),
    version_argv=("codex", "--version"),
)

ANTIGRAVITY = HarnessConfig(
    name="antigravity",
    command=["agy", "-p", "{prompt}", "--output-format", "json", "--dangerously-skip-permissions"],
    model_flag=["--model", "{model}"],
    parse="single-json",
    response_path=["result"],
    input_tokens_path=["usage", "input_tokens"],
    output_tokens_path=["usage", "output_tokens"],
    cost_path=["total_cost_usd"],
    version_argv=("agy", "--version"),
)

PI_AGENT = HarnessConfig(
    name="pi-agent",
    command=["pi", "-p", "{prompt}", "--mode", "json", "--no-session"],
    model_flag=["--model", "{model}"],
    parse="jsonl",
    # Final assistant text: _find_last walks events in reverse; turn_end carries
    # the assistant message that ended the last turn. _dig steps through the
    # content block list to the block that has a "text" key.
    response_path=["message", "content", "text"],
    input_tokens_path=["message", "usage", "input"],
    output_tokens_path=["message", "usage", "output"],
    cost_path=["message", "usage", "cost", "total"],
    tool_call_event_types=("tool_execution_start",),
    # usage/cost are per-turn on assistant message_end events; a multi-turn run
    # must SUM them, not take last-wins. user/toolResult message_end events
    # carry no usage, so they contribute nothing.
    sum_usage_event_types=("message_end",),
    version_argv=("pi", "--version"),
)

OPENCODE = HarnessConfig(
    name="opencode",
    command=["opencode", "run", "--format", "json", "{prompt}"],
    # opencode wants provider/model form, e.g. opencode-go/muse-spark
    model_flag=["--model", "{model}"],
    parse="jsonl",
    response_path=["text"],
    input_tokens_path=["usage", "input_tokens"],
    output_tokens_path=["usage", "output_tokens"],
    cost_path=["cost_usd"],
    tool_call_event_types=("tool_call", "tool"),
    version_argv=("opencode", "--version"),
)

REGISTRY: dict[str, HarnessConfig] = {
    "claude-code": CLAUDE_CODE,
    "codex-cli": CODEX_CLI,
    "antigravity": ANTIGRAVITY,
    "pi-agent": PI_AGENT,
    "opencode": OPENCODE,
}
