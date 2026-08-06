"""Contract for docs/skill/SKILL.md and its runtime identity (`fae skill`, `fae version`).

The skill is served by the CLI rather than read from the repository root precisely so that it
always describes the installation that emitted it. These tests protect that property: the identity
must be resolved (never left as a marker), and it must never be invented when unknowable.
"""

from __future__ import annotations

import json

from ruamel.yaml import YAML
from typer.testing import CliRunner

import fairypcbot
from fairypcbot import skill, version_info
from fairypcbot.cli import app

runner = CliRunner()


def test_skill_file_is_packaged_and_non_empty():
    assert skill.skill_path().is_file()
    assert len(skill.read_raw()) > 0


def test_raw_skill_carries_the_identity_marker():
    assert skill.IDENTITY_MARKER in skill.read_raw()


def test_rendered_skill_resolves_the_marker():
    rendered = skill.render()
    assert skill.IDENTITY_MARKER not in rendered
    assert fairypcbot.__version__ in rendered


def test_identity_block_is_valid_yaml():
    block = skill.render_identity_block()
    body = block.split("```yaml", 1)[1].split("```", 1)[0]
    data = YAML(typ="safe").load(body)
    assert data["version"] == fairypcbot.__version__
    assert data["commit_source"] in {"git", "build_stamp", "unknown"}
    # `None` must never leak as a Python repr into a block that claims to be YAML.
    assert "None" not in body


def test_commit_is_never_invented():
    info = version_info.resolve()
    if info.commit_source == "unknown":
        assert info.commit is None
        assert info.commit_short is None
    elif info.commit_source == "git":
        assert info.commit
        assert info.commit_short == info.commit[:7]
    else:  # build_stamp — só o hash abreviado existe; preencher `commit` seria inventá-lo
        assert info.commit is None
        assert info.commit_short


def test_base_version_strips_dev_and_local_suffixes():
    assert version_info.base_version("0.1.1.dev8+gf42f7062.d20260806") == "0.1.1"
    assert version_info.base_version("0.1.0") == "0.1.0"
    assert version_info.base_version("garbage") == "garbage"


def test_local_segment_parsing_detects_commit_and_dirtiness():
    assert version_info._commit_from_local_segment("0.1.1.dev8+gf42f7062") == ("f42f7062", False)
    assert version_info._commit_from_local_segment("0.1.1.dev8+gf42f7062.d20260806") == (
        "f42f7062",
        True,
    )
    assert version_info._commit_from_local_segment("0.1.0") is None


def test_version_command_json_is_parseable():
    result = runner.invoke(app, ["version", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["version"] == fairypcbot.__version__
    assert set(data) >= {"commit", "branch", "dirty", "tag", "commit_source", "python"}


def test_version_command_plain_is_one_line():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert len(result.stdout.strip().splitlines()) == 1
    assert fairypcbot.__version__ in result.stdout


def test_skill_command_renders_and_raw_does_not():
    rendered = runner.invoke(app, ["skill"])
    assert rendered.exit_code == 0
    assert skill.IDENTITY_MARKER not in rendered.stdout

    raw = runner.invoke(app, ["skill", "--raw"])
    assert raw.exit_code == 0
    assert skill.IDENTITY_MARKER in raw.stdout


def test_skill_declares_the_cli_as_its_canonical_source():
    raw = skill.read_raw()
    assert "fae skill" in raw
    assert "fae version" in raw
