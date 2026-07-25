from __future__ import annotations

from fairypcbot.schemas.errors import ValidationErrorItem
from fairypcbot.validate.loader import ProjectGraph


def check_imports(graph: ProjectGraph) -> list[ValidationErrorItem]:
    """Cycle/file-not-found/invalid-schema errors are already collected during the
    recursive loading in `resolve_imports`; this check merely exposes them to the runner.
    """
    return list(graph.errors)
