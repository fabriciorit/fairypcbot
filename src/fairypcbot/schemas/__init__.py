"""Pydantic v2 schemas for fairypcbot.

The import order below is significant: `intents_builtin` must register its types with the
registry (`registry.intents`) before `intent.py` assembles the discriminated union used by
`Intent.intents`. Importing this package (`fairypcbot.schemas`) guarantees that order at any
entry point (CLI, tests).
"""

from fairypcbot.schemas import intents_builtin  # noqa: F401  (registers types with the registry)
from fairypcbot.schemas.audit import AuditEvent, FileRef
from fairypcbot.schemas.component_class import ComponentClass, PinSpec, RuleRef
from fairypcbot.schemas.component_part import ComponentPart, PackageSpec
from fairypcbot.schemas.errors import ValidationErrorItem, ValidationReport
from fairypcbot.schemas.intent import (
    Board,
    ImportRef,
    Intent,
    MountingHole,
    Outline,
    PartByCatalog,
    PartByClass,
    PlacementHint,
)

__all__ = [
    "AuditEvent",
    "Board",
    "ComponentClass",
    "ComponentPart",
    "FileRef",
    "ImportRef",
    "Intent",
    "MountingHole",
    "Outline",
    "PackageSpec",
    "PartByCatalog",
    "PartByClass",
    "PinSpec",
    "PlacementHint",
    "RuleRef",
    "ValidationErrorItem",
    "ValidationReport",
]
