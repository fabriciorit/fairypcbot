from __future__ import annotations

import shutil
from pathlib import Path

from pypdf import PdfWriter
from typer.testing import CliRunner

from fairypcbot.cli import app

runner = CliRunner()


def _make_pdf(path: Path, pages: int = 2) -> None:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    with open(path, "wb") as f:
        writer.write(f)


def _cleanup(project: Path) -> None:
    for d in ("build", "audit", "library/datasheets"):
        p = project / d
        if p.exists():
            shutil.rmtree(p)


def test_ingest_generates_skeleton_and_text(repo_root: Path):
    fixture_project = repo_root / "examples" / "led_blinker_555"
    pdf_path = fixture_project / "_test_datasheet.pdf"
    _make_pdf(pdf_path, pages=2)
    try:
        result = runner.invoke(
            app,
            [
                "datasheet",
                "ingest",
                str(pdf_path),
                "--class",
                "mcu.riscv.ch32v203",
                "-p",
                str(fixture_project),
                "--no-audit",
            ],
        )
        assert result.exit_code == 0
        ds_path = fixture_project / "library" / "datasheets" / "mcu.riscv.ch32v203.yaml"
        assert ds_path.exists()
        content = ds_path.read_text()
        assert "vdd_range_v" in content  # checklist derivado de params.required da classe

        text_dir = fixture_project / "build" / "datasheet_text" / "mcu.riscv.ch32v203"
        assert (text_dir / "page_001.txt").exists()
        assert (text_dir / "page_002.txt").exists()
    finally:
        pdf_path.unlink(missing_ok=True)
        _cleanup(fixture_project)


def test_ingest_missing_pdf_fails(tmp_path: Path):
    result = runner.invoke(app, ["datasheet", "ingest", str(tmp_path / "nope.pdf"), "-p", str(tmp_path)])
    assert result.exit_code == 1


def test_ingest_with_source_url_records_url_not_local_path(repo_root: Path):
    """Real finding: a local path from /tmp was recorded as the canonical source of a datasheet in
    the field test of the metal detector — see ADR-013. --source-url fixes this."""
    fixture_project = repo_root / "examples" / "led_blinker_555"
    pdf_path = fixture_project / "_test_datasheet_url.pdf"
    _make_pdf(pdf_path, pages=1)
    try:
        result = runner.invoke(
            app,
            [
                "datasheet", "ingest", str(pdf_path),
                "--class", "mcu.riscv.ch32v203",
                "--source-url", "https://example.com/datasheet.pdf",
                "-p", str(fixture_project), "--no-audit",
            ],
        )
        assert result.exit_code == 0
        assert "Nenhum --source-url" not in result.stdout

        ds_path = fixture_project / "library" / "datasheets" / "mcu.riscv.ch32v203.yaml"
        from fairypcbot.schemas.datasheet import DatasheetExtract
        from fairypcbot.validate.loader import load_yaml

        ds = DatasheetExtract.model_validate(load_yaml(ds_path))
        assert ds.source_pdf.path_or_url == "https://example.com/datasheet.pdf"
        assert ds.source_pdf.local_path == str(pdf_path)
    finally:
        pdf_path.unlink(missing_ok=True)
        _cleanup(fixture_project)


def test_ingest_without_source_url_warns_and_uses_local_path(repo_root: Path):
    fixture_project = repo_root / "examples" / "led_blinker_555"
    pdf_path = fixture_project / "_test_datasheet_nourl.pdf"
    _make_pdf(pdf_path, pages=1)
    try:
        result = runner.invoke(
            app,
            [
                "datasheet", "ingest", str(pdf_path),
                "--class", "mcu.riscv.ch32v203",
                "-p", str(fixture_project), "--no-audit",
            ],
        )
        assert result.exit_code == 0
        assert "No --source-url" in result.stdout

        ds_path = fixture_project / "library" / "datasheets" / "mcu.riscv.ch32v203.yaml"
        from fairypcbot.schemas.datasheet import DatasheetExtract
        from fairypcbot.validate.loader import load_yaml

        ds = DatasheetExtract.model_validate(load_yaml(ds_path))
        assert ds.source_pdf.path_or_url == str(pdf_path)
        assert ds.source_pdf.local_path is None  # without --source-url, there is no distinction to make
    finally:
        pdf_path.unlink(missing_ok=True)
        _cleanup(fixture_project)


def test_ingest_unknown_class_still_generates_empty_skeleton(repo_root: Path):
    fixture_project = repo_root / "examples" / "led_blinker_555"
    pdf_path = fixture_project / "_test_datasheet2.pdf"
    _make_pdf(pdf_path, pages=1)
    try:
        result = runner.invoke(
            app,
            [
                "datasheet", "ingest", str(pdf_path),
                "--class", "does.not.exist",
                "-p", str(fixture_project), "--no-audit",
            ],
        )
        assert result.exit_code == 0
        ds_path = fixture_project / "library" / "datasheets" / "does.not.exist.yaml"
        assert ds_path.exists()
    finally:
        pdf_path.unlink(missing_ok=True)
        _cleanup(fixture_project)


def test_review_bulk_confirm_marks_verified(repo_root: Path):
    fixture_project = repo_root / "examples" / "led_blinker_555"
    pdf_path = fixture_project / "_test_datasheet3.pdf"
    _make_pdf(pdf_path, pages=1)
    try:
        runner.invoke(
            app,
            [
                "datasheet", "ingest", str(pdf_path),
                "--class", "mcu.riscv.ch32v203",
                "-p", str(fixture_project), "--no-audit",
            ],
        )
        result = runner.invoke(
            app,
            ["datasheet", "review", "mcu.riscv.ch32v203", "-p", str(fixture_project), "--all", "--no-audit"],
        )
        assert result.exit_code == 0
        assert "verified_by=user" in result.stdout

        ds_path = fixture_project / "library" / "datasheets" / "mcu.riscv.ch32v203.yaml"
        assert "verified_by: user" in ds_path.read_text()
    finally:
        pdf_path.unlink(missing_ok=True)
        _cleanup(fixture_project)


def test_review_nonexistent_datasheet_fails(tmp_path: Path):
    result = runner.invoke(app, ["datasheet", "review", "does-not-exist", "-p", str(tmp_path)])
    assert result.exit_code == 1
