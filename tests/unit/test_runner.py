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
def test_arm64_command_uses_wave_profile() -> None:
    command = build_nextflow_command(
        stage_id="T2A",
        run_id="T2A_20260902T040000Z",
        profile="server_docker_arm64",
        repo_root=Path("/opt/bulk-rnaseq-governance-mvp"),
        workspace=Path("/data/rnaseq-arm/runtime"),
        resume=True,
    )

    assert command[command.index("-r") + 1] == "3.26.0"
    assert command[command.index("-profile") + 1] == "docker"
    assert command[command.index("-c") + 1] == (
        "/opt/bulk-rnaseq-governance-mvp/"
        "configs/profiles/server_docker_arm64.config"
    )
