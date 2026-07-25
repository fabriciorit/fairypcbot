"""Base shared by all fairypcbot pydantic schemas."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class FairyBaseModel(BaseModel):
    """Base model used by all fairypcbot schemas.

    `extra="forbid"` is deliberate: since the LLM authors the YAML, mistyped fields must
    become an immediate validation error instead of being silently ignored.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, populate_by_name=True)


# Physical types reused across the intent/class/object schemas.
Millimeters = Annotated[float, Field(gt=0)]
NonNegativeMillimeters = Annotated[float, Field(ge=0)]
