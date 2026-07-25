"""Schema for structured datasheet extraction (`library/datasheets/*.yaml`).

**The datasheet is always the canonical reference** (a normative project principle — for the
published revision of the document). Fixed source precedence: datasheet > API/web > estimate.
APIs (EasyEDA, etc.) are a convenience, never authoritative — see the documentation/the documentation.

Each extracted item carries a `source` (PDF page/section) and an `extraction_status` —
extraction never feigns a certainty it doesn't have. `document_version` is **mandatory to
attempt**: if it cannot be read, that is recorded explicitly (`document_version_status`)
rather than omitted — the absence of a version is itself information (LLM reading failure, or
a manufacturer that doesn't version its documents).
"""

from __future__ import annotations

from typing import Any, Literal

from fairypcbot.schemas.base import FairyBaseModel
from fairypcbot.schemas.provenance import Provenance

ExtractionStatus = Literal["extracted", "approximate", "gave_up", "needs_user"]


class SourceRef(FairyBaseModel):
    page: int | None = None
    section: str | None = None


class SourcePdf(FairyBaseModel):
    """`path_or_url` is the canonical ORIGIN of the document — the manufacturer's public URL
    when available (`fae datasheet ingest --source-url ...`), never a temporary local path. A
    local path is only acceptable when the document genuinely has no public URL (confidential,
    received by email, etc.) — in that case a stable path is still preferable (e.g. inside the
    library itself), not `/tmp/...`, which stops existing after the session that generated the
    stub (actual finding: a `/tmp/...` path was recorded by mistake during a field test — see
    the documentation). `local_path`, if present, is only where the file was read during `ingest` — it is
    not the document's identity, it is operational metadata (useful for auditing how the hash
    was computed, not for reproducing/re-fetching the document later)."""

    path_or_url: str
    local_path: str | None = None
    sha256: str
    accessed: str  # ISO date/datetime — when the PDF was obtained/hashed


class ExtractedItem(FairyBaseModel):
    """Common base for any extracted item: where it came from, how confident, whether confirmed."""

    source: SourceRef = SourceRef()
    extraction_status: ExtractionStatus = "needs_user"
    verified_by: Literal["user"] | None = None
    notes: str = ""


class IdentificationItem(ExtractedItem):
    key: str
    value: str


class RatingItem(ExtractedItem):
    symbol: str
    param: str | None = None  # canonical parameter name for the class, when applicable
    min: float | None = None
    typ: float | None = None
    max: float | None = None
    unit: str = ""
    conditions: dict[str, Any] = {}


class PinoutEntry(ExtractedItem):
    package_ref: str | None = None  # reference to a component_package (family[:variant])
    pin_number: str
    pin_name: str
    pin_type: Literal["power", "gnd", "input", "output", "io", "analog", "nc", "other"] = "other"
    description: str = ""


class FunctionTableItem(ExtractedItem):
    name: str
    inputs: list[str] = []
    outputs: list[str] = []
    rows: list[dict[str, str]] = []


class FormulaItem(ExtractedItem):
    name: str
    expression: str
    variables: dict[str, str] = {}  # symbol -> description/unit


class LayoutGuidanceItem(ExtractedItem):
    text: str
    intent_type: str | None = None  # e.g. "decouples", "current_loop_minimize"
    intent_params: dict[str, Any] = {}


class CurveAxis(FairyBaseModel):
    quantity: str
    unit: str = ""
    scale: Literal["linear", "log"] = "linear"


class CurveSeries(FairyBaseModel):
    conditions: dict[str, Any] = {}
    points: list[list[float]] = []  # [[x, y], ...] — empty when only the reference was captured
    approximate: bool = True


class CurveItem(ExtractedItem):
    title: str
    x: CurveAxis
    y: CurveAxis
    series: list[CurveSeries] = []


class BehaviorItem(ExtractedItem):
    name: str
    summary: str


class DatasheetExtract(FairyBaseModel):
    fairypcbot: str = "0.1"
    kind: Literal["datasheet_extract"]
    id: str
    mpn_family: list[str] = []
    source_pdf: SourcePdf
    document_version: str | None = None
    document_version_status: Literal["read", "unreadable", "absent"] = "unreadable"

    identification: list[IdentificationItem] = []
    absolute_maximum: list[RatingItem] = []
    operating_conditions: list[RatingItem] = []
    electrical: list[RatingItem] = []
    pinout: list[PinoutEntry] = []
    land_package_ref: str | None = None
    function_tables: list[FunctionTableItem] = []
    formulas: list[FormulaItem] = []
    layout_guidance: list[LayoutGuidanceItem] = []
    thermal: list[RatingItem] = []
    reflow: list[RatingItem] = []
    curves: list[CurveItem] = []
    behaviors: list[BehaviorItem] = []

    provenance: dict[str, Provenance] = {}
