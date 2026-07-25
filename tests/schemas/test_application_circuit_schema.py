from __future__ import annotations

import pytest
from pydantic import ValidationError

from fairypcbot.schemas.component_class import ComponentClass


def test_application_circuit_parses_buck_template():
    cc = ComponentClass.model_validate(
        {
            "kind": "component_class",
            "id": "buck_converter",
            "pins": [{"role": "vin"}, {"role": "vout"}, {"role": "gnd"}],
            "application_circuit": {
                "parts": {
                    "L1": {"class": "inductor.power", "sizing": "buck.inductor_sizing"},
                    "COUT": {"class": "capacitor", "sizing": "buck.cout_sizing"},
                },
                "nets_internal": ["SW_NODE"],
                "intents": [
                    {
                        "type": "current_loop_minimize",
                        "parts": ["SELF", "L1", "COUT"],
                        "priority": "critical",
                    }
                ],
                "domain": {"atomic": False, "split_cost": "high"},
            },
        }
    )
    assert cc.application_circuit is not None
    assert cc.application_circuit.parts["L1"].class_ == "inductor.power"
    assert cc.application_circuit.domain.split_cost == "high"


def test_application_circuit_rejects_unknown_intent_type():
    with pytest.raises(ValidationError):
        ComponentClass.model_validate(
            {
                "kind": "component_class",
                "id": "x",
                "application_circuit": {
                    "parts": {},
                    "intents": [{"type": "not_a_real_intent"}],
                },
            }
        )


def test_application_circuit_none_by_default():
    cc = ComponentClass.model_validate({"kind": "component_class", "id": "resistor"})
    assert cc.application_circuit is None
