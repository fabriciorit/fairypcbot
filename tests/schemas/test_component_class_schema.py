from __future__ import annotations

import pytest
from pydantic import ValidationError

from fairypcbot.schemas.component_class import ComponentClass


def test_minimal_valid_class():
    cc = ComponentClass.model_validate(
        {
            "kind": "component_class",
            "id": "resistor",
            "pins": [{"role": "p1"}, {"role": "p2"}],
        }
    )
    assert cc.id == "resistor"
    assert len(cc.pins) == 2


def test_pin_with_name_and_count_rejected():
    with pytest.raises(ValidationError):
        ComponentClass.model_validate(
            {
                "kind": "component_class",
                "id": "x",
                "pins": [{"name": "VDD", "role": "power", "count": 3}],
            }
        )


def test_pin_count_greater_than_one_requires_separable():
    with pytest.raises(ValidationError):
        ComponentClass.model_validate(
            {
                "kind": "component_class",
                "id": "x",
                "pins": [{"role": "terminal", "count": 2}],
            }
        )


def test_pin_count_with_separable_accepted():
    cc = ComponentClass.model_validate(
        {
            "kind": "component_class",
            "id": "x",
            "pins": [{"role": "terminal", "count": 2, "separable": False}],
        }
    )
    assert cc.pins[0].separable is False


def test_wrong_kind_rejected():
    with pytest.raises(ValidationError):
        ComponentClass.model_validate({"kind": "component_part", "id": "x", "pins": []})
