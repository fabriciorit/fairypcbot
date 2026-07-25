"""Persistence of `component_package` from geometry obtained via a catalog.

Normative rule (see the documentation): **`catalog fetch` never overwrites a variant whose provenance is
`datasheet` or `user`** — the datasheet is the project's canonical reference; API data is a
convenience. Even between two API sources, an existing variant is never silently overwritten: if
the new geometry diverges from the stored one, a sibling variant is written with a source suffix
and a warning is raised. Refetching exactly the same geometry is idempotent (no-op).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ruamel.yaml import YAML

from fairypcbot.catalog.yaml_io import dump_component_package
from fairypcbot.place.package_size import bbox_from_footprint
from fairypcbot.schemas.component_package import ComponentPackage, PackageVariant
from fairypcbot.schemas.footprint import Footprint
from fairypcbot.schemas.provenance import Provenance

_yaml = YAML(typ="safe")

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def family_id_from_package_name(package_name: str) -> str:
    """'SOIC-8' -> 'soic-8'; normalizes any package name into a stable family id."""
    slug = _NON_ALNUM_RE.sub("-", package_name.strip().lower()).strip("-")
    return slug or "unknown"


def variant_name_from_footprint(footprint: Footprint) -> str:
    """Deterministic name derived from the pad bounding box (we do not have a parsed
    body/courtyard from the API — see docs/easyeda_format.md). E.g. '4.9x3.9'."""
    bbox = bbox_from_footprint(footprint)
    if bbox is None:
        return "unknown"
    w, h = bbox
    return f"{w:.4g}x{h:.4g}"


def _footprints_equal(a: Footprint, b: Footprint) -> bool:
    def normalize(fp: Footprint) -> list[tuple[str, str, float, float, float, float]]:
        return sorted(
            (p.number, p.shape, round(p.x_mm, 4), round(p.y_mm, 4), round(p.width_mm, 4), round(p.height_mm, 4))
            for p in fp.pads
        )

    return normalize(a) == normalize(b)


@dataclass
class PackageWriteResult:
    family_id: str
    variant_name: str
    action: str  # "created" | "updated_empty" | "unchanged" | "skipped_conflict" | "sibling_created"
    path: Path
    warning: str | None = None


def _load_family(path: Path, family_id: str) -> ComponentPackage:
    if path.exists():
        raw = _yaml.load(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict) and raw.get("kind") == "component_package":
            return ComponentPackage.model_validate(raw)
    return ComponentPackage(kind="component_package", id=family_id, variants={})


def write_package_variant(
    packages_dir: Path,
    *,
    package_name: str,
    footprint: Footprint,
    source_ref: str,
    sha256: str | None,
) -> PackageWriteResult:
    family_id = family_id_from_package_name(package_name)
    family_path = packages_dir / f"{family_id}.yaml"
    family = _load_family(family_path, family_id)

    variant_name = variant_name_from_footprint(footprint)
    now = datetime.now(UTC)
    new_provenance = Provenance(source="easyeda_api", ref=source_ref, timestamp=now, sha256=sha256)

    existing = family.variants.get(variant_name)

    if existing is None:
        family.variants[variant_name] = PackageVariant(
            footprint=footprint,
            default=not family.variants,  # first variant of the family becomes the default
            provenance={"footprint": new_provenance},
        )
        action = "created"
        warning = None
    elif existing.footprint is not None and _footprints_equal(existing.footprint, footprint):
        action = "unchanged"
        warning = None
    else:
        existing_source = existing.provenance.get("footprint")
        if existing_source is not None and existing_source.source in ("datasheet", "user"):
            action = "skipped_conflict"
            warning = (
                f"Variant '{family_id}:{variant_name}' already exists with provenance "
                f"'{existing_source.source}' (protected) — API geometry was NOT written. "
                f"Divergence detected; review manually if needed."
            )
        elif existing.footprint is None:
            family.variants[variant_name] = PackageVariant(
                footprint=footprint,
                default=existing.default,
                provenance={"footprint": new_provenance},
            )
            action = "updated_empty"
            warning = None
        else:
            sibling_name = f"{variant_name}-easyeda2"
            suffix = 2
            while sibling_name in family.variants:
                suffix += 1
                sibling_name = f"{variant_name}-easyeda{suffix}"
            family.variants[sibling_name] = PackageVariant(
                footprint=footprint, default=False, provenance={"footprint": new_provenance}
            )
            action = "sibling_created"
            variant_name = sibling_name
            warning = (
                f"Geometry diverges from the one already registered for "
                f"'{family_id}:{variant_name.rsplit('-', 1)[0]}' — written as sibling variant "
                f"'{family_id}:{variant_name}'. Review and merge manually."
            )

    packages_dir.mkdir(parents=True, exist_ok=True)
    family_path.write_text(dump_component_package(family), encoding="utf-8")

    return PackageWriteResult(
        family_id=family_id, variant_name=variant_name, action=action, path=family_path, warning=warning
    )
