from __future__ import annotations

from fairypcbot.schemas.errors import ValidationErrorItem
from fairypcbot.schemas.intent import PartSpec
from fairypcbot.validate.loader import ProjectGraph


def check_designator_uniqueness(
    graph: ProjectGraph,
) -> tuple[dict[str, PartSpec], list[ValidationErrorItem]]:
    combined, dup_errors = graph.combined_parts()
    return combined, dup_errors
