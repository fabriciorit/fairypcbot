from __future__ import annotations

import pytest

from fairypcbot.registry.models import call_model, is_model_implemented, known_models


def test_known_sizing_models_registered():
    for name in (
        "buck.inductor_sizing",
        "buck.cin_sizing",
        "buck.cout_sizing",
        "ldo.cin_cout_sizing",
        "mcu.decoupling_sizing",
        "crystal.load_cap_sizing",
    ):
        assert is_model_implemented(name)
    assert not is_model_implemented("made_up_model")
    assert "buck.inductor_sizing" in known_models()


def test_buck_inductor_sizing_returns_positive_value_and_justification():
    value, justification = call_model(
        "buck.inductor_sizing", vin_v=5.0, vout_v=3.3, iout_max_a=0.5
    )
    assert value > 0
    assert "L =" in justification


def test_buck_cin_cout_sizing_positive():
    cin, _ = call_model("buck.cin_sizing", iout_max_a=0.5)
    cout, _ = call_model("buck.cout_sizing", ripple_current_a=0.15)
    assert cin > 0
    assert cout > 0


def test_ldo_sizing_returns_typical_value():
    value, justification = call_model("ldo.cin_cout_sizing")
    assert value == pytest.approx(1e-6)
    assert "µF" in justification


def test_mcu_decoupling_sizing_default_100nf():
    value, justification = call_model("mcu.decoupling_sizing")
    assert value == pytest.approx(100e-9)
    assert "100nF" in justification.replace(" ", "")


def test_crystal_load_cap_sizing_formula():
    value, justification = call_model(
        "crystal.load_cap_sizing", load_capacitance_f=18e-12, stray_capacitance_f=3e-12
    )
    assert value == pytest.approx(2 * (18e-12 - 3e-12))
    assert "CL" in justification
