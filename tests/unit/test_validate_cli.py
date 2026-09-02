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
def test_revalidate_cli_passes_reason_and_revalidate_flag(
    tmp_path: Path,
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_validate(*args, **kwargs):
        captured.update(kwargs)
        return FakeReport()

    monkeypatch.setattr(
        "rnaseq_mvp.cli.validate_stage",
        fake_validate,
    )

    result = runner.invoke(
        app,
        [
            "revalidate",
            "--stage",
            "T2A",
            "--run-id",
            "T2A_20260902T042101Z",
            "--workspace",
            str(tmp_path),
            "--reason",
            "MultiQC 3.26 parser compatibility fix",
        ],
    )

    assert result.exit_code == 0
    assert captured["revalidate"] is True
    assert captured["reason"] == (
        "MultiQC 3.26 parser compatibility fix"
    )
    assert "Revalidation status: PASS" in result.stdout
