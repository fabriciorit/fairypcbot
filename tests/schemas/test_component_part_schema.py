from __future__ import annotations

import pytest
from pydantic import ValidationError

from fairypcbot.schemas.component_part import ComponentPart


def _base(**overrides):
    data = {
        "kind": "component_part",
        "id": "lcsc:C1",
        "class": "resistor",
        "mpn": "ABC123",
        "manufacturer": "Acme",
        "package": {"name": "R0402", "source": "easyeda"},
        "pinout": {"p1": 1, "p2": 2},
    }
    data.update(overrides)
    return data


def test_minimal_valid_part():
    part = ComponentPart.model_validate(_base())
    assert part.class_ == "resistor"


def test_invalid_id_format_rejected():
    with pytest.raises(ValidationError):
        ComponentPart.model_validate(_base(id="C1"))


def test_missing_pinout_defaults_empty():
    data = _base()
    del data["pinout"]
    part = ComponentPart.model_validate(data)
    assert part.pinout == {}


def test_pinout_accepts_list_of_pins():
    part = ComponentPart.model_validate(_base(pinout={"vdd": [1, 2, 3]}))
    assert part.pinout["vdd"] == [1, 2, 3]


def test_missing_required_field_rejected():
    data = _base()
    del data["mpn"]
    with pytest.raises(ValidationError):
        ComponentPart.model_validate(data)
