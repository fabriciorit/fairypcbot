from __future__ import annotations

from fairypcbot.registry.class_resolver import resolve_class
from fairypcbot.schemas.component_class import ComponentClass, PinSpec


def test_pin_spec_type_optional_defaults_none():
    pin = PinSpec(role="vdd")
    assert pin.type is None


def test_pin_spec_accepts_valid_type():
    pin = PinSpec(role="vs", type="power")
    assert pin.type == "power"


def test_pin_spec_rejects_invalid_type():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        PinSpec(role="x", type="not_a_real_type")


def test_component_class_description_defaults_empty():
    cc = ComponentClass(kind="component_class", id="x")
    assert cc.description == ""


def test_component_class_description_roundtrip():
    cc = ComponentClass(kind="component_class", id="x", description="Amplificador de áudio")
    assert cc.description == "Amplificador de áudio"


def test_description_propagates_through_extends_merge():
    registry = {
        "base": ComponentClass(kind="component_class", id="base", description="base desc"),
        "child": ComponentClass(kind="component_class", id="child", extends="base", description="child desc"),
        "child_no_desc": ComponentClass(kind="component_class", id="child_no_desc", extends="base"),
    }
    resolved_child = resolve_class("child", loader=lambda cid: registry[cid])
    assert resolved_child.description == "child desc"

    resolved_no_desc = resolve_class("child_no_desc", loader=lambda cid: registry[cid])
    assert resolved_no_desc.description == "base desc"  # cai para a descrição herdada
