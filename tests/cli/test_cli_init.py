from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from fairypcbot.cli import app

runner = CliRunner()


def test_init_creates_project_structure(tmp_path: Path):
    project = tmp_path / "myproj"
    result = runner.invoke(app, ["init", str(project)])
    assert result.exit_code == 0
    assert (project / "intent.yaml").exists()
    assert (project / "blocks").is_dir()
    assert (project / "build").is_dir()
    assert (project / "audit").is_dir()


def test_init_creates_llm_pointers(tmp_path: Path):
    project = tmp_path / "myproj"
    result = runner.invoke(app, ["init", str(project)])
    assert result.exit_code == 0
    for pointer in ("AGENTS.md",):
        content = (project / pointer).read_text(encoding="utf-8")
        assert "fae llm" in content
        # A skill portátil não vive na raiz do repo, então o ponteiro gerado é o que a torna
        # descobrível para uma LLM trabalhando num projeto de PCB.
        assert "fae skill" in content


def test_init_does_not_overwrite_existing(tmp_path: Path):
    project = tmp_path / "myproj"
    project.mkdir()
    (project / "intent.yaml").write_text("existing", encoding="utf-8")
    result = runner.invoke(app, ["init", str(project)])
    assert result.exit_code == 1
    assert (project / "intent.yaml").read_text() == "existing"
