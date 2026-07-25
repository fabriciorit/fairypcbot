from __future__ import annotations

from fairypcbot.schemas.component_class import ComponentClass
from fairypcbot.schemas.component_package import ComponentPackage
from fairypcbot.schemas.component_part import ComponentPart, PackageSpec
from fairypcbot.schemas.datasheet import DatasheetExtract, RatingItem, SourcePdf
from fairypcbot.schemas.error_codes import ErrorCode
from fairypcbot.schemas.intent import PartByCatalog
from fairypcbot.validate.checks.datasheets import check_datasheets
from fairypcbot.validate.library import LibraryIndex


class _FakeLibrary(LibraryIndex):
    def __init__(self, classes=None, parts=None, packages=None, datasheets=None):
        self.classes = classes or {}
        self.parts = parts or {}
        self.packages = packages or {}
        self.datasheets = datasheets or {}
        self._package_aliases = {}


def _resistor_class():
    return ComponentClass(
        kind="component_class", id="resistor", params={"required": ["resistance_ohm"]}
    )


def _part(package_ref=None, datasheet_ref=None):
    return ComponentPart(
        kind="component_part",
        id="lcsc:C1",
        **{"class": "resistor"},
        mpn="X",
        manufacturer="Y",
        package=PackageSpec(name="R0402", source="easyeda", ref=package_ref),
        datasheet_ref=datasheet_ref,
    )


def test_no_datasheet_ref_no_findings():
    library = _FakeLibrary(classes={"resistor": _resistor_class()}, parts={"lcsc:C1": _part()})
    errors, warnings = check_datasheets({"R1": PartByCatalog(part="lcsc:C1")}, library)
    assert errors == []
    assert warnings == []


def test_missing_datasheet_ref_is_error():
    library = _FakeLibrary(
        classes={"resistor": _resistor_class()},
        parts={"lcsc:C1": _part(datasheet_ref="does-not-exist")},
    )
    errors, warnings = check_datasheets({"R1": PartByCatalog(part="lcsc:C1")}, library)
    assert len(errors) == 1
    assert errors[0].code == ErrorCode.E_DATASHEET_NOT_FOUND


def test_package_ref_not_found_is_warning():
    library = _FakeLibrary(
        classes={"resistor": _resistor_class()},
        parts={"lcsc:C1": _part(package_ref="nonexistent-family")},
    )
    errors, warnings = check_datasheets({"R1": PartByCatalog(part="lcsc:C1")}, library)
    assert errors == []
    assert any(w.code == ErrorCode.W_PACKAGE_REF_NOT_FOUND for w in warnings)


def test_package_ref_found_no_warning():
    library = _FakeLibrary(
        classes={"resistor": _resistor_class()},
        parts={"lcsc:C1": _part(package_ref="r0402")},
        packages={"r0402": ComponentPackage(kind="component_package", id="r0402", variants={"x": {}})},
    )
    errors, warnings = check_datasheets({"R1": PartByCatalog(part="lcsc:C1")}, library)
    assert warnings == []


def _datasheet(electrical=None, version_status="read"):
    return DatasheetExtract(
        kind="datasheet_extract",
        id="ds1",
        source_pdf=SourcePdf(path_or_url="x.pdf", sha256="a" * 64, accessed="2026-01-01"),
        document_version="Rev 2",
        document_version_status=version_status,
        electrical=electrical or [],
    )


def test_incomplete_electrical_coverage_is_warning():
    library = _FakeLibrary(
        classes={"resistor": _resistor_class()},
        parts={"lcsc:C1": _part(datasheet_ref="ds1")},
        datasheets={"ds1": _datasheet(electrical=[])},
    )
    errors, warnings = check_datasheets({"R1": PartByCatalog(part="lcsc:C1")}, library)
    assert any(w.code == ErrorCode.W_DATASHEET_INCOMPLETE for w in warnings)


def test_complete_electrical_coverage_no_warning():
    library = _FakeLibrary(
        classes={"resistor": _resistor_class()},
        parts={"lcsc:C1": _part(datasheet_ref="ds1")},
        datasheets={
            "ds1": _datasheet(
                electrical=[RatingItem(symbol="R", param="resistance_ohm", extraction_status="extracted")]
            )
        },
    )
    errors, warnings = check_datasheets({"R1": PartByCatalog(part="lcsc:C1")}, library)
    assert not any(w.code == ErrorCode.W_DATASHEET_INCOMPLETE for w in warnings)


def test_unreadable_version_is_warning():
    library = _FakeLibrary(
        classes={"resistor": _resistor_class()},
        parts={"lcsc:C1": _part(datasheet_ref="ds1")},
        datasheets={
            "ds1": _datasheet(
                electrical=[RatingItem(symbol="R", param="resistance_ohm")],
                version_status="unreadable",
            )
        },
    )
    errors, warnings = check_datasheets({"R1": PartByCatalog(part="lcsc:C1")}, library)
    assert any(w.code == ErrorCode.W_DATASHEET_VERSION_UNKNOWN for w in warnings)
