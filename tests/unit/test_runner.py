from pathlib import Path

from rnaseq_mvp.runner import build_nextflow_command


def test_t2a_command_is_frozen() -> None:
    command = build_nextflow_command(
        stage_id="T2A",
        run_id="T2A_20260901T013000Z",
        profile="server_docker",
        repo_root=Path("/opt/bulk-rnaseq-governance-mvp"),
        workspace=Path("/data/rnaseq/runtime"),
        resume=True,
    )

    assert command == [
        "nextflow",
        "run",
        "nf-core/rnaseq",
        "-r",
        "3.26.0",
        "-profile",
        "docker",
        "-params-file",
        "/data/rnaseq/runtime/runs/T2A_20260901T013000Z/parameters.yaml",
        "-c",
        "/opt/bulk-rnaseq-governance-mvp/configs/profiles/server_docker.config",
        "-work-dir",
        "/data/rnaseq/runtime/work",
        "-resume",
    ]
