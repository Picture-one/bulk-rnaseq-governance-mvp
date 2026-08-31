from pathlib import Path

from typer.testing import CliRunner

from rnaseq_mvp.cli import app
from rnaseq_mvp.prepare import PreparationError, PreparationResult

runner = CliRunner()


def _result(workspace: Path) -> PreparationResult:
    run_directory = workspace / "runs" / "T2A_20260901T013000Z"
    return PreparationResult(
        status="PREPARED",
        stage_id="T2A",
        run_id="T2A_20260901T013000Z",
        input_manifest_path=run_directory / "input_manifest.tsv",
        reference_manifest_path=run_directory / "reference_manifest.tsv",
        samplesheet_path=run_directory / "samplesheet.csv",
        parameters_path=run_directory / "parameters.yaml",
        input_manifest_sha256="a" * 64,
        reference_manifest_sha256="b" * 64,
        samplesheet_sha256="c" * 64,
        scientific_template_sha256="d" * 64,
        parameters_sha256="e" * 64,
    )


def test_prepare_cli_prints_run_and_artifact_paths(
    tmp_path: Path,
    monkeypatch,
) -> None:
    expected = _result(tmp_path)

    monkeypatch.setattr(
        "rnaseq_mvp.cli.prepare_stage",
        lambda stage_id, workspace, registry, client, now: expected,
    )

    result = runner.invoke(
        app,
        ["prepare", "--stage", "T2A", "--workspace", str(tmp_path)],
    )

    assert result.exit_code == 0
    assert expected.run_id in result.stdout
    assert str(expected.input_manifest_path) in result.stdout
    assert str(expected.reference_manifest_path) in result.stdout


def test_prepare_cli_maps_preparation_error_to_exit_four(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def fail(*args, **kwargs):
        raise PreparationError("download verification failed")

    monkeypatch.setattr("rnaseq_mvp.cli.prepare_stage", fail)

    result = runner.invoke(
        app,
        ["prepare", "--stage", "T2A", "--workspace", str(tmp_path)],
    )

    assert result.exit_code == 4
    assert "download verification failed" in result.stderr
