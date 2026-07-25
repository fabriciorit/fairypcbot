from __future__ import annotations

import json

from typer.testing import CliRunner

from fairypcbot.cli import app

runner = CliRunner()


def test_schema_intent_outputs_valid_json_schema():
    result = runner.invoke(app, ["schema", "intent"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert "properties" in data


def test_schema_unknown_name_fails():
    result = runner.invoke(app, ["schema", "not_a_schema"])
    assert result.exit_code == 1
