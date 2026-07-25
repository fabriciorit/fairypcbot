from __future__ import annotations

from fairypcbot.schemas.datasheet import DatasheetExtract, RatingItem, SourcePdf


def _base(**overrides):
    data = {
        "kind": "datasheet_extract",
        "id": "mcu.generic",
        "source_pdf": {"path_or_url": "/tmp/x.pdf", "sha256": "a" * 64, "accessed": "2026-01-01"},
    }
    data.update(overrides)
    return DatasheetExtract.model_validate(data)


def test_minimal_valid_datasheet():
    ds = _base()
    assert ds.document_version_status == "unreadable"  # default honesto: não afirma "read"
    assert ds.electrical == []


def test_document_version_status_absent_accepted():
    ds = _base(document_version_status="absent")
    assert ds.document_version_status == "absent"


def test_electrical_item_defaults_needs_user():
    item = RatingItem(symbol="Rds(on)", param="rds_on_ohm")
    assert item.extraction_status == "needs_user"
    assert item.verified_by is None


def test_source_pdf_requires_sha256():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        SourcePdf.model_validate({"path_or_url": "/tmp/x.pdf", "accessed": "2026-01-01"})


def test_source_pdf_local_path_optional_defaults_none():
    sp = SourcePdf(path_or_url="https://example.com/x.pdf", sha256="a" * 64, accessed="2026-01-01")
    assert sp.local_path is None


def test_source_pdf_local_path_set_alongside_url():
    sp = SourcePdf(
        path_or_url="https://example.com/x.pdf",
        local_path="/tmp/x.pdf",
        sha256="a" * 64,
        accessed="2026-01-01",
    )
    assert sp.path_or_url == "https://example.com/x.pdf"
    assert sp.local_path == "/tmp/x.pdf"


def test_curve_item_points_default_empty_and_approximate():
    from fairypcbot.schemas.datasheet import CurveAxis, CurveItem

    curve = CurveItem(
        title="Efficiency",
        x=CurveAxis(quantity="load_current", unit="A"),
        y=CurveAxis(quantity="efficiency", unit="pct"),
    )
    assert curve.series == []
