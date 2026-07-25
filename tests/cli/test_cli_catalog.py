from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

import fairypcbot.cli as cli_module
from fairypcbot.catalog.base import CatalogFetchError
from fairypcbot.cli import app
from fairypcbot.schemas.component_part import ComponentPart, PackageSpec

runner = CliRunner()


class _FakeResolverOk:
    def __init__(self, *args, **kwargs):
        pass

    def fetch_stub_with_hash(self, lcsc_id: str) -> tuple[ComponentPart, str]:
        part = ComponentPart(
            kind="component_part",
            id=lcsc_id,
            class_=None,
            mpn="FAKE-MPN",
            manufacturer="FakeCorp",
            package=PackageSpec(name="SOIC-8", source="easyeda"),
            pinout={},
        )
        return part, "0" * 64


class _FakeResolverFail:
    def __init__(self, *args, **kwargs):
        pass

    def fetch_stub_with_hash(self, lcsc_id: str) -> tuple[ComponentPart, str]:
        raise CatalogFetchError("rede indisponível")


def test_catalog_fetch_writes_stub_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(cli_module, "EasyedaResolver", _FakeResolverOk)
    result = runner.invoke(
        app, ["catalog", "fetch", "lcsc:C81036", "-p", str(tmp_path), "--no-audit"]
    )
    assert result.exit_code == 0
    out_file = tmp_path / "library" / "parts" / "lcsc_C81036.yaml"
    assert out_file.exists()
    assert "FAKE-MPN" in out_file.read_text()


def test_catalog_fetch_reports_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(cli_module, "EasyedaResolver", _FakeResolverFail)
    result = runner.invoke(
        app, ["catalog", "fetch", "lcsc:C1", "-p", str(tmp_path), "--no-audit"]
    )
    assert result.exit_code == 1
