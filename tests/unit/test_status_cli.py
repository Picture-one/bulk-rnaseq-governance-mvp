import json
from pathlib import Path

from typer.testing import CliRunner

from rnaseq_mvp.cli import app
from rnaseq_mvp.orchestrator import StatusSummary

runner = CliRunner()


def test_status_cli_json_has_stable_contract(tmp_path: Path, monkeypatch) -> None:
    expected = StatusSummary(
        stage_id="T2A",
        run_id="T2A_20260901T013000Z",
        status="AWAITING_REVIEW",
        last_error=None,
        next_action="record human review",
        release_allowed=False,
    )
    monkeypatch.setattr("rnaseq_mvp.cli.stage_status", lambda *args: expected)

    result = runner.invoke(
        app,
        [
            "status",
            "--stage",
            "T2A",
            "--workspace",
            str(tmp_path),
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == expected.model_dump(mode="json")
