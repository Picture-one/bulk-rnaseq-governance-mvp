import json
from pathlib import Path

from typer.testing import CliRunner

from rnaseq_mvp.cli import app
from rnaseq_mvp.preflight import (
    RealSystemProbe,
    StaticSystemProbe,
)

runner = CliRunner()


def test_preflight_cli_writes_failure_report_and_exits_three(
    tmp_path: Path,
    monkeypatch,
) -> None:
    probe = StaticSystemProbe(
        system="Linux",
        architecture="x86_64",
        cpus=16,
        memory_gib=31.5,
        disk_free_gib=600,
        java_version="17.0.20",
        nextflow_version="25.10.4",
        docker_version="29.7.2",
        docker_hello_ok=True,
        reachable_urls={
            "github": True,
            "encode": True,
            "gencode": True,
            "container_registry": True,
        },
    )

    monkeypatch.setattr(
        RealSystemProbe,
        "collect",
        classmethod(
            lambda cls, workspace: probe
        ),
    )

    result = runner.invoke(
        app,
        [
            "preflight",
            "--profile",
            "server_docker",
            "--workspace",
            str(tmp_path),
        ],
    )

    report_path = (
        tmp_path
        / "reports"
        / "preflight_report.json"
    )
    report = json.loads(
        report_path.read_text(encoding="utf-8")
    )

    assert result.exit_code == 3
    assert report["status"] == "FAIL"
    assert report["profile"] == "server_docker"
    assert "memory" in result.stdout
    assert "FAIL" in result.stdout
