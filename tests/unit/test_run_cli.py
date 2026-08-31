from pathlib import Path

from typer.testing import CliRunner

from rnaseq_mvp.cli import app
from rnaseq_mvp.runner import RunResult

runner = CliRunner()


def test_run_cli_prints_executed_status(tmp_path: Path, monkeypatch) -> None:
    run_id = "T2A_20260901T013000Z"
    expected = RunResult(
        stage_id="T2A",
        run_id=run_id,
        status="EXECUTED",
        exit_code=0,
        command=["nextflow"],
        provenance_path=tmp_path / "runs" / run_id / "run_provenance.json",
        stdout_path=tmp_path / "runs" / run_id / "nextflow.stdout.log",
        stderr_path=tmp_path / "runs" / run_id / "nextflow.stderr.log",
    )
    monkeypatch.setattr("rnaseq_mvp.cli.run_stage", lambda *args, **kwargs: expected)

    result = runner.invoke(
        app,
        [
            "run",
            "--stage",
            "T2A",
            "--run-id",
            run_id,
            "--profile",
            "server_docker",
            "--workspace",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0
    assert "EXECUTED" in result.stdout
    assert str(expected.provenance_path) in result.stdout
