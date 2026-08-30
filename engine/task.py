from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import markdown as md


@dataclass
class SeedFile:
    path: str
    content: str


@dataclass
class Task:
    id: str
    path: Path
    dimensions: str
    difficulty: str
    instruction: str
    seed_files: list[SeedFile]
    setup_script: str | None
    constraints: str


def parse_task(path: Path) -> Task:
    text = path.read_text()

    dimensions = md.extract_bold_field(text, "dimension(s)") or ""
    difficulty = md.extract_bold_field(text, "difficulty tier") or ""
    instruction = (md.extract_section(text, "Instruction") or "").strip()
    env_section = md.extract_section(text, "Environment/setup") or ""
    setup_section = md.extract_section(text, "Setup")
    constraints = (md.extract_section(text, "Constraints") or "").strip()

    seed_files = [
        SeedFile(path=p, content=c) for p, c in md.extract_seed_files(env_section)
    ]
    setup_script = md.first_bash_block(setup_section) if setup_section else None

    # Required-field validation: a task with an empty id/instruction/
    # dimension used to run the full harness pipeline and record a real
    # "fail" against blank data (F-10 data-integrity hole).
    # id derives from the filename stem; a name that IS all suffix (".md")
    # has no stem (Path('.md').stem == '.md' is dotfile trivia).
    task_id = "" if path.stem == path.name else path.stem
    for field_name, value in (
        ("id", task_id),
        ("instruction", instruction),
        ("dimension(s)", dimensions),
    ):
        if not value:
            raise ValueError(f"Task {path}: missing required field '{field_name}'")

    if "## Setup" in text and not setup_script:
        raise ValueError(f"Task {path.stem} contains '## Setup' but failed to extract a bash block.")
    if "## Environment/setup" in text and not env_section and not seed_files:
        raise ValueError(f"Task {path.stem} contains '## Environment/setup' but extracted nothing.")

    return Task(
        id=path.stem,
        path=path,
        dimensions=dimensions,
        difficulty=difficulty,
        instruction=instruction,
        seed_files=seed_files,
        setup_script=setup_script,
        constraints=constraints,
    )
