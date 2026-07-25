from __future__ import annotations

from typer.testing import CliRunner

from fairypcbot.cli import app

runner = CliRunner()


def test_llm_no_arg_prints_index():
    result = runner.invoke(app, ["llm"])
    assert result.exit_code == 0
    assert "fairypcbot" in result.stdout
    assert "Tópicos" in result.stdout or "workflow.md" in result.stdout


def test_llm_topic_prints_content():
    result = runner.invoke(app, ["llm", "errors"])
    assert result.exit_code == 0
    assert "code" in result.stdout


def test_llm_unknown_topic_fails():
    result = runner.invoke(app, ["llm", "not-a-real-topic"])
    assert result.exit_code == 1


def test_llm_all_topics_from_index_are_printable():
    from fairypcbot import llm_docs

    for topic in llm_docs.list_topics():
        result = runner.invoke(app, ["llm", topic])
        assert result.exit_code == 0, f"tópico '{topic}' falhou"
