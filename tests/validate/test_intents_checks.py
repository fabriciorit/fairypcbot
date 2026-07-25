from __future__ import annotations

import pytest
from pydantic import ValidationError

from fairypcbot.schemas.error_codes import ErrorCode
from fairypcbot.schemas.intent import Intent
from fairypcbot.validate.checks.intents import check_intents


def _intent(nets, parts, intents):
    return Intent.model_validate(
        {
            "fairypcbot": "0.1",
            "kind": "block",
            "name": "t",
            "parts": parts,
            "nets": nets,
            "intents": intents,
        }
    )


def test_power_rail_valid_net_accepted():
    intent = _intent(
        nets={"VDD": ["R1.p1"]},
        parts={"R1": {"part": "lcsc:C1"}},
        intents=[{"type": "power_rail", "net": "VDD", "voltage_v": 3.3}],
    )
    errors = check_intents(intent, intent.parts)
    assert errors == []


def test_power_rail_unknown_net_rejected():
    intent = _intent(
        nets={"VDD": ["R1.p1"]},
        parts={"R1": {"part": "lcsc:C1"}},
        intents=[{"type": "power_rail", "net": "GHOST", "voltage_v": 3.3}],
    )
    errors = check_intents(intent, intent.parts)
    assert len(errors) == 1
    assert errors[0].code == ErrorCode.E_INTENT_BAD_PARAMS


def test_decouples_unknown_part_rejected():
    intent = _intent(
        nets={},
        parts={"R1": {"part": "lcsc:C1"}},
        intents=[{"type": "decouples", "part": "C99", "target": "R1.p1"}],
    )
    errors = check_intents(intent, intent.parts)
    assert len(errors) == 1


def test_power_rail_with_wrong_type_voltage_rejected():
    with pytest.raises(ValidationError):
        _intent(
            nets={"VDD": ["R1.p1"]},
            parts={"R1": {"part": "lcsc:C1"}},
            intents=[{"type": "power_rail", "net": "VDD", "voltage_v": "cinco"}],
        )
