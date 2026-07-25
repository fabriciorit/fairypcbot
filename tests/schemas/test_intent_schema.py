from __future__ import annotations

import pytest
from pydantic import ValidationError

from fairypcbot.schemas.intent import Intent


def _base(**overrides):
    data = {
        "fairypcbot": "0.1",
        "kind": "board",
        "name": "test",
        "board": {"layers": 2, "outline": {"shape": "rect", "width_mm": 10, "height_mm": 10}},
        "parts": {"R1": {"part": "lcsc:C1"}},
        "nets": {},
        "intents": [],
    }
    data.update(overrides)
    return data


def test_minimal_valid_intent():
    intent = Intent.model_validate(_base())
    assert intent.name == "test"
    assert "R1" in intent.parts


def test_schematic_config_absent_by_default():
    """the documentation: `schematic:` is optional — without it, `intent.schematic` is `None` (it is
    `build_rules`, not the schema, that fills the neutral default in `RulesDoc.schematic`)."""
    intent = Intent.model_validate(_base())
    assert intent.schematic is None


def test_schematic_config_parses_declared_knobs():
    data = _base(schematic={"min_gap_mm": 20.0, "max_wire_bends": 1})
    intent = Intent.model_validate(data)
    assert intent.schematic is not None
    assert intent.schematic.min_gap_mm == 20.0
    assert intent.schematic.max_wire_bends == 1
    assert intent.schematic.grid_mm == 2.54  # undeclared -> default


def test_schematic_config_layout_defaults_to_progressive():
    """the documentation: progressive engine is the default; `clustered` remains as explicit
    fallback, chosen via `schematic.layout` when declared."""
    intent = Intent.model_validate(_base())
    assert intent.schematic is None  # absent by default — build_rules fills the neutral

    from fairypcbot.schemas.intent import SchematicConfig

    assert SchematicConfig().layout == "progressive"
    data = _base(schematic={"layout": "clustered"})
    intent = Intent.model_validate(data)
    assert intent.schematic.layout == "clustered"


def test_block_kind_does_not_require_board():
    data = _base(kind="block")
    del data["board"]
    intent = Intent.model_validate(data)
    assert intent.board is None


def test_board_kind_requires_board_section():
    data = _base()
    del data["board"]
    with pytest.raises(ValidationError):
        Intent.model_validate(data)


def test_missing_kind_field_rejected():
    data = _base()
    del data["kind"]
    with pytest.raises(ValidationError):
        Intent.model_validate(data)


def test_invalid_outline_shape_rejected():
    data = _base()
    data["board"]["outline"] = {"shape": "hexagon"}
    with pytest.raises(ValidationError):
        Intent.model_validate(data)


def test_rect_outline_without_dimensions_rejected():
    data = _base()
    data["board"]["outline"] = {"shape": "rect"}
    with pytest.raises(ValidationError):
        Intent.model_validate(data)


def test_part_with_both_part_and_class_rejected():
    data = _base(parts={"R1": {"part": "lcsc:C1", "class": "resistor"}})
    with pytest.raises(ValidationError):
        Intent.model_validate(data)


def test_part_with_neither_part_nor_class_rejected():
    data = _base(parts={"R1": {"params": {}}})
    with pytest.raises(ValidationError):
        Intent.model_validate(data)


def test_part_by_class_accepted():
    data = _base(parts={"R1": {"class": "resistor"}})
    intent = Intent.model_validate(data)
    assert intent.parts["R1"].class_ == "resistor"


def test_unknown_intent_type_rejected():
    data = _base(intents=[{"type": "made_up_type", "net": "X"}])
    with pytest.raises(ValidationError):
        Intent.model_validate(data)


def test_known_intent_types_accepted():
    data = _base(
        nets={"VDD": ["R1.p1"]},
        intents=[{"type": "power_rail", "net": "VDD", "voltage_v": 3.3}],
    )
    intent = Intent.model_validate(data)
    assert len(intent.intents) == 1


def test_extra_field_rejected():
    data = _base()
    data["not_a_real_field"] = 123
    with pytest.raises(ValidationError):
        Intent.model_validate(data)
