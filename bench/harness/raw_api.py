"""raw-api harness: the baseline every CLI harness is compared against.

A minimal Anthropic tool-use loop with exactly 3 tools (bash, read_file,
write_file), all executing inside the same sandbox the CLI harnesses use.
This is the one genuinely new piece of agent logic in the system -- every
other harness shells out to an existing CLI.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from .. import sandbox as sandbox_mod

MAX_TURNS = 20
MAX_TOKENS = 4096

TOOLS = [
    {
        "name": "bash",
        "description": "Run a shell command in the task sandbox and return its stdout/stderr/exit code.",
        "input_schema": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
    },
    {
        "name": "read_file",
        "description": "Read a file from the task sandbox.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Write (overwrite) a file in the task sandbox.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    },
]


@dataclass
class RawApiResult:
    response_text: str
    input_tokens: int
    output_tokens: int
    tool_call_count: int
    wall_clock_seconds: float


def _resolve_in_sandbox(sb: sandbox_mod.Sandbox, path: str) -> Path:
    target = (sb.workdir / path).resolve()
    if not target.is_relative_to(sb.workdir.resolve()):
        raise PermissionError(f"path escapes the task workspace: {path}")
    return target


def _execute_tool(sb: sandbox_mod.Sandbox, name: str, tool_input: dict) -> str:
    if name == "bash":
        proc = sandbox_mod.exec_in(sb, tool_input["command"])
        return f"exit={proc.returncode}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    if name == "read_file":
        try:
            target = _resolve_in_sandbox(sb, tool_input["path"])
            return target.read_text()
        except (OSError, ValueError) as e:
            return f"error reading {tool_input['path']}: {e}"
    if name == "write_file":
        try:
            target = _resolve_in_sandbox(sb, tool_input["path"])
        except (OSError, ValueError) as e:
            return f"error writing {tool_input['path']}: {e}"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(tool_input["content"])
        return f"wrote {tool_input['path']}"
    return f"unknown tool {name}"


def run(sb: sandbox_mod.Sandbox, instruction: str, model: str) -> RawApiResult:
    import anthropic  # lazy import: not required for tasks graded without raw-api

    client = anthropic.Anthropic()
    messages: list = [{"role": "user", "content": instruction}]
    input_tokens = 0
    output_tokens = 0
    tool_call_count = 0
    final_text = ""
    start = time.monotonic()

    for _ in range(MAX_TURNS):
        resp = client.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            tools=TOOLS,
            messages=messages,
        )
        input_tokens += resp.usage.input_tokens
        output_tokens += resp.usage.output_tokens

        text_parts = [b.text for b in resp.content if b.type == "text"]
        if text_parts:
            final_text = "\n".join(text_parts)

        tool_uses = [b for b in resp.content if b.type == "tool_use"]
        if not tool_uses:
            break

        messages.append({"role": "assistant", "content": resp.content})
        tool_results = []
        for tu in tool_uses:
            tool_call_count += 1
            output = _execute_tool(sb, tu.name, tu.input)
            tool_results.append({"type": "tool_result", "tool_use_id": tu.id, "content": output})
        messages.append({"role": "user", "content": tool_results})

    elapsed = time.monotonic() - start
    return RawApiResult(
        response_text=final_text,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        tool_call_count=tool_call_count,
        wall_clock_seconds=elapsed,
    )
