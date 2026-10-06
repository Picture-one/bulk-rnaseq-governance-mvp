from pathlib import Path

from rnaseq_mvp.models import MethodDefinition
from rnaseq_mvp.runner import build_longread_command, build_nextflow_command, build_pipeline_command


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


def test_longread_command_is_not_nf_core_rnaseq() -> None:
    method = MethodDefinition(
        schema_version="1.0",
        method_profile_id="longread_rnaseq_minimap2_gene_counts_v1",
        method_family="longread_gene_counts",
        nextflow_version=None,
        pipeline_name="custom-longread-gene-counts",
        pipeline_version="0.1.0",
        aligner="minimap2",
        quantifier="featureCounts",
        aggregation="gene_assignment",
        counts_measure_type="assigned_longread_gene_counts",
    )

    command = build_longread_command(
        run_id="LR_20261005T000000Z",
        repo_root=Path("/opt/bulk-rnaseq-governance-mvp"),
        workspace=Path("/data/rnaseq/runtime"),
    )

    assert command[0] == "rnaseq-mvp-longread"
    assert "nf-core/rnaseq" not in command
    assert "--samplesheet" in command
    assert "/data/rnaseq/runtime/runs/LR_20261005T000000Z/longread_samplesheet.csv" in command

    dispatched = build_pipeline_command(
        stage_id="LR",
        run_id="LR_20261005T000000Z",
        profile="server_docker",
        repo_root=Path("/opt/bulk-rnaseq-governance-mvp"),
        workspace=Path("/data/rnaseq/runtime"),
        resume=False,
        method=method,
    )

    assert dispatched == command
