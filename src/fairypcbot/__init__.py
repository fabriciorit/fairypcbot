"""fairypcbot (fae) — intent-driven PCB design framework."""

from __future__ import annotations

#: Derived from git by hatch-vcs at build time (see pyproject.toml). In a release build this is a
#: plain `X.Y.Z`; between tags it carries the commit as a PEP 440 local segment
#: (`0.1.1.dev8+gf42f706`), which is how `fae version` recovers the commit when no checkout is
#: available. Importing must never fail over this, so both lookups degrade instead of raising.
try:
    from fairypcbot._version import __version__
except ImportError:  # pragma: no cover — not built by hatch-vcs (e.g. a bare source tree)
    from importlib.metadata import PackageNotFoundError, version

    try:
        __version__ = version("fairypcbot")
    except PackageNotFoundError:
        __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
