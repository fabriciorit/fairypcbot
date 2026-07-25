from __future__ import annotations

from fairypcbot.schemas.component_class import ComponentClass
from fairypcbot.schemas.component_part import ComponentPart
from fairypcbot.schemas.error_codes import ErrorCode
from fairypcbot.schemas.intent import Intent
from fairypcbot.validate.checks.pins import check_pins
from fairypcbot.validate.library import LibraryIndex


class _FakeLibrary(LibraryIndex):
    def __init__(self, classes=None, parts=None):
        self.classes = classes or {}
        self.parts = parts or {}


def _intent(nets, parts):
    return Intent.model_validate(
        {
            "fairypcbot": "0.1",
            "kind": "block",
            "name": "t",
            "parts": parts,
            "nets": nets,
            "intents": [],
        }
    )


def _resistor_class():
    return ComponentClass(
        kind="component_class", id="resistor", pins=[{"role": "p1"}, {"role": "p2"}]
    )


def _resistor_part():
    return ComponentPart(
        kind="component_part",
        id="lcsc:C1",
        **{"class": "resistor"},
        mpn="X",
        manufacturer="Y",
        package={"name": "R0402", "source": "easyeda"},
        pinout={"p1": 1, "p2": 2},
    )


def test_known_pin_accepted():
    intent = _intent(nets={"N1": ["R1.p1"]}, parts={"R1": {"part": "lcsc:C1"}})
    library = _FakeLibrary(
        classes={"resistor": _resistor_class()}, parts={"lcsc:C1": _resistor_part()}
    )
    errors, warnings = check_pins(intent, intent.parts, library)
    assert errors == []
    assert warnings == []


def test_unknown_pin_rejected():
    intent = _intent(nets={"N1": ["R1.p3"]}, parts={"R1": {"part": "lcsc:C1"}})
    library = _FakeLibrary(
        classes={"resistor": _resistor_class()}, parts={"lcsc:C1": _resistor_part()}
    )
    errors, warnings = check_pins(intent, intent.parts, library)
    assert len(errors) == 1
    assert errors[0].code == ErrorCode.E_UNKNOWN_PIN


def test_part_not_in_library_warns_not_errors():
    intent = _intent(nets={"N1": ["R1.p1"]}, parts={"R1": {"part": "lcsc:C999"}})
    library = _FakeLibrary()
    errors, warnings = check_pins(intent, intent.parts, library)
    assert errors == []
    assert len(warnings) == 1
    assert warnings[0].code == ErrorCode.W_PART_NOT_IN_LIBRARY


def test_class_reference_checked_against_library_class():
    intent = _intent(nets={"N1": ["R1.p1"]}, parts={"R1": {"class": "resistor"}})
    library = _FakeLibrary(classes={"resistor": _resistor_class()})
    errors, warnings = check_pins(intent, intent.parts, library)
    assert errors == []
    assert warnings == []
