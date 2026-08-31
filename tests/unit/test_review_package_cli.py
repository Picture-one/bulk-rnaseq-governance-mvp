from pathlib import Path

from typer.testing import CliRunner

from rnaseq_mvp.cli import app
from rnaseq_mvp.packager import PackageResult

runner = CliRunner()


def test_package_cli_prints_release_directory(tmp_path: Path, monkeypatch) -> None:
    release = tmp_path / "release" / "T2A" / "T2A_20260901T013000Z"
    expected = PackageResult(
        stage_id="T2A",
        run_id="T2A_20260901T013000Z",
        status="READY_FOR_RESEARCH",
        release_directory=release,
        checksums_path=release / "checksums.sha256",
    )
    monkeypatch.setattr("rnaseq_mvp.cli.package_run", lambda *args: expected)

    result = runner.invoke(
        app,
        [
            "package",
            "--stage",
            "T2A",
            "--run-id",
            expected.run_id,
            "--workspace",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0
    assert "READY_FOR_RESEARCH" in result.stdout
    assert str(release) in result.stdout
