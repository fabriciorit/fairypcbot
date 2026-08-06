"""Runtime identity of the running fairypcbot — version *and*, when resolvable, the exact commit.

A version string is a label chosen by a human: two different trees can carry `0.1.0`. A commit
hash identifies one tree exactly. Whoever is driving the framework (especially an LLM) needs the
second one to know what it is actually talking to, so this module resolves it at call time rather
than trusting anything stamped into a file.

Resolution order:

1. **git** — if the package is running from a checkout (source install, `pip install -e`, or the
   repository itself), ask git directly. This is authoritative and also reports a dirty worktree,
   which no stamp can describe.
2. **build stamp** — `fairypcbot/_build_info.json`, written at build time when the wheel is built
   from a checkout. Covers `pip install` from a plain wheel/sdist.
3. **unknown** — a plain PyPI install with no stamp genuinely cannot know its commit; the field
   stays `None` with `commit_source: "unknown"` rather than being guessed. Never fabricate it.
"""

from __future__ import annotations

import json
import platform
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

import fairypcbot

_BUILD_INFO_FILENAME = "_build_info.json"


@dataclass
class VersionInfo:
    """Everything needed to identify this fairypcbot unambiguously."""

    version: str
    commit: str | None
    commit_short: str | None
    commit_date: str | None
    branch: str | None
    dirty: bool | None
    tag: str | None
    commit_source: str  # "git" | "build_stamp" | "unknown"
    install_path: str
    editable: bool
    python: str

    def to_json_str(self) -> str:
        return json.dumps(asdict(self), indent=2, ensure_ascii=False)


def _run_git(repo: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def find_repo_root() -> Path | None:
    """Walk up from this module looking for the checkout that contains it."""
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / ".git").exists() and (current / "pyproject.toml").exists():
            return current
        current = current.parent
    return None


def _build_stamp() -> dict[str, str] | None:
    stamp = Path(__file__).resolve().parent / _BUILD_INFO_FILENAME
    if not stamp.is_file():
        return None
    try:
        data = json.loads(stamp.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _is_editable() -> bool:
    import importlib.metadata as md

    try:
        raw = md.distribution("fairypcbot").read_text("direct_url.json")
    except (md.PackageNotFoundError, OSError):
        return False
    if not raw:
        return False
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return False
    return bool(parsed.get("dir_info", {}).get("editable", False))


def resolve() -> VersionInfo:
    """Resolve the running installation's identity. Never raises, never invents a commit."""
    base = {
        "version": fairypcbot.__version__,
        "commit": None,
        "commit_short": None,
        "commit_date": None,
        "branch": None,
        "dirty": None,
        "tag": None,
        "commit_source": "unknown",
        "install_path": str(Path(fairypcbot.__file__).resolve().parent),
        "editable": _is_editable(),
        "python": platform.python_version(),
    }

    repo = find_repo_root()
    if repo is not None:
        commit = _run_git(repo, "rev-parse", "HEAD")
        if commit:
            status = _run_git(repo, "status", "--porcelain")
            branch = _run_git(repo, "rev-parse", "--abbrev-ref", "HEAD")
            base.update(
                commit=commit,
                commit_short=commit[:7],
                commit_date=_run_git(repo, "log", "-1", "--format=%cs"),
                branch=None if branch == "HEAD" else branch,
                dirty=bool(status),
                tag=_run_git(repo, "describe", "--tags", "--exact-match"),
                commit_source="git",
            )
            return VersionInfo(**base)  # type: ignore[arg-type]

    stamp = _build_stamp()
    if stamp and stamp.get("commit"):
        commit = str(stamp["commit"])
        base.update(
            commit=commit,
            commit_short=commit[:7],
            commit_date=stamp.get("commit_date"),
            branch=stamp.get("branch"),
            dirty=stamp.get("dirty"),
            tag=stamp.get("tag"),
            commit_source="build_stamp",
        )

    return VersionInfo(**base)  # type: ignore[arg-type]


def describe() -> str:
    """One-line human/LLM readable identity, e.g. `0.1.0 @ e18056f (main, clean) [git]`."""
    info = resolve()
    if info.commit_short is None:
        return f"{info.version} @ commit unknown [{info.commit_source}]"
    parts = [info.branch or "detached", "dirty" if info.dirty else "clean"]
    tag = f", tag {info.tag}" if info.tag else ""
    return (
        f"{info.version} @ {info.commit_short} ({', '.join(parts)}{tag}) [{info.commit_source}]"
    )
