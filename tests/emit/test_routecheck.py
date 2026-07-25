from __future__ import annotations

from pathlib import Path

import pytest

from fairypcbot.emit import routecheck as routecheck_module
from fairypcbot.emit.routecheck import find_freerouting_jar, run_routecheck


def test_find_freerouting_jar_none_when_not_configured(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("FAIRYPCBOT_FREEROUTING_JAR", raising=False)
    assert find_freerouting_jar() is None


def test_find_freerouting_jar_explicit_path_must_exist(tmp_path: Path):
    missing = tmp_path / "does_not_exist.jar"
    assert find_freerouting_jar(missing) is None

    existing = tmp_path / "freerouting.jar"
    existing.write_text("fake jar", encoding="utf-8")
    assert find_freerouting_jar(existing) == existing


def test_run_routecheck_graceful_when_not_found(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(routecheck_module, "find_java", lambda: None)
    dsn = tmp_path / "board.dsn"
    dsn.write_text("(pcb)", encoding="utf-8")
    result = run_routecheck(dsn, tmp_path)
    assert result.ran is False
    assert result.success is False
    assert "not detected" in result.message.lower()


def test_run_routecheck_invokes_java_when_available(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    jar = tmp_path / "freerouting.jar"
    jar.write_text("fake", encoding="utf-8")
    monkeypatch.setattr(routecheck_module, "find_java", lambda: "/usr/bin/java")

    dsn = tmp_path / "board.dsn"
    dsn.write_text("(pcb)", encoding="utf-8")

    class _FakeCompleted:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def fake_runner(cmd, **kwargs):
        # simula o Freerouting gerando o .ses
        (tmp_path / "board.ses").write_text("session", encoding="utf-8")
        return _FakeCompleted()

    result = run_routecheck(dsn, tmp_path, jar_path=jar, runner=fake_runner)
    assert result.ran is True
    assert result.success is True
    assert result.output_path == tmp_path / "board.ses"


def test_run_routecheck_reports_subprocess_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    jar = tmp_path / "freerouting.jar"
    jar.write_text("fake", encoding="utf-8")
    monkeypatch.setattr(routecheck_module, "find_java", lambda: "/usr/bin/java")

    dsn = tmp_path / "board.dsn"
    dsn.write_text("(pcb)", encoding="utf-8")

    def failing_runner(cmd, **kwargs):
        raise OSError("boom")

    result = run_routecheck(dsn, tmp_path, jar_path=jar, runner=failing_runner)
    assert result.ran is False
    assert "Failed to run" in result.message
