from typer.testing import CliRunner

from rnaseq_mvp.cli import app

runner = CliRunner()


def test_version_command_reports_frozen_version() -> None:
    result = runner.invoke(app, ["version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == "rnaseq-mvp 0.1.0"


def test_help_lists_governance_commands() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0

    for command in (
        "preflight",
        "prepare",
        "run",
        "validate",
        "review",
        "package",
        "status",
        "execute",
        "smoke-test",
    ):
        assert command in result.stdout
