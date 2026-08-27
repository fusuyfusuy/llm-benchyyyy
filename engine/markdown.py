"""Shared parsing helpers for the task/expected markdown convention.

Reuses the fenced-code-block + bold-field prose already written in tasks/ and
expected/ instead of introducing a separate structured format. See scope.md's
"Task schema" section and the plan for the exact conventions this implements.
"""
from __future__ import annotations

import re

_FENCE_RE = re.compile(r"```([\w+-]*)\n(.*?)\n```", re.DOTALL)
_SEED_FILE_FIRSTLINE_RE = re.compile(r"^#\s*(\S+\.\w+)")


def extract_section(text: str, heading: str) -> str | None:
    """Return the body text under `## {heading}` up to the next `## ` heading.

    The heading line may carry trailing prose after the heading itself (e.g.
    `## Rubric (score each 0/1, ...)`) -- matched by prefix, not exact line.
    """
    pattern = re.compile(
        r"^##\s+" + re.escape(heading) + r"\b[^\n]*\n(.*?)(?=^##\s+|\Z)",
        re.DOTALL | re.MULTILINE,
    )
    m = pattern.search(text)
    return m.group(1) if m else None


def extract_bold_field(text: str, label: str) -> str | None:
    """Return the value after `**{label}:**`, joining any wrapped lines."""
    pattern = re.compile(
        r"\*\*" + re.escape(label) + r":\*\*\s*(.+?)(?=\n\*\*[^*\n]+:\*\*|\n\n|\Z)",
        re.DOTALL,
    )
    m = pattern.search(text)
    if not m:
        return None
    return re.sub(r"\s+", " ", m.group(1)).strip()


def extract_fenced_blocks(text: str) -> list[tuple[str, str]]:
    """Return [(language, body)] for every fenced code block in text."""
    return list(_FENCE_RE.findall(text))


def extract_seed_files(text: str) -> list[tuple[str, str]]:
    """Fenced blocks whose first line is `# path/to/file.ext` -> [(path, content)].

    A block with no body after the comment line (a held-out placeholder, e.g. a
    test file the agent under test shouldn't see) is skipped rather than written
    empty -- there's nothing to seed.
    """
    seeds = []
    for _lang, body in extract_fenced_blocks(text):
        lines = body.split("\n")
        m = _SEED_FILE_FIRSTLINE_RE.match(lines[0])
        if not m:
            continue
        filename = m.group(1)
        rest = "\n".join(lines[1:]).strip("\n")
        if not rest.strip():
            continue
        seeds.append((filename, rest + "\n"))
    return seeds


def first_bash_block(text: str) -> str | None:
    """First fenced bash/sh block in text, stripped. None if there isn't one."""
    for lang, body in extract_fenced_blocks(text):
        if lang in ("bash", "sh", ""):
            return body.strip()
    return None
