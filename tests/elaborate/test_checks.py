from __future__ import annotations

from fairypcbot.elaborate.checks.current_budget import check_current_budget
from fairypcbot.elaborate.checks.decoupling import check_missing_decoupling
from fairypcbot.elaborate.checks.floating_pins import check_floating_required_pins
from fairypcbot.elaborate.checks.logic_levels import check_logic_levels
from fairypcbot.elaborate.checks.power_tree import check_power_tree
from fairypcbot.schemas.component_class import ComponentClass
from fairypcbot.schemas.error_codes import ErrorCode
from fairypcbot.schemas.ir import Net, Netlist, NetMember, ResolvedPart, RulesDoc
from fairypcbot.validate.library import LibraryIndex


class _FakeLibrary(LibraryIndex):
    def __init__(self, classes=None):
        self.classes = classes or {}
        self.parts = {}


def _mcu_generic_class():
    return ComponentClass(
        kind="component_class", id="mcu.generic", pins=[{"role": "vdd"}, {"role": "vss"}]
    )


def _buck_class():
    return ComponentClass(
        kind="component_class",
        id="buck_converter",
        pins=[{"role": "vin"}, {"role": "vout"}, {"role": "gnd"}, {"role": "en"}],
    )


# --- current_budget ---------------------------------------------------------------------------


def test_current_budget_flags_net_above_default_trace():
    rules = RulesDoc.model_validate(
        {"intents": [{"type": "high_current", "net": "HEAVY", "current_a": 3.0}]}
    )
    warnings = check_current_budget(rules)
    assert len(warnings) == 1
    assert warnings[0].code == ErrorCode.W_CURRENT_OVER_TRACE_CAPACITY


def test_current_budget_ok_for_small_current():
    rules = RulesDoc.model_validate(
        {"intents": [{"type": "high_current", "net": "LIGHT", "current_a": 0.1}]}
    )
    assert check_current_budget(rules) == []


# --- power_tree --------------------------------------------------------------------------------


def test_power_tree_floating_pin_detected():
    library = _FakeLibrary(classes={"mcu.generic": _mcu_generic_class()})
    netlist = Netlist(
        parts={"U1": ResolvedPart(designator="U1", class_id="mcu.generic")},
        nets={},
    )
    rules = RulesDoc.model_validate({"intents": []})
    errors = check_power_tree(netlist, rules, library)
    assert len(errors) == 1
    assert errors[0].code == ErrorCode.E_POWER_TREE_UNREACHABLE


def test_power_tree_connected_but_no_source_detected():
    library = _FakeLibrary(classes={"mcu.generic": _mcu_generic_class()})
    netlist = Netlist(
        parts={"U1": ResolvedPart(designator="U1", class_id="mcu.generic")},
        nets={"VDD_NET": Net(name="VDD_NET", members=[NetMember(designator="U1", pin="vdd")])},
    )
    rules = RulesDoc.model_validate({"intents": []})
    errors = check_power_tree(netlist, rules, library)
    assert len(errors) == 1


def test_power_tree_ok_when_net_has_power_rail():
    library = _FakeLibrary(classes={"mcu.generic": _mcu_generic_class()})
    netlist = Netlist(
        parts={"U1": ResolvedPart(designator="U1", class_id="mcu.generic")},
        nets={"VDD_NET": Net(name="VDD_NET", members=[NetMember(designator="U1", pin="vdd")])},
    )
    rules = RulesDoc.model_validate(
        {"intents": [{"type": "power_rail", "net": "VDD_NET", "voltage_v": 3.3}]}
    )
    assert check_power_tree(netlist, rules, library) == []


def test_power_tree_ok_through_buck_converter():
    library = _FakeLibrary(
        classes={"mcu.generic": _mcu_generic_class(), "buck_converter": _buck_class()}
    )
    netlist = Netlist(
        parts={
            "U1": ResolvedPart(designator="U1", class_id="mcu.generic"),
            "U3": ResolvedPart(designator="U3", class_id="buck_converter"),
        },
        nets={
            "VBUS": Net(
                name="VBUS",
                members=[NetMember(designator="U3", pin="vin")],
            ),
            "V3V3": Net(
                name="V3V3",
                members=[
                    NetMember(designator="U3", pin="vout"),
                    NetMember(designator="U1", pin="vdd"),
                ],
            ),
        },
    )
    rules = RulesDoc.model_validate(
        {"intents": [{"type": "power_rail", "net": "VBUS", "voltage_v": 5.0}]}
    )
    assert check_power_tree(netlist, rules, library) == []


# --- logic_levels ------------------------------------------------------------------------------


def test_logic_level_mismatch_detected():
    netlist = Netlist(
        parts={
            "A": ResolvedPart(designator="A", class_id=None, params={"vdd_range_v": [1.7, 1.9]}),
            "B": ResolvedPart(designator="B", class_id=None, params={"vdd_range_v": [4.5, 5.5]}),
        },
        nets={"N1": Net(name="N1", members=[NetMember(designator="A"), NetMember(designator="B")])},
    )
    warnings = check_logic_levels(netlist)
    assert len(warnings) == 1
    assert warnings[0].code == ErrorCode.W_LOGIC_LEVEL_MISMATCH


def test_logic_level_overlap_ok():
    netlist = Netlist(
        parts={
            "A": ResolvedPart(designator="A", class_id=None, params={"vdd_range_v": [2.7, 5.5]}),
            "B": ResolvedPart(designator="B", class_id=None, params={"vdd_range_v": [3.0, 3.6]}),
        },
        nets={"N1": Net(name="N1", members=[NetMember(designator="A"), NetMember(designator="B")])},
    )
    assert check_logic_levels(netlist) == []


# --- floating_pins -----------------------------------------------------------------------------


def test_floating_required_pin_detected():
    library = _FakeLibrary(classes={"buck_converter": _buck_class()})
    netlist = Netlist(
        parts={"U3": ResolvedPart(designator="U3", class_id="buck_converter")},
        nets={"VBUS": Net(name="VBUS", members=[NetMember(designator="U3", pin="vin")])},
    )
    warnings = check_floating_required_pins(netlist, library)
    assert len(warnings) == 1
    assert warnings[0].code == ErrorCode.W_FLOATING_REQUIRED_PIN


def test_floating_required_pin_ok_when_connected():
    library = _FakeLibrary(classes={"buck_converter": _buck_class()})
    netlist = Netlist(
        parts={"U3": ResolvedPart(designator="U3", class_id="buck_converter")},
        nets={"VBUS": Net(name="VBUS", members=[NetMember(designator="U3", pin="en")])},
    )
    assert check_floating_required_pins(netlist, library) == []


# --- decoupling --------------------------------------------------------------------------------


def test_missing_decoupling_detected():
    library = _FakeLibrary(classes={"mcu.generic": _mcu_generic_class()})
    netlist = Netlist(parts={"U1": ResolvedPart(designator="U1", class_id="mcu.generic")})
    rules = RulesDoc.model_validate({"intents": []})
    warnings = check_missing_decoupling(netlist, rules, library)
    assert len(warnings) == 1
    assert warnings[0].code == ErrorCode.W_MISSING_DECOUPLING


def test_decoupling_present_ok():
    library = _FakeLibrary(classes={"mcu.generic": _mcu_generic_class()})
    netlist = Netlist(parts={"U1": ResolvedPart(designator="U1", class_id="mcu.generic")})
    rules = RulesDoc.model_validate(
        {"intents": [{"type": "decouples", "part": "C1", "target": "U1.vdd"}]}
    )
    assert check_missing_decoupling(netlist, rules, library) == []
