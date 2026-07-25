from __future__ import annotations

from pathlib import Path

from fairypcbot.schemas.error_codes import ErrorCode
from fairypcbot.validate.runner import validate_project


def _write_intent(path: Path, imports: list[str] = ()) -> None:
    path.mkdir(parents=True, exist_ok=True)
    imports_yaml = "\n".join(f"  - path: {p}" for p in imports) or "[]"
    (path / "intent.yaml").write_text(
        f"""\
fairypcbot: "0.1"
kind: block
name: {path.name}
imports:
{imports_yaml if imports else "  []"}
parts: {{}}
nets: {{}}
intents: []
""",
        encoding="utf-8",
    )


def test_import_cycle_detected(tmp_path: Path):
    a_dir = tmp_path / "a"
    b_dir = tmp_path / "b"
    _write_intent(a_dir, imports=["../b"])
    _write_intent(b_dir, imports=["../a"])

    report = validate_project(a_dir, no_audit=True)
    assert not report.ok
    assert any(e.code == ErrorCode.E_IMPORT_CYCLE for e in report.errors)


def test_import_not_found(tmp_path: Path):
    a_dir = tmp_path / "a"
    _write_intent(a_dir, imports=["../does_not_exist"])

    report = validate_project(a_dir, no_audit=True)
    assert not report.ok
    assert any(e.code == ErrorCode.E_IMPORT_NOT_FOUND for e in report.errors)
