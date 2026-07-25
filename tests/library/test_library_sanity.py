"""Sanity of the founding library (`library/classes`, `library/parts`, `library/packages`): every
YAML parses, every `extends` chain resolves without cycle, application circuits reference only
registered models (or emit warning, not error — see the documentation), and every part `package.ref`
resolves to an existing variant (see the documentation)."""

from __future__ import annotations

from pathlib import Path

from fairypcbot.registry.class_resolver import resolve_class
from fairypcbot.validate.library import LibraryIndex

REPO_ROOT = Path(__file__).resolve().parents[2]


def _library() -> LibraryIndex:
    return LibraryIndex([REPO_ROOT / "library"])


def test_at_least_twenty_classes_loaded():
    library = _library()
    assert len(library.classes) >= 20


def test_every_class_extends_chain_resolves():
    library = _library()
    for class_id in library.classes:
        resolved = resolve_class(class_id, loader=library.get_class)
        assert resolved.id == class_id


def test_mcu_ch32v203_inherits_decoupling_from_generic():
    library = _library()
    resolved = resolve_class("mcu.riscv.ch32v203", loader=library.get_class)
    assert resolved.application_circuit is not None
    assert "C_VDD" in resolved.application_circuit.parts  # inherited from mcu.generic
    assert "Y1" in resolved.application_circuit.parts  # specific to ch32v203


def test_every_part_class_reference_exists_in_library():
    library = _library()
    for part in library.parts.values():
        if part.class_ is not None:
            assert library.has_class(part.class_), f"{part.id} references non-existent class"


def test_at_least_three_packages_loaded():
    library = _library()
    assert len(library.packages) >= 3


def test_every_package_has_a_resolvable_default_or_single_variant():
    library = _library()
    for package in library.packages.values():
        assert package.resolve_variant(None) is not None, f"{package.id} without default/single variant"


def test_every_part_package_ref_resolves():
    library = _library()
    for part in library.parts.values():
        if part.package.ref:
            resolved = library.resolve_package_ref(part.package.ref)
            assert resolved is not None, f"{part.id} references non-existent package '{part.package.ref}'"
