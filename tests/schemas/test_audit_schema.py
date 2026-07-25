from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from fairypcbot.schemas.audit import AuditEvent


def _base(**overrides):
    data = {
        "ts": datetime.now(UTC),
        "run_id": "abc123",
        "phase": "validate",
        "actor": "framework",
        "event": "validation",
        "code": "VALIDATE_RUN",
        "summary": "ok",
    }
    data.update(overrides)
    return data


def test_valid_event():
    ev = AuditEvent.model_validate(_base())
    assert ev.actor == "framework"


def test_invalid_actor_rejected():
    with pytest.raises(ValidationError):
        AuditEvent.model_validate(_base(actor="robot"))


def test_invalid_event_type_rejected():
    with pytest.raises(ValidationError):
        AuditEvent.model_validate(_base(event="banana"))


def test_invalid_phase_rejected():
    with pytest.raises(ValidationError):
        AuditEvent.model_validate(_base(phase="lunch"))
