"""power_tree/decoupling reconhecem PinSpec.type == "power" além dos papéis vdd/vcc hardcoded
(achado do teste BFO: o LM386 usa o papel 'vs', não 'vdd'/'vcc' — ver the documentation)."""

from __future__ import annotations

from fairypcbot.elaborate.checks.decoupling import check_missing_decoupling
from fairypcbot.elaborate.checks.power_tree import check_power_tree
from fairypcbot.schemas.component_class import ComponentClass
from fairypcbot.schemas.error_codes import ErrorCode
from fairypcbot.schemas.ir import Net, Netlist, NetMember, ResolvedPart, RulesDoc
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
        pins=[{"role": "vs", "type": "power"}, {"role": "gnd", "type": "gnd"}],
    )


def test_power_tree_recognizes_type_power_role():
    library = _FakeLibrary(classes={"amp": _amp_class()})
    netlist = Netlist(parts={"U1": ResolvedPart(designator="U1", class_id="amp")})
    rules = RulesDoc(intents=[])
    errors = check_power_tree(netlist, rules, library)
    assert len(errors) == 1
    assert errors[0].code == ErrorCode.E_POWER_TREE_UNREACHABLE
    assert "vs" in errors[0].message


def test_power_tree_type_power_reaches_rail():
    library = _FakeLibrary(classes={"amp": _amp_class()})
    netlist = Netlist(
        parts={"U1": ResolvedPart(designator="U1", class_id="amp")},
        nets={"V9V": Net(name="V9V", members=[NetMember(designator="U1", pin="vs")])},
    )
    rules = RulesDoc.model_validate({"intents": [{"type": "power_rail", "net": "V9V", "voltage_v": 9}]})
    assert check_power_tree(netlist, rules, library) == []


def test_missing_decoupling_recognizes_type_power_role():
    library = _FakeLibrary(classes={"amp": _amp_class()})
    netlist = Netlist(parts={"U1": ResolvedPart(designator="U1", class_id="amp")})
    rules = RulesDoc(intents=[])
    warnings = check_missing_decoupling(netlist, rules, library)
    assert len(warnings) == 1
    assert warnings[0].code == ErrorCode.W_MISSING_DECOUPLING
    assert "vs" in warnings[0].message
