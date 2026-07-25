"""Schema for package descriptors (`library/packages/*.yaml`) — families with variants.

Design decision (see the documentation): a package is a FAMILY (e.g. `soic-8`) containing geometric VARIANTS
(e.g. `3.9x4.9`), because generic names like "SOIC-8" don't identify a unique geometry (3.9mm
and 5.3mm bodies coexist under the same JEDEC name). Parts reference `family` (default/only
variant) or `family:variant` via `PackageSpec.ref`.

The datasheet is the canonical source of geometry (a normative project principle); API data is
a convenience and never overrides variants with `datasheet` or `user` provenance.
"""

from __future__ import annotations

from typing import Literal

from pydantic import model_validator

from fairypcbot.schemas.base import FairyBaseModel
from fairypcbot.schemas.footprint import Footprint
from fairypcbot.schemas.provenance import Provenance


class BodySize(FairyBaseModel):
    width_mm: float
    height_mm: float
    height_z_mm: float | None = None


class PackageVariant(FairyBaseModel):
    footprint: Footprint | None = None
    body: BodySize | None = None
    default: bool = False
    provenance: dict[str, Provenance] = {}


class ComponentPackage(FairyBaseModel):
    fairypcbot: str = "0.1"
    kind: Literal["component_package"]
    id: str
    aliases: list[str] = []
    description: str = ""
    variants: dict[str, PackageVariant] = {}

    @model_validator(mode="after")
    def check_single_default(self) -> ComponentPackage:
        defaults = [name for name, v in self.variants.items() if v.default]
        if len(defaults) > 1:
            raise ValueError(
                f"Package '{self.id}': only one variant may be 'default' "
                f"(found: {defaults})"
            )
        return self

    def resolve_variant(self, variant_name: str | None) -> tuple[str, PackageVariant] | None:
        """Resolve the requested variant (or the default/only one when None). None if not resolvable."""
        if variant_name is not None:
            variant = self.variants.get(variant_name)
            return (variant_name, variant) if variant is not None else None
        for name, variant in self.variants.items():
            if variant.default:
                return name, variant
        if len(self.variants) == 1:
            name = next(iter(self.variants))
            return name, self.variants[name]
        return None


def parse_package_ref(ref: str) -> tuple[str, str | None]:
    """`soic-8` -> ("soic-8", None); `soic-8:3.9x4.9` -> ("soic-8", "3.9x4.9")."""
    if ":" in ref:
        family, variant = ref.split(":", 1)
        return family, variant
    return ref, None


def variant_name_from_body(body: BodySize) -> str:
    """Deterministic variant name derived from body dimensions (e.g. '3.9x4.9')."""
    def fmt(v: float) -> str:
        return f"{v:.4g}"

    return f"{fmt(body.width_mm)}x{fmt(body.height_mm)}"
