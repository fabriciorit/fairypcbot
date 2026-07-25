from __future__ import annotations

import pytest

from fairypcbot.registry.class_resolver import (
    ClassExtendsCycleError,
    ClassNotFoundError,
    resolve_class,
)
from fairypcbot.schemas.component_class import ComponentClass


def _class(id_, extends=None, pins=None, params=None):
    return ComponentClass(
        kind="component_class",
        id=id_,
        extends=extends,
        pins=pins or [],
        params=params or {},
    )


def test_merge_extends_simple():
    registry = {
        "base": _class("base", pins=[{"role": "p1"}], params={"required": ["a"]}),
        "child": _class(
            "child", extends="base", pins=[{"role": "p2"}], params={"required": ["b"]}
        ),
    }
    resolved = resolve_class("child", loader=lambda cid: registry[cid])
    roles = {p.role for p in resolved.pins}
    assert roles == {"p1", "p2"}
    assert set(resolved.params["required"]) == {"a", "b"}


def test_child_overrides_pin_with_same_key():
    registry = {
        "base": _class("base", pins=[{"role": "vdd"}]),
        "child": _class("child", extends="base", pins=[{"role": "vdd", "count": 2, "separable": True}]),
    }
    resolved = resolve_class("child", loader=lambda cid: registry[cid])
    assert len(resolved.pins) == 1
    assert resolved.pins[0].count == 2


def test_cycle_detected():
    registry = {
        "a": _class("a", extends="b"),
        "b": _class("b", extends="a"),
    }
    with pytest.raises(ClassExtendsCycleError):
        resolve_class("a", loader=lambda cid: registry[cid])


def test_missing_class_raises():
    with pytest.raises(ClassNotFoundError):
        resolve_class("nonexistent", loader=lambda cid: (_ for _ in ()).throw(KeyError(cid)))
