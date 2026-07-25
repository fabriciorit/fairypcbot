"""Access to `docs/llm/` (vendor-neutral documentation for LLMs) under any installation form.

Packaged as package data (`[tool.hatch.build.targets.wheel.force-include]` in pyproject.toml:
`docs/llm` -> `fairypcbot/docs/llm`), so that `fae llm` works from any pip installation, without
requiring the repository to be cloned. In an editable install (development), the force-include may
not materialize the path — in that case, fall back to locating `docs/llm` by walking up from this
module's directory until `pyproject.toml` is found (same heuristic as
`validate/library.py::resolve_library_paths`).
"""

from __future__ import annotations

import importlib.resources
from pathlib import Path


def llm_docs_dir() -> Path:
    try:
        packaged = importlib.resources.files("fairypcbot") / "docs" / "llm"
        if packaged.is_dir():
            return Path(str(packaged))
    except (ModuleNotFoundError, FileNotFoundError):
        pass

    current = Path(__file__).resolve().parent
    while current != current.parent:
        candidate = current / "docs" / "llm"
        if (current / "pyproject.toml").exists() and candidate.is_dir():
            return candidate
        current = current.parent

    raise FileNotFoundError(
        "docs/llm not found — neither packaged nor locatable from the repository"
    )


def list_topics() -> list[str]:
    docs_dir = llm_docs_dir()
    return sorted(p.stem for p in docs_dir.glob("*.md") if p.stem != "INDEX")


def read_index() -> str:
    return (llm_docs_dir() / "INDEX.md").read_text(encoding="utf-8")


def read_topic(name: str) -> str | None:
    path = llm_docs_dir() / f"{name}.md"
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")
