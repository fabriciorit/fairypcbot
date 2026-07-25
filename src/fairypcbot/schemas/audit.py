"""Pydantic schema for audit trail events (spec section 8)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fairypcbot.schemas.base import FairyBaseModel


class FileRef(FairyBaseModel):
    path: str
    sha256: str


class AuditEvent(FairyBaseModel):
    ts: datetime
    run_id: str
    phase: Literal[
        "init", "validate", "elaborate", "place", "emit", "render", "routecheck", "catalog",
        "manual",
    ]
    actor: Literal["framework", "llm", "user"]
    event: Literal["decision", "artifact", "validation", "external_call", "prompt", "error"]
    code: str
    summary: str
    detail: dict[str, Any] = {}
    inputs: list[FileRef] = []
    outputs: list[FileRef] = []
