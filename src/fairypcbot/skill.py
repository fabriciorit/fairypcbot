"""Access to `docs/skill/SKILL.md` — the portable, vendor-neutral skill for any LLM.

Same packaging strategy as `llm_docs` (`force-include` in pyproject.toml), so `fae skill` works
from any pip installation without the repository being cloned.

Why the CLI renders it instead of the file being read directly from the repo root: the skill has
to state *which* fairypcbot it describes, and a file cannot contain the hash of the commit that
contains it. Serving it through the CLI resolves that identity at read time (`version_info`), so
the emitted skill always describes the tree it was emitted from — no stamp to keep in sync, and
nothing that can silently go stale.
"""

from __future__ import annotations

import importlib.resources
import json
from pathlib import Path

from fairypcbot import version_info

IDENTITY_MARKER = "<!-- fae:identity -->"


def skill_dir() -> Path:
    try:
        packaged = importlib.resources.files("fairypcbot") / "docs" / "skill"
        if packaged.is_dir():
            return Path(str(packaged))
    except (ModuleNotFoundError, FileNotFoundError):
        pass

    current = Path(__file__).resolve().parent
    while current != current.parent:
        candidate = current / "docs" / "skill"
        if (current / "pyproject.toml").exists() and candidate.is_dir():
            return candidate
        current = current.parent

    raise FileNotFoundError(
        "docs/skill not found — neither packaged nor locatable from the repository"
    )


def skill_path() -> Path:
    return skill_dir() / "SKILL.md"


def read_raw() -> str:
    """The skill as stored, with the identity marker unresolved."""
    return skill_path().read_text(encoding="utf-8")


def _yaml_scalar(value: str | bool | None) -> str:
    """Render a scalar as YAML, not as a Python repr (`None` is not `null`)."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    return json.dumps(value, ensure_ascii=False)


def render_identity_block() -> str:
    """The resolved identity, as a markdown block an LLM or a parser can read."""
    info = version_info.resolve()
    lines = [
        "```yaml",
        "# resolved by `fae skill` at read time — describes the running installation",
        f"version: {_yaml_scalar(info.version)}",
    ]
    if info.commit:
        lines += [
            f"commit: {_yaml_scalar(info.commit)}",
            f"commit_short: {_yaml_scalar(info.commit_short)}",
            f"commit_date: {_yaml_scalar(info.commit_date)}",
            f"branch: {_yaml_scalar(info.branch)}",
            f"tag: {_yaml_scalar(info.tag)}",
            f"dirty: {_yaml_scalar(bool(info.dirty))}   # true = local edits, not in any commit",
        ]
    else:
        lines += [
            "commit: null   # no checkout and no build stamp — unknowable, not omitted",
        ]
    lines += [
        f"commit_source: {_yaml_scalar(info.commit_source)}   # git | build_stamp | unknown",
        f"editable_install: {_yaml_scalar(info.editable)}",
        f"install_path: {_yaml_scalar(info.install_path)}",
        f"python: {_yaml_scalar(info.python)}",
        "```",
    ]
    if info.dirty:
        lines.append(
            "\n**The worktree is dirty** — there are edits not present in any commit, so the hash "
            "above does not fully describe the code you are driving. Verify behavior directly "
            "(`fae <cmd> --help`, `fae schema <name>`) instead of trusting documented specifics."
        )
    if info.commit_source == "unknown":
        lines.append(
            "\n**The commit could not be resolved** — this is a plain install with no checkout and "
            "no build stamp. Only the version label is available; say so if precision matters."
        )
    return "\n".join(lines)


def render() -> str:
    """The skill with its identity block resolved for the running installation."""
    raw = read_raw()
    block = render_identity_block()
    if IDENTITY_MARKER in raw:
        return raw.replace(IDENTITY_MARKER, block)
    return f"{raw}\n\n## Running installation\n\n{block}\n"
