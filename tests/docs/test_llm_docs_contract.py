"""Size/coverage contract for docs/llm/ (see the documentation and docs/llm/INDEX.md).

The budgets below (150/400 lines) are the same declared in prose in INDEX.md itself —
if one of the two sides changes, change the other as well, intentionally (the text explains the number to
the human reader; the test enforces it)."""

from __future__ import annotations

from pathlib import Path

from fairypcbot import llm_docs, version_info

INDEX_MAX_LINES = 150
TOPIC_MAX_LINES = 400


def _line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def test_index_within_size_budget():
    index_path = llm_docs.llm_docs_dir() / "INDEX.md"
    assert _line_count(index_path) <= INDEX_MAX_LINES


def test_every_topic_within_size_budget():
    docs_dir = llm_docs.llm_docs_dir()
    for topic in llm_docs.list_topics():
        path = docs_dir / f"{topic}.md"
        assert _line_count(path) <= TOPIC_MAX_LINES, f"'{topic}.md' excede o orçamento de {TOPIC_MAX_LINES} linhas"


def test_index_mentions_every_topic():
    index_text = llm_docs.read_index()
    for topic in llm_docs.list_topics():
        assert topic in index_text, f"'{topic}' não é mencionado em INDEX.md"


def test_index_declares_version_matching_package():
    # A versão é derivada do git (hatch-vcs), então entre tags ela carrega sufixos de dev/commit
    # (`0.1.1.dev8+gf42f7062`). O INDEX.md documenta a linha de release, não o build exato — para
    # o build exato existe `fae version`.
    index_text = llm_docs.read_index()
    declared = version_info.base_version()
    assert declared in index_text, (
        f"INDEX.md não declara a versão atual ({declared}) — atualize junto de "
        f"qualquer bump em fairypcbot.__version__"
    )


def test_all_topics_are_readable_via_helper():
    for topic in llm_docs.list_topics():
        content = llm_docs.read_topic(topic)
        assert content is not None
        assert len(content) > 0
