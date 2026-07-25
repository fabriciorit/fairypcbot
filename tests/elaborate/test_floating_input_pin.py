"""Finding from the BFO metal detector test: a floating amplifier -INPUT was not caught
because the check only recognized hardcoded roles (EN/VREF/EP) — see the documentation."""

from __future__ import annotations

from fairypcbot.elaborate.checks.floating_pins import check_floating_required_pins
from fairypcbot.schemas.component_class import ComponentClass
from fairypcbot.schemas.error_codes import ErrorCode
from fairypcbot.schemas.ir import Net, Netlist, NetMember, ResolvedPart
from fairypcbot.validate.library import LibraryIndex


class _FakeLibrary(LibraryIndex):
    def __init__(self, classes=None):
        self.classes = classes or {}
        self.parts = {}
        self.packages = {}
        self.datasheets = {}
        self._package_aliases = {}


def _amp_class():
    return ComponentClass(
        kind="component_class",
        id="amp",
        pins=[
            {"role": "in_minus", "type": "input"},
            {"role": "in_plus", "type": "input"},
            {"role": "gain1", "type": "other"},  # intentionally can be left open
        ],
    )


def test_floating_input_pin_detected():
    library = _FakeLibrary(classes={"amp": _amp_class()})
    netlist = Netlist(
        parts={"U1": ResolvedPart(designator="U1", class_id="amp")},
        nets={"IN": Net(name="IN", members=[NetMember(designator="U1", pin="in_plus")])},
    )
    warnings = check_floating_required_pins(netlist, library)
    codes = {w.code for w in warnings}
    paths = {w.path for w in warnings}
    assert ErrorCode.W_FLOATING_INPUT_PIN in codes
    assert "parts.U1" in paths
    # floating in_minus generates the warning; in_plus (connected) and gain1 (type=other) do not
    assert sum(1 for w in warnings if w.code == ErrorCode.W_FLOATING_INPUT_PIN) == 1


def test_other_type_pin_not_flagged_when_floating():
    library = _FakeLibrary(classes={"amp": _amp_class()})
    netlist = Netlist(
        parts={"U1": ResolvedPart(designator="U1", class_id="amp")},
        nets={
            "IN": Net(name="IN", members=[NetMember(designator="U1", pin="in_plus")]),
            "INM": Net(name="INM", members=[NetMember(designator="U1", pin="in_minus")]),
        },
    )
    warnings = check_floating_required_pins(netlist, library)
    assert warnings == []  # gain1 (type=other) is left open without generating warning
