"""Per-page text extraction + assembly of the `DatasheetExtract` skeleton."""

from __future__ import annotations

import inspect
from datetime import UTC, datetime
from pathlib import Path

from pypdf import PdfReader

from fairypcbot.audit.hashing import sha256_file
from fairypcbot.registry.models import get_model
from fairypcbot.schemas.component_class import ComponentClass
from fairypcbot.schemas.datasheet import DatasheetExtract, RatingItem, SourcePdf


def extract_text_pages(pdf_path: Path) -> list[str]:
    """Raw text per page — never raises on a malformed PDF, just returns an empty string for the
    page that fails (graceful degradation, consistent with the rest of the catalog)."""
    reader = PdfReader(str(pdf_path))
    pages: list[str] = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:  # noqa: BLE001 — PDF extraction is best-effort, must never abort ingest
            pages.append("")
    return pages


def write_text_pages(pages: list[str], out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, text in enumerate(pages, start=1):
        page_path = out_dir / f"page_{i:03d}.txt"
        page_path.write_text(text, encoding="utf-8")
        paths.append(page_path)
    return paths


def _checklist_param_names(component_class: ComponentClass | None) -> list[str]:
    if component_class is None:
        return []
    names = list(dict.fromkeys(component_class.params.get("required", [])))
    for model_name in component_class.models.values():
        fn = get_model(model_name)
        if fn is None:
            continue
        for param_name in inspect.signature(fn).parameters:
            if param_name not in names:
                names.append(param_name)
    return names


def build_skeleton(
    *,
    datasheet_id: str,
    mpn_family: list[str],
    pdf_path: Path,
    component_class: ComponentClass | None = None,
    source_url: str | None = None,
) -> DatasheetExtract:
    """`source_url`, when provided, becomes the canonical origin (`SourcePdf.path_or_url`) — the
    manufacturer's public URL, not the local path used to read the file. Without `source_url`, the
    local path becomes the origin by default (honest fallback: we do not pretend to have a URL that
    was not given), but this should be the exception, not the rule — a local path does not survive
    the session that created it (see the documentation)."""
    digest = sha256_file(pdf_path)
    checklist = _checklist_param_names(component_class)

    return DatasheetExtract(
        kind="datasheet_extract",
        id=datasheet_id,
        mpn_family=mpn_family,
        source_pdf=SourcePdf(
            path_or_url=source_url or str(pdf_path),
            local_path=str(pdf_path) if source_url else None,
            sha256=digest,
            accessed=datetime.now(UTC).isoformat(),
        ),
        document_version=None,
        document_version_status="unreadable",
        electrical=[
            RatingItem(symbol="", param=name, extraction_status="needs_user")
            for name in checklist
        ],
    )
