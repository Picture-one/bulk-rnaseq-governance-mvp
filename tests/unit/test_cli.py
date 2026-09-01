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


def test_smoke_help_lists_assets_manifest_option() -> None:
    result = runner.invoke(app, ["smoke-test", "--help"])

    assert result.exit_code == 0
    assert "--assets-manifest" in result.stdout


def test_execution_help_lists_arm64_profile() -> None:
    for command in ("smoke-test", "run", "execute"):
        result = runner.invoke(app, [command, "--help"])

        assert result.exit_code == 0
        assert "server_docker_arm64" in result.stdout
