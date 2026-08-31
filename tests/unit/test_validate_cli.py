from pathlib import Path

from typer.testing import CliRunner

from rnaseq_mvp.cli import app

runner = CliRunner()


class FakeReport:
    status = "PASS"
    counts_path = Path("/results/counts.tsv")
    reference_traceability = "PASS"


def test_validate_cli_prints_validation_status(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "rnaseq_mvp.cli.validate_stage", lambda *args, **kwargs: FakeReport()
    )

    result = runner.invoke(
        app,
        [
            "validate",
            "--stage",
            "T2A",
            "--run-id",
            "T2A_20260901T013000Z",
            "--workspace",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0
    assert "PASS" in result.stdout
    assert "counts.tsv" in result.stdout
