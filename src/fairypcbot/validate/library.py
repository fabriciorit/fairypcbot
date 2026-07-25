"""Index of the class/part/package/datasheet library (`library/*`).

Normative layout documented in `docs/library_repo.md`: `classes/`, `parts/`, `packages/`,
`datasheets/`, `blocks/`. Multiple libraries can be combined (`resolve_library_paths`),
with precedence: the project's own library > `libraries:` declared in the intent > the
fairypcbot repository's founding library (when the project is nested inside it, like the
`examples/`).
"""

from __future__ import annotations

from pathlib import Path

from ruamel.yaml import YAML

from fairypcbot.schemas.component_class import ComponentClass
from fairypcbot.schemas.component_package import ComponentPackage, PackageVariant, parse_package_ref
from fairypcbot.schemas.component_part import ComponentPart
from fairypcbot.schemas.datasheet import DatasheetExtract
from fairypcbot.schemas.intent import PartByCatalog, PartByClass, PartSpec

_yaml = YAML(typ="safe")


def resolve_library_paths(
    project_root: Path, extra_paths: list[Path] | None = None
) -> list[Path]:
    """Discovers relevant `library/` directories, in precedence order: the project's library,
    extra declared libraries (`intent.libraries`), the fairypcbot repository's founding library
    (when the project is nested inside it, like the `examples/`)."""
    project_root = Path(project_root).resolve()
    paths: list[Path] = []

    local = project_root / "library"
    if local.is_dir():
        paths.append(local)

    for extra in extra_paths or []:
        resolved = extra if extra.is_absolute() else (project_root / extra)
        resolved = resolved.resolve()
        if resolved.is_dir() and resolved not in paths:
            paths.append(resolved)

    current = project_root
    while current != current.parent:
        candidate = current / "library"
        if (current / "pyproject.toml").exists() and candidate.is_dir() and candidate not in paths:
            paths.append(candidate)
        current = current.parent

    return paths


class LibraryIndex:
    def __init__(self, library_paths: list[Path]) -> None:
        self.classes: dict[str, ComponentClass] = {}
        self.parts: dict[str, ComponentPart] = {}
        self.packages: dict[str, ComponentPackage] = {}
        self.datasheets: dict[str, DatasheetExtract] = {}
        self._package_aliases: dict[str, str] = {}
        for lib_path in library_paths:
            self._load_dir(lib_path / "classes", "component_class")
            self._load_dir(lib_path / "parts", "component_part")
            self._load_dir(lib_path / "packages", "component_package")
            self._load_dir(lib_path / "datasheets", "datasheet_extract")

    def _load_dir(self, dir_path: Path, expected_kind: str) -> None:
        if not dir_path.is_dir():
            return
        for yaml_path in sorted(dir_path.glob("*.yaml")):
            raw = _yaml.load(yaml_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict) or raw.get("kind") != expected_kind:
                continue
            if expected_kind == "component_class":
                obj = ComponentClass.model_validate(raw)
                self.classes[obj.id] = obj
            elif expected_kind == "component_part":
                part = ComponentPart.model_validate(raw)
                self.parts[part.id] = part
            elif expected_kind == "component_package":
                package = ComponentPackage.model_validate(raw)
                self.packages[package.id] = package
                for alias in package.aliases:
                    self._package_aliases[alias] = package.id
            elif expected_kind == "datasheet_extract":
                datasheet = DatasheetExtract.model_validate(raw)
                self.datasheets[datasheet.id] = datasheet

    def get_class(self, class_id: str) -> ComponentClass:
        return self.classes[class_id]

    def has_class(self, class_id: str) -> bool:
        return class_id in self.classes

    def has_part(self, part_id: str) -> bool:
        return part_id in self.parts

    def get_package(self, family_id: str) -> ComponentPackage | None:
        resolved_id = self._package_aliases.get(family_id, family_id)
        return self.packages.get(resolved_id)

    def resolve_package_ref(self, ref: str) -> tuple[ComponentPackage, str, PackageVariant] | None:
        """Resolves a `family` or `family:variant` reference to
        (package, variant_name, variant). None if the family or the variant does not exist."""
        family_id, variant_name = parse_package_ref(ref)
        package = self.get_package(family_id)
        if package is None:
            return None
        resolved = package.resolve_variant(variant_name)
        if resolved is None:
            return None
        name, variant = resolved
        return package, name, variant


def class_id_for(designator: str, spec: PartSpec, library: LibraryIndex) -> str | None:
    """Class id resolved for the designator, or None if it cannot be resolved (a catalog
    part with no descriptor in the library, or a stub descriptor with 'class' not yet filled in)."""
    if isinstance(spec, PartByClass):
        return spec.class_
    if isinstance(spec, PartByCatalog):
        part = library.parts.get(spec.part)
        return part.class_ if part else None
    return None
