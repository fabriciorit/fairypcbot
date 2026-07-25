from __future__ import annotations

from pathlib import Path

from fairypcbot.validate.library import LibraryIndex, resolve_library_paths


def _write_external_class(lib_dir: Path) -> None:
    (lib_dir / "classes").mkdir(parents=True)
    (lib_dir / "classes" / "external_thing.yaml").write_text(
        """\
fairypcbot: "0.1"
kind: component_class
id: external.thing
pins: [{role: a}]
""",
        encoding="utf-8",
    )


def test_resolve_library_paths_includes_extra_relative_path(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    external = tmp_path / "external_lib"
    _write_external_class(external)

    paths = resolve_library_paths(project, extra_paths=[Path("../external_lib")])
    assert external in paths


def test_resolve_library_paths_includes_extra_absolute_path(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    external = tmp_path / "external_lib"
    _write_external_class(external)

    paths = resolve_library_paths(project, extra_paths=[external])
    assert external in paths


def test_libraryindex_loads_class_from_extra_path(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    external = tmp_path / "external_lib"
    _write_external_class(external)

    paths = resolve_library_paths(project, extra_paths=[external])
    library = LibraryIndex(paths)
    assert library.has_class("external.thing")


def test_project_library_takes_precedence_order(tmp_path: Path):
    project = tmp_path / "project"
    (project / "library").mkdir(parents=True)
    external = tmp_path / "external_lib"
    external.mkdir()

    paths = resolve_library_paths(project, extra_paths=[external])
    assert paths[0] == project / "library"


def test_intent_libraries_field_resolved_by_validate(tmp_path: Path):
    from fairypcbot.validate.runner import validate_project

    project = tmp_path / "project"
    project.mkdir()
    external = tmp_path / "external_lib"
    _write_external_class(external)

    (project / "intent.yaml").write_text(
        """\
fairypcbot: "0.1"
kind: block
name: t
libraries: ["../external_lib"]
parts:
  X1: {class: external.thing}
nets:
  N1: [X1.a]
intents: []
""",
        encoding="utf-8",
    )
    report = validate_project(project, no_audit=True)
    assert report.ok is True
    assert report.errors == []
