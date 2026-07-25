"""Provenance of catalog data (spec section 7).

Every piece of data obtained from external sources (or left open for the LLM to complete)
carries provenance: where it came from, a reference (URL/hash), and when it was obtained.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fairypcbot.schemas.base import FairyBaseModel


class Provenance(FairyBaseModel):
    source: Literal["easyeda_api", "datasheet", "llm", "user", "missing"]
    ref: str = ""
    timestamp: datetime
    # sha256 of the RAW BYTES of the source (whole PDF; HTTP response as received) — never of a
    # "canonical" subset: a hash that hides changes lies by omission. A false "changed" caused
    # by a volatile server field is an accepted cost (a normative project principle, see the documentation).
    sha256: str | None = None
