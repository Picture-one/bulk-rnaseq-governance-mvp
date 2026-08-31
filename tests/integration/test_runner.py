import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from rnaseq_mvp.checksums import hash_file
from rnaseq_mvp.definitions import DefinitionRegistry
from rnaseq_mvp.manifests import atomic_write_json
from rnaseq_mvp.runner import IntegrityError, run_stage
from rnaseq_mvp.state import RunStatus, StateStore


class NeverExecutor:
    def __init__(self) -> None:
        self.called = False

    def run(self, *args, **kwargs):
        self.called = True
        raise AssertionError("executor must not run after integrity failure")


def test_changed_parameters_are_blocked_before_executor(tmp_path: Path) -> None:
    run_id = "T2A_20260901T013000Z"
    run_directory = tmp_path / "runs" / run_id
    run_directory.mkdir(parents=True)
    artifacts = {}
    for name, content in {
        "input_manifest.tsv": "sample_id\tpath\nS1\t/a.fastq.gz\n",
        "reference_manifest.tsv": "role\tpath\ngenome_fasta\t/a.fa.gz\n",
        "samplesheet.csv": "sample,fastq_1,fastq_2\nS1,/a,/b\n",
        "parameters.yaml": "input: /original.csv\n",
    }.items():
        path = run_directory / name
        path.write_text(content, encoding="utf-8")
        artifacts[name] = path

    atomic_write_json(
        run_directory / "preparation.json",
        {
            "status": "PREPARED",
            "stage_id": "T2A",
            "run_id": run_id,
            "input_manifest_path": str(artifacts["input_manifest.tsv"]),
            "reference_manifest_path": str(artifacts["reference_manifest.tsv"]),
            "samplesheet_path": str(artifacts["samplesheet.csv"]),
            "parameters_path": str(artifacts["parameters.yaml"]),
            "input_manifest_sha256": hash_file(
                artifacts["input_manifest.tsv"], "sha256"
            ),
            "reference_manifest_sha256": hash_file(
                artifacts["reference_manifest.tsv"], "sha256"
            ),
            "samplesheet_sha256": hash_file(artifacts["samplesheet.csv"], "sha256"),
            "scientific_template_sha256": "a" * 64,
            "parameters_sha256": hash_file(artifacts["parameters.yaml"], "sha256"),
        },
    )
    store = StateStore(tmp_path)
    store.create("T2A", run_id)
    store.transition(run_id, RunStatus.PREFLIGHT_PASSED)
    store.transition(run_id, RunStatus.PREPARED)

    now = datetime(2026, 9, 1, 2, 0, tzinfo=timezone.utc)
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "preflight_report.json").write_text(
        json.dumps(
            {
                "profile": "server_docker",
                "workspace": str(tmp_path.resolve()),
                "status": "PASS",
                "created_at": now.isoformat(),
                "checks": [],
            }
        ),
        encoding="utf-8",
    )
    artifacts["parameters.yaml"].write_text("input: /changed.csv\n", encoding="utf-8")
    executor = NeverExecutor()
    repo_root = Path(__file__).resolve().parents[2]
    registry = DefinitionRegistry.load(repo_root / "definitions")

    with pytest.raises(IntegrityError, match="parameters changed after prepare"):
        run_stage(
            "T2A",
            run_id,
            "server_docker",
            tmp_path,
            registry,
            executor,
            resume=True,
            now=now,
        )

    assert executor.called is False
    assert store.load(run_id).status == RunStatus.PREPARED


def test_successful_run_sets_nxf_version_and_writes_provenance(
    tmp_path: Path,
) -> None:
    run_id = "T2A_20260901T013000Z"
    run_directory = tmp_path / "runs" / run_id
    run_directory.mkdir(parents=True)
    output_directory = tmp_path / "results" / "T2A" / run_id
    artifacts = {}
    for name, content in {
        "input_manifest.tsv": "sample_id\tpath\nS1\t/a.fastq.gz\n",
        "reference_manifest.tsv": "role\tpath\ngenome_fasta\t/a.fa.gz\n",
        "samplesheet.csv": "sample,fastq_1,fastq_2\nS1,/a,/b\n",
        "parameters.yaml": f"input: /original.csv\noutdir: {output_directory}\n",
    }.items():
        path = run_directory / name
        path.write_text(content, encoding="utf-8")
        artifacts[name] = path
    atomic_write_json(
        run_directory / "preparation.json",
        {
            "status": "PREPARED",
            "stage_id": "T2A",
            "run_id": run_id,
            "input_manifest_path": str(artifacts["input_manifest.tsv"]),
            "reference_manifest_path": str(artifacts["reference_manifest.tsv"]),
            "samplesheet_path": str(artifacts["samplesheet.csv"]),
            "parameters_path": str(artifacts["parameters.yaml"]),
            "input_manifest_sha256": hash_file(
                artifacts["input_manifest.tsv"], "sha256"
            ),
            "reference_manifest_sha256": hash_file(
                artifacts["reference_manifest.tsv"], "sha256"
            ),
            "samplesheet_sha256": hash_file(artifacts["samplesheet.csv"], "sha256"),
            "scientific_template_sha256": "a" * 64,
            "parameters_sha256": hash_file(artifacts["parameters.yaml"], "sha256"),
        },
    )
    store = StateStore(tmp_path)
    store.create("T2A", run_id)
    store.transition(run_id, RunStatus.PREFLIGHT_PASSED)
    store.transition(run_id, RunStatus.PREPARED)
    now = datetime(2026, 9, 1, 2, 0, tzinfo=timezone.utc)
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "preflight_report.json").write_text(
        json.dumps(
            {
                "profile": "server_docker",
                "workspace": str(tmp_path.resolve()),
                "status": "PASS",
                "created_at": now.isoformat(),
                "checks": [],
            }
        ),
        encoding="utf-8",
    )

    class SuccessfulExecutor:
        def run(self, args, cwd, env, stdout_path, stderr_path):
            assert env["NXF_VER"] == "25.10.4"
            assert cwd == tmp_path.resolve()
            stdout_path.write_text("completed\n", encoding="utf-8")
            stderr_path.write_text("", encoding="utf-8")
            return subprocess.CompletedProcess(args, 0)

    repo_root = Path(__file__).resolve().parents[2]
    registry = DefinitionRegistry.load(repo_root / "definitions")
    result = run_stage(
        "T2A",
        run_id,
        "server_docker",
        tmp_path,
        registry,
        SuccessfulExecutor(),
        resume=True,
        now=now,
    )

    provenance = json.loads(result.provenance_path.read_text(encoding="utf-8"))
    assert result.status == "EXECUTED"
    assert provenance["pipeline_version"] == "3.26.0"
    assert provenance["nextflow_version"] == "25.10.4"
    assert provenance["exit_code"] == 0
    assert store.load(run_id).status == RunStatus.EXECUTED
