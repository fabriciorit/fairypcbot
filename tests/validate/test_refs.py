from __future__ import annotations

from fairypcbot.schemas.error_codes import ErrorCode
from fairypcbot.schemas.intent import Intent
from fairypcbot.validate.checks.refs import check_refs


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


def test_valid_ref_accepted():
    intent = _intent(nets={"N1": ["R1.p1"]}, parts={"R1": {"part": "lcsc:C1"}})
    errors = check_refs(intent, intent.parts)
    assert errors == []


def test_unknown_designator_rejected():
    intent = _intent(nets={"N1": ["R2.p1"]}, parts={"R1": {"part": "lcsc:C1"}})
    errors = check_refs(intent, intent.parts)
    assert len(errors) == 1
    assert errors[0].code == ErrorCode.E_UNKNOWN_PART_REF


def test_ref_without_pin_ok_if_designator_exists():
    intent = _intent(nets={"N1": ["R1"]}, parts={"R1": {"part": "lcsc:C1"}})
    errors = check_refs(intent, intent.parts)
    assert errors == []
