"""Stable validation error/warning format — designed for LLM consumption."""

from __future__ import annotations

import json

from fairypcbot.schemas.base import FairyBaseModel


class ValidationErrorItem(FairyBaseModel):
    path: str
    code: str
    message: str
    suggestion: str


class ValidationReport(FairyBaseModel):
    ok: bool
    errors: list[ValidationErrorItem] = []
    warnings: list[ValidationErrorItem] = []

    def to_json_str(self) -> str:
        return json.dumps(self.model_dump(mode="json"), ensure_ascii=False, indent=2)


class LintReport(FairyBaseModel):
    """Electrical linter report (stage 3, spec section 4) — three severities: error/warning/info."""

    ok: bool
    errors: list[ValidationErrorItem] = []
    warnings: list[ValidationErrorItem] = []
    infos: list[ValidationErrorItem] = []

    def to_json_str(self) -> str:
        return json.dumps(self.model_dump(mode="json"), ensure_ascii=False, indent=2)
