from __future__ import annotations

import pytest
from pydantic import ValidationError

from fairypcbot.schemas.component_package import (
    BodySize,
    ComponentPackage,
    parse_package_ref,
    variant_name_from_body,
)


def _package(**overrides):
    data = {
        "kind": "component_package",
        "id": "soic-8",
        "variants": {
            "4.9x3.9": {"default": True, "body": {"width_mm": 4.9, "height_mm": 3.9}},
            "5.3x5.3": {"default": False},
        },
    }
    data.update(overrides)
    return ComponentPackage.model_validate(data)


def test_minimal_valid_package():
    pkg = _package()
    assert pkg.id == "soic-8"
    assert len(pkg.variants) == 2


def test_multiple_defaults_rejected():
    with pytest.raises(ValidationError):
        _package(
            variants={
                "a": {"default": True},
                "b": {"default": True},
            }
        )


def test_resolve_variant_by_name():
    pkg = _package()
    resolved = pkg.resolve_variant("5.3x5.3")
    assert resolved is not None
    name, variant = resolved
    assert name == "5.3x5.3"


def test_resolve_variant_default_when_none_requested():
    pkg = _package()
    resolved = pkg.resolve_variant(None)
    assert resolved is not None
    name, _ = resolved
    assert name == "4.9x3.9"


def test_resolve_variant_single_variant_no_default():
    pkg = ComponentPackage.model_validate(
        {"kind": "component_package", "id": "x", "variants": {"only": {}}}
    )
    resolved = pkg.resolve_variant(None)
    assert resolved is not None
    assert resolved[0] == "only"


def test_resolve_variant_unknown_returns_none():
    pkg = _package()
    assert pkg.resolve_variant("does-not-exist") is None


def test_parse_package_ref_family_only():
    assert parse_package_ref("soic-8") == ("soic-8", None)


def test_parse_package_ref_family_and_variant():
    assert parse_package_ref("soic-8:4.9x3.9") == ("soic-8", "4.9x3.9")


def test_variant_name_from_body():
    body = BodySize(width_mm=4.9, height_mm=3.9)
    assert variant_name_from_body(body) == "4.9x3.9"
